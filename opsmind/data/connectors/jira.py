"""
JIRA Real-time Connector for OpsMind RAG system
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, AsyncGenerator, cast
from urllib.parse import urljoin
import base64
import logging
import pandas as pd

from .base import BaseConnector, ConnectorConfig, DataRecord
from opsmind.config import get_jira_config, logger


def create_jira_connector(name: str = "jira_connector", **override_params) -> Optional['JiraConnector']:
    """
    Create a JIRA connector using environment configuration
    
    Args:
        name: Name for the connector
        **override_params: Override any configuration parameters
        
    Returns:
        JiraConnector instance or None if configuration is invalid
    """
    try:
        jira_config = get_jira_config()
        
        # Check if Jira is enabled and properly configured
        if not jira_config["enabled"]:
            logger.info("Jira connector is disabled in configuration")
            return None
        
        if not all([jira_config["base_url"], jira_config["username"], jira_config["api_token"]]):
            logger.warning("Jira connector configuration is incomplete")
            return None
        
        # Merge override parameters
        connection_params = {
            "base_url": jira_config["base_url"],
            "username": jira_config["username"],
            "api_token": jira_config["api_token"],
            "project_keys": jira_config["project_keys"],
            **override_params
        }
        
        # Create connector configuration
        config = ConnectorConfig(
            name=name,
            connector_type="jira",
            enabled=jira_config["enabled"],
            poll_interval=jira_config["poll_interval"],
            max_retries=jira_config["max_retries"],
            retry_delay=jira_config["retry_delay"],
            batch_size=jira_config["batch_size"],
            connection_params=connection_params
        )
        
        return JiraConnector(config)
        
    except Exception as e:
        logger.error(f"Error creating Jira connector: {e}")
        return None


class JiraConnector(BaseConnector):
    """Real-time JIRA connector for fetching issues, comments, and updates"""
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_sync_time: Optional[datetime] = None
        self.auth_header: Optional[str] = None
        
        # JIRA specific configuration - validate and assign
        base_url = config.connection_params.get('base_url')
        username = config.connection_params.get('username') 
        api_token = config.connection_params.get('api_token')
        
        if not all([base_url, username, api_token]):
            raise ValueError("JIRA connector requires base_url, username, and api_token")
        
        # Ensure types are correct after validation
        if not isinstance(base_url, str):
            raise ValueError("base_url must be a string")
        if not isinstance(username, str):
            raise ValueError("username must be a string")
        if not isinstance(api_token, str):
            raise ValueError("api_token must be a string")
        
        # Now assign with proper types
        self.base_url: str = base_url.rstrip('/')  # Remove trailing slash
        self.username: str = username
        self.api_token: str = api_token
        self.project_keys = config.connection_params.get('project_keys', [])
        self.jql_filter = config.connection_params.get('jql_filter', '')
    
    async def connect(self) -> bool:
        """Establish connection to JIRA"""
        try:
            # Create auth header
            auth_string = f"{self.username}:{self.api_token}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            self.auth_header = f"Basic {auth_b64}"
            
            # Create HTTP session
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'Authorization': self.auth_header,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            # Test connection
            url = urljoin(self.base_url, '/rest/api/2/myself')
            async with self.session.get(url) as response:
                if response.status == 200:
                    user_info = await response.json()
                    logger.info(f"Connected to JIRA as {user_info.get('displayName', 'Unknown')}")
                    return True
                else:
                    logger.error(f"JIRA connection failed: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error connecting to JIRA: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to JIRA"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def fetch_data(self) -> AsyncGenerator[List[DataRecord], None]:
        """Fetch data from JIRA - yields batches of records"""
        if not self.session:
            logger.error("JIRA session not established")
            return
        
        # Set last sync time if not set (start from 1 hour ago)
        if not self.last_sync_time:
            self.last_sync_time = datetime.now() - timedelta(hours=1)
        
        try:
            # Fetch recent issues
            issues = await self._fetch_recent_issues()
            if issues:
                yield issues
            
            # Fetch recent comments
            comments = await self._fetch_recent_comments()
            if comments:
                yield comments
            
            # Fetch recent worklogs
            worklogs = await self._fetch_recent_worklogs()
            if worklogs:
                yield worklogs
            
            # Update last sync time
            self.last_sync_time = datetime.now()
            
        except Exception as e:
            logger.error(f"Error fetching JIRA data: {e}")
            raise
    
    async def _fetch_recent_issues(self) -> List[DataRecord]:
        """Fetch recently updated issues"""
        records = []
        
        if not self.session:
            return records
        
        try:
            # Build JQL query for recent updates
            jql_parts = []
            
            # Add project filter if specified
            if self.project_keys:
                project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                jql_parts.append(f"({project_filter})")
            
            # Add time filter
            time_filter = f"updated >= -{self.config.poll_interval}m"
            jql_parts.append(time_filter)
            
            # Add custom JQL filter if specified
            if self.jql_filter:
                jql_parts.append(f"({self.jql_filter})")
            
            jql = " AND ".join(jql_parts)
            
            # Make API request
            url = urljoin(self.base_url, '/rest/api/2/search')
            params = {
                'jql': jql,
                'maxResults': self.config.batch_size,
                'expand': 'changelog',
                'fields': 'summary,description,status,priority,assignee,reporter,created,updated,components,labels,fixVersions,customfield_*'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for issue in data.get('issues', []):
                        record = self._convert_issue_to_record(issue)
                        records.append(record)
                        
                        # Also create records for changelog entries
                        changelog_records = self._extract_changelog_records(issue)
                        records.extend(changelog_records)
                        
                else:
                    logger.warning(f"Failed to fetch issues: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error fetching recent issues: {e}")
        
        return records
    
    async def _fetch_recent_comments(self) -> List[DataRecord]:
        """Fetch recent comments across projects"""
        records = []
        
        if not self.session:
            return records
        
        try:
            # Get recently updated issues first (they might have new comments)
            jql_parts = []
            
            if self.project_keys:
                project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                jql_parts.append(f"({project_filter})")
            
            # Look for issues updated in the last poll interval
            time_filter = f"updated >= -{self.config.poll_interval}m"
            jql_parts.append(time_filter)
            
            jql = " AND ".join(jql_parts)
            
            url = urljoin(self.base_url, '/rest/api/2/search')
            params = {
                'jql': jql,
                'maxResults': self.config.batch_size,
                'fields': 'key'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # For each issue, fetch recent comments
                    for issue in data.get('issues', []):
                        issue_key = issue['key']
                        comment_records = await self._fetch_issue_comments(issue_key)
                        records.extend(comment_records)
                        
        except Exception as e:
            logger.error(f"Error fetching recent comments: {e}")
        
        return records
    
    async def _fetch_issue_comments(self, issue_key: str) -> List[DataRecord]:
        """Fetch comments for a specific issue"""
        records = []
        
        if not self.session:
            return records
        
        try:
            url = urljoin(self.base_url, f'/rest/api/2/issue/{issue_key}/comment')
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for comment in data.get('comments', []):
                        # Only include recent comments
                        comment_created = datetime.fromisoformat(
                            comment['created'].replace('Z', '+00:00')
                        )
                        
                        if self.last_sync_time and comment_created >= self.last_sync_time:
                            record = DataRecord(
                                id=f"jira_comment_{comment['id']}",
                                source="jira",
                                type="comment",
                                timestamp=comment_created,
                                data={
                                    'issue_key': issue_key,
                                    'comment_id': comment['id'],
                                    'body': comment['body'],
                                    'author': comment['author']['displayName'],
                                    'author_email': comment['author'].get('emailAddress', ''),
                                    'created': comment['created'],
                                    'updated': comment.get('updated', comment['created']),
                                    'visibility': comment.get('visibility', {})
                                },
                                metadata={
                                    'jira_url': f"{self.base_url}/browse/{issue_key}",
                                    'connector': self.config.name
                                }
                            )
                            records.append(record)
                            
        except Exception as e:
            logger.error(f"Error fetching comments for {issue_key}: {e}")
        
        return records
    
    async def _fetch_recent_worklogs(self) -> List[DataRecord]:
        """Fetch recent worklogs"""
        records = []
        
        if not self.session:
            return records
        
        try:
            # Similar approach to comments - get recently updated issues
            jql_parts = []
            
            if self.project_keys:
                project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                jql_parts.append(f"({project_filter})")
            
            time_filter = f"worklogDate >= -{self.config.poll_interval}m"
            jql_parts.append(time_filter)
            
            jql = " AND ".join(jql_parts)
            
            url = urljoin(self.base_url, '/rest/api/2/search')
            params = {
                'jql': jql,
                'maxResults': self.config.batch_size,
                'fields': 'key,worklog'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for issue in data.get('issues', []):
                        issue_key = issue['key']
                        worklog_records = await self._fetch_issue_worklogs(issue_key)
                        records.extend(worklog_records)
                        
        except Exception as e:
            logger.error(f"Error fetching recent worklogs: {e}")
        
        return records
    
    async def _fetch_issue_worklogs(self, issue_key: str) -> List[DataRecord]:
        """Fetch worklogs for a specific issue"""
        records = []
        
        if not self.session:
            return records
        
        try:
            url = urljoin(self.base_url, f'/rest/api/2/issue/{issue_key}/worklog')
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for worklog in data.get('worklogs', []):
                        # Only include recent worklogs
                        worklog_created = datetime.fromisoformat(
                            worklog['created'].replace('Z', '+00:00')
                        )
                        
                        if self.last_sync_time and worklog_created >= self.last_sync_time:
                            record = DataRecord(
                                id=f"jira_worklog_{worklog['id']}",
                                source="jira",
                                type="worklog",
                                timestamp=worklog_created,
                                data={
                                    'issue_key': issue_key,
                                    'worklog_id': worklog['id'],
                                    'time_spent': worklog['timeSpent'],
                                    'time_spent_seconds': worklog['timeSpentSeconds'],
                                    'comment': worklog.get('comment', ''),
                                    'author': worklog['author']['displayName'],
                                    'author_email': worklog['author'].get('emailAddress', ''),
                                    'created': worklog['created'],
                                    'updated': worklog.get('updated', worklog['created']),
                                    'started': worklog['started']
                                },
                                metadata={
                                    'jira_url': f"{self.base_url}/browse/{issue_key}",
                                    'connector': self.config.name
                                }
                            )
                            records.append(record)
                            
        except Exception as e:
            logger.error(f"Error fetching worklogs for {issue_key}: {e}")
        
        return records
    
    def _convert_issue_to_record(self, issue: Dict[str, Any]) -> DataRecord:
        """Convert JIRA issue to DataRecord"""
        fields = issue['fields']
        
        return DataRecord(
            id=f"jira_issue_{issue['key']}",
            source="jira",
            type="issue",
            timestamp=datetime.fromisoformat(fields['updated'].replace('Z', '+00:00')),
            data={
                'key': issue['key'],
                'summary': fields.get('summary', ''),
                'description': fields.get('description', ''),
                'status': fields.get('status', {}).get('name', ''),
                'status_category': fields.get('status', {}).get('statusCategory', {}).get('name', ''),
                'priority': fields.get('priority', {}).get('name', ''),
                'assignee': fields.get('assignee', {}).get('displayName', '') if fields.get('assignee') else '',
                'assignee_email': fields.get('assignee', {}).get('emailAddress', '') if fields.get('assignee') else '',
                'reporter': fields.get('reporter', {}).get('displayName', '') if fields.get('reporter') else '',
                'reporter_email': fields.get('reporter', {}).get('emailAddress', '') if fields.get('reporter') else '',
                'created': fields.get('created', ''),
                'updated': fields.get('updated', ''),
                'components': [comp['name'] for comp in fields.get('components', [])],
                'labels': fields.get('labels', []),
                'fix_versions': [ver['name'] for ver in fields.get('fixVersions', [])],
                'custom_fields': {k: v for k, v in fields.items() if k.startswith('customfield_')}
            },
            metadata={
                'jira_url': f"{self.base_url}/browse/{issue['key']}",
                'connector': self.config.name
            }
        )
    
    def _extract_changelog_records(self, issue: Dict[str, Any]) -> List[DataRecord]:
        """Extract changelog records from issue data"""
        records = []
        
        changelog = issue.get('changelog', {})
        if not changelog:
            return records
        
        histories = changelog.get('histories', [])
        
        for history in histories:
            for item in history.get('items', []):
                record = DataRecord(
                    id=f"{issue['key']}-changelog-{history['id']}-{item.get('field', 'unknown')}",
                    source="jira_changelog",
                    type="changelog",
                    timestamp=datetime.fromisoformat(history.get('created', '').replace('Z', '+00:00')) if history.get('created') else datetime.now(),
                    data={
                        "id": history['id'],
                        "key": issue['key'],
                        "author": history.get('author', {}),
                        "created": history.get('created', ''),
                        "field": item.get('field', ''),
                        "fieldtype": item.get('fieldtype', ''),
                        "from": item.get('from', ''),
                        "fromString": item.get('fromString', ''),
                        "to": item.get('to', ''),
                        "toString": item.get('toString', ''),
                        "issue_summary": issue.get('fields', {}).get('summary', ''),
                        "issue_status": issue.get('fields', {}).get('status', {}).get('name', ''),
                        "issue_priority": issue.get('fields', {}).get('priority', {}).get('name', ''),
                        "issue_project": issue.get('fields', {}).get('project', {}).get('key', '')
                                         },
                     metadata={
                        "issue_key": issue['key'],
                        "change_type": "field_change",
                        "field_changed": item.get('field', ''),
                        "change_id": history['id']
                    }
                )
                records.append(record)
        
        return records

    async def search_issues(
        self,
        jql: str = "",
        search_term: str = "",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        project: str = "",
        issue_type: str = "",
        created_after: str = "",
        created_before: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search JIRA issues with various filters using REST API
        
        Args:
            jql: Custom JQL query string
            search_term: Search in summary and description
            status: Filter by status name
            priority: Filter by priority name
            assignee: Filter by assignee
            project: Filter by project key
            issue_type: Filter by issue type
            created_after: Filter by creation date (YYYY-MM-DD)
            created_before: Filter by creation date (YYYY-MM-DD)
            limit: Maximum number of results to return
        
        Returns:
            List of matching issues
        """
        if not self.session:
            logger.error("JIRA session not established")
            return []
        
        try:
            # Build JQL query
            jql_parts = []
            
            # Use custom JQL if provided
            if jql:
                jql_parts.append(f"({jql})")
            else:
                # Build JQL from filters
                if search_term:
                    jql_parts.append(f'(summary ~ "{search_term}" OR description ~ "{search_term}")')
                
                if status:
                    jql_parts.append(f'status = "{status}"')
                
                if priority:
                    jql_parts.append(f'priority = "{priority}"')
                
                if assignee:
                    jql_parts.append(f'assignee = "{assignee}"')
                
                if project:
                    jql_parts.append(f'project = "{project}"')
                
                if issue_type:
                    jql_parts.append(f'issuetype = "{issue_type}"')
                
                if created_after:
                    jql_parts.append(f'created >= "{created_after}"')
                
                if created_before:
                    jql_parts.append(f'created <= "{created_before}"')
                
                # Add project filter if configured
                if self.project_keys:
                    project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                    jql_parts.append(f"({project_filter})")
            
            # Combine JQL parts
            final_jql = " AND ".join(jql_parts) if jql_parts else ""
            
            # Build search parameters
            params = {
                'jql': final_jql,
                'maxResults': min(limit, 100),  # API limit
                'startAt': 0,
                'expand': 'changelog',
                'fields': 'summary,description,status,priority,assignee,creator,created,updated,issuetype,project'
            }
            
            # Make API request
            url = urljoin(self.base_url, '/rest/api/2/search')
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    issues = data.get('issues', [])
                    logger.info(f"Found {len(issues)} issues matching search criteria")
                    return issues
                else:
                    logger.error(f"JIRA search failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error searching JIRA issues: {e}")
            return []

    async def get_issue_details(self, issue_key: str) -> Dict[str, Any]:
        """
        Get complete details for a specific JIRA issue including comments and changelog
        
        Args:
            issue_key: The JIRA issue key (e.g., 'PROJ-123')
        
        Returns:
            Dictionary containing issue details, comments, and changelog
        """
        if not self.session:
            logger.error("JIRA session not established")
            return {"error": "No session"}
        
        try:
            # Get issue details
            url = urljoin(self.base_url, f'/rest/api/2/issue/{issue_key}')
            params = {
                'expand': 'changelog',
                'fields': '*all'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    issue = await response.json()
                    
                    # Get comments
                    comments_url = urljoin(self.base_url, f'/rest/api/2/issue/{issue_key}/comment')
                    comments_params = {
                        'maxResults': 1000,
                        'startAt': 0
                    }
                    
                    comments = []
                    async with self.session.get(comments_url, params=comments_params) as comments_response:
                        if comments_response.status == 200:
                            comments_data = await comments_response.json()
                            comments = comments_data.get('comments', [])
                    
                    # Extract changelog from issue
                    changelog = []
                    if 'changelog' in issue:
                        for history in issue['changelog'].get('histories', []):
                            for item in history.get('items', []):
                                changelog.append({
                                    'id': history['id'],
                                    'author': history.get('author', {}),
                                    'created': history.get('created', ''),
                                    'field': item.get('field', ''),
                                    'fieldtype': item.get('fieldtype', ''),
                                    'from': item.get('from', ''),
                                    'fromString': item.get('fromString', ''),
                                    'to': item.get('to', ''),
                                    'toString': item.get('toString', '')
                                })
                    
                    result = {
                        'issue': issue,
                        'comments': comments,
                        'changelog': changelog,
                        'summary': {
                            'issue_found': True,
                            'comments_count': len(comments),
                            'changelog_count': len(changelog)
                        }
                    }
                    
                    logger.info(f"Retrieved details for {issue_key}: {len(comments)} comments, {len(changelog)} changelog entries")
                    return result
                else:
                    logger.error(f"Failed to get issue {issue_key}: {response.status}")
                    return {
                        'issue': None,
                        'comments': [],
                        'changelog': [],
                        'summary': {
                            'issue_found': False,
                            'comments_count': 0,
                            'changelog_count': 0
                        }
                    }
                    
        except Exception as e:
            logger.error(f"Error getting JIRA issue details for {issue_key}: {e}")
            return {
                'issue': None,
                'comments': [],
                'changelog': [],
                'summary': {
                    'issue_found': False,
                    'comments_count': 0,
                    'changelog_count': 0
                }
            }

    async def search_comments(
        self,
        issue_key: str = "",
        search_term: str = "",
        author: str = "",
        created_after: str = "",
        created_before: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search JIRA comments with various filters
        
        Args:
            issue_key: Filter by specific issue key
            search_term: Search in comment body
            author: Filter by comment author
            created_after: Filter by creation date (YYYY-MM-DD)
            created_before: Filter by creation date (YYYY-MM-DD)
            limit: Maximum number of results to return
        
        Returns:
            List of matching comments
        """
        if not self.session:
            logger.error("JIRA session not established")
            return []
        
        try:
            comments = []
            
            if issue_key:
                # Search comments for specific issue
                url = urljoin(self.base_url, f'/rest/api/2/issue/{issue_key}/comment')
                params = {
                    'maxResults': min(limit, 1000),
                    'startAt': 0
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        comments = data.get('comments', [])
            else:
                # Search across all accessible issues
                # This is more complex and would require searching issues first
                # For now, we'll use a JQL search to find issues and then get their comments
                search_jql = ""
                if search_term:
                    search_jql = f'comment ~ "{search_term}"'
                
                if author:
                    if search_jql:
                        search_jql += f' AND comment ~ "{author}"'
                    else:
                        search_jql = f'comment ~ "{author}"'
                
                if created_after:
                    if search_jql:
                        search_jql += f' AND commented >= "{created_after}"'
                    else:
                        search_jql = f'commented >= "{created_after}"'
                
                if created_before:
                    if search_jql:
                        search_jql += f' AND commented <= "{created_before}"'
                    else:
                        search_jql = f'commented <= "{created_before}"'
                
                # Add project filter if configured
                if self.project_keys:
                    project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                    if search_jql:
                        search_jql += f' AND ({project_filter})'
                    else:
                        search_jql = f'({project_filter})'
                
                if search_jql:
                    # Search for issues that have matching comments
                    issues = await self.search_issues(jql=search_jql, limit=50)
                    
                    # Get comments from these issues
                    for issue in issues:
                        issue_key = issue.get('key', '')
                        if issue_key:
                            issue_comments = await self.search_comments(
                                issue_key=issue_key,
                                search_term=search_term,
                                author=author,
                                created_after=created_after,
                                created_before=created_before,
                                limit=limit
                            )
                            comments.extend(issue_comments)
            
            # Apply additional filters to comments
            filtered_comments = []
            for comment in comments:
                # Apply search term filter
                if search_term:
                    comment_body = comment.get('body', '')
                    if search_term.lower() not in comment_body.lower():
                        continue
                
                # Apply author filter
                if author:
                    comment_author = comment.get('author', {}).get('displayName', '')
                    if author.lower() not in comment_author.lower():
                        continue
                
                # Apply date filters
                if created_after or created_before:
                    try:
                        comment_created = comment.get('created', '')
                        comment_date = pd.to_datetime(comment_created)
                        
                        if created_after:
                            after_date = pd.to_datetime(created_after)
                            if comment_date < after_date:
                                continue
                        
                        if created_before:
                            before_date = pd.to_datetime(created_before)
                            if comment_date > before_date:
                                continue
                    except:
                        # Skip if date parsing fails
                        continue
                
                filtered_comments.append(comment)
                
                # Apply limit
                if len(filtered_comments) >= limit:
                    break
            
            logger.info(f"Found {len(filtered_comments)} comments matching search criteria")
            return filtered_comments
            
        except Exception as e:
            logger.error(f"Error searching JIRA comments: {e}")
            return []

    async def correlate_with_incidents(
        self,
        incident_keywords: List[str],
        time_window_hours: int = 24,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Correlate JIRA data with incidents based on keywords and time window
        
        Args:
            incident_keywords: List of keywords to search for
            time_window_hours: Time window to search within
            limit: Maximum number of results per type
        
        Returns:
            Dictionary with correlation results
        """
        if not self.session:
            logger.error("JIRA session not established")
            return {"error": "No session"}
        
        try:
            # Calculate time window
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=time_window_hours)
            
            start_date = start_time.strftime('%Y-%m-%d')
            end_date = end_time.strftime('%Y-%m-%d')
            
            results = {
                'issues': [],
                'comments': [],
                'total_found': 0
            }
            
            # Search for issues with incident keywords
            for keyword in incident_keywords:
                if keyword and keyword.strip():
                    # Search in issues
                    issues = await self.search_issues(
                        search_term=keyword,
                        created_after=start_date,
                        created_before=end_date,
                        limit=limit
                    )
                    results['issues'].extend(issues)
                    
                    # Search in comments
                    comments = await self.search_comments(
                        search_term=keyword,
                        created_after=start_date,
                        created_before=end_date,
                        limit=limit
                    )
                    results['comments'].extend(comments)
            
            # Remove duplicates
            unique_issues = {}
            for issue in results['issues']:
                key = issue.get('key', '')
                if key:
                    unique_issues[key] = issue
            results['issues'] = list(unique_issues.values())
            
            unique_comments = {}
            for comment in results['comments']:
                key = f"{comment.get('id', '')}-{comment.get('created', '')}"
                if key:
                    unique_comments[key] = comment
            results['comments'] = list(unique_comments.values())
            
            results['total_found'] = len(results['issues']) + len(results['comments'])
            
            logger.info(f"Correlated {results['total_found']} JIRA items with incidents")
            return results
            
        except Exception as e:
            logger.error(f"Error correlating JIRA with incidents: {e}")
            return {"error": str(e)} 