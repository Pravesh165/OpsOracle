"""
Incident processing tools for OpsMind
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import re
import json
import pandas as pd

from google.adk.tools.tool_context import ToolContext
from opsmind.config import logger
from opsmind.utils import safe_json_loads
from opsmind.tools.guardrail import with_guardrail
from opsmind.data.loader import (
    load_incident_data,
    load_jira_data,
    search_jira_issues,
    search_jira_comments,
    search_jira_changelog,
    get_jira_issue_details
)

@with_guardrail
async def process_incident_stream(
    tool_context: ToolContext,
    incident_data: str
) -> Dict[str, str]:
    """Process incident data and add to context for RAG"""
    try:
        incident_info = safe_json_loads(incident_data)
        existing_incidents = tool_context.state.get("incident_stream", [])
        tool_context.state["incident_stream"] = existing_incidents + [incident_info]
        logger.info(f"Added incident {incident_info.get('number', 'unknown')} to stream")
        return {"status": "success", "message": f"Processed incident {incident_info.get('number', 'unknown')}"}
    except Exception as e:
        logger.error(f"Error processing incident: {e}")
        return {"status": "error", "message": str(e)}

@with_guardrail
async def create_incident_summary(
    tool_context: ToolContext,
    incident_id: str,
    summary_text: str
) -> Dict[str, str]:
    """Create incident summary and store for postmortem generation"""
    summaries = tool_context.state.get("incident_summaries", {})
    summaries[incident_id] = {
        "id": incident_id,
        "summary": summary_text,
        "timestamp": datetime.now().isoformat(),
        "status": "summarized"
    }
    tool_context.state["incident_summaries"] = summaries
    logger.info(f"Created summary for incident {incident_id}")
    return {"status": "success", "incident_id": incident_id}

@with_guardrail
async def search_incidents(
    tool_context: ToolContext,
    search_term: str = "",
    limit: int = 50
) -> Dict[str, Any]:
    """
    Simple fuzzy search for incidents
    
    Args:
        search_term: Search across all incident fields
        limit: Maximum number of results to return
    
    Returns:
        Dictionary with search results
    """
    try:
        incidents_df = load_incident_data()
        
        if incidents_df.empty:
            logger.warning("No incident data available")
            return {"incidents": [], "total_count": 0, "message": "No incident data available"}
        
        # Simple fuzzy search across multiple fields
        if search_term:
            search_mask = pd.Series([False] * len(incidents_df))
            search_columns = ['u_symptom', 'description', 'category', 'subcategory', 'priority', 'assignment_group']
            
            for col in search_columns:
                if col in incidents_df.columns:
                    mask = incidents_df[col].astype(str).str.contains(search_term, case=False, na=False)
                    search_mask = search_mask | mask
            
            filtered_df = incidents_df[search_mask]
        else:
            filtered_df = incidents_df
        
        # Apply limit
        if limit > 0:
            filtered_df = filtered_df.head(limit)
        
        # Convert to records
        results = [row.to_dict() for _, row in filtered_df.iterrows()]
        
        # Store in context
        tool_context.state["last_incident_search"] = {
            "results": results,
            "search_term": search_term,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Found {len(results)} incidents matching search")
        return {
            "incidents": results,
            "total_count": len(results),
            "message": f"Found {len(results)} incidents"
        }
        
    except Exception as e:
        logger.error(f"Error searching incidents: {e}")
        return {"incidents": [], "total_count": 0, "message": f"Error: {str(e)}"}

@with_guardrail
async def correlate_incident_with_jira(
    tool_context: ToolContext,
    incident_id: str,
    search_keywords: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Simple correlation between incident and JIRA data
    
    Args:
        incident_id: The incident ID to correlate
        search_keywords: Additional keywords to search for
    
    Returns:
        Dictionary with correlation results
    """
    try:
        # Load incident data
        incidents_df = load_incident_data()
        incident_data = [row.to_dict() for _, row in incidents_df.iterrows() if row.get('number') == incident_id]
        
        if not incident_data:
            return {
                "incident_found": False,
                "message": f"Incident {incident_id} not found"
            }
        
        incident = incident_data[0]
        
        # Build search terms
        search_terms = []
        if search_keywords:
            search_terms.extend(search_keywords)
        
        # Add incident-specific terms
        for field in ['u_symptom', 'category', 'subcategory']:
            if incident.get(field):
                search_terms.append(str(incident[field]))
        
        # Search JIRA data
        related_issues = []
        related_comments = []
        related_changelog = []
        
        for term in search_terms:
            if term and term.strip():
                # Simple search without complex time filters
                issues = search_jira_issues(search_term=term, limit=10)
                related_issues.extend(issues)
                
                comments = search_jira_comments(search_term=term, limit=10)
                related_comments.extend(comments)
                
                changelog = search_jira_changelog(limit=10)
                related_changelog.extend(changelog)
        
        # Remove duplicates
        related_issues = list({issue['key']: issue for issue in related_issues if issue.get('key')}.values())
        related_comments = list({f"{comment['key']}-{comment['comment.id']}": comment for comment in related_comments if comment.get('key')}.values())
        related_changelog = list({f"{change['key']}-{change['id']}": change for change in related_changelog if change.get('key')}.values())
        
        result = {
            "incident_found": True,
            "incident": incident,
            "related_issues": related_issues,
            "related_comments": related_comments,
            "related_changelog": related_changelog,
            "summary": {
                "incident_id": incident_id,
                "issues_count": len(related_issues),
                "comments_count": len(related_comments),
                "changelog_count": len(related_changelog),
                "search_terms": search_terms
            }
        }
        
        # Store in context
        tool_context.state["last_incident_correlation"] = result
        
        logger.info(f"Correlated incident {incident_id} with {len(related_issues)} issues, {len(related_comments)} comments")
        return result
        
    except Exception as e:
        logger.error(f"Error correlating incident {incident_id}: {e}")
        return {
            "incident_found": False,
            "message": f"Error correlating incident: {str(e)}"
        }

def search_jira_for_incidents(
    tool_context: ToolContext,
    search_terms: List[str],
    limit: int = 50
) -> Dict[str, Any]:
    """
    Simple search of JIRA data for incident-related information
    
    Args:
        search_terms: List of terms to search for
        limit: Maximum number of results per search type
    
    Returns:
        Dictionary with search results from JIRA
    """
    try:
        if not search_terms:
            return {
                "message": "No search terms provided",
                "results": {"issues": [], "comments": [], "changelog": []}
            }
        
        results = {
            "issues": [],
            "comments": [],
            "changelog": []
        }
        
        # Search across all terms
        for term in search_terms:
            if term and term.strip():
                # Search issues
                issues = search_jira_issues(search_term=term, limit=limit)
                results["issues"].extend(issues)
                
                # Search comments
                comments = search_jira_comments(search_term=term, limit=limit)
                results["comments"].extend(comments)
                
                # Search changelog
                changelog = search_jira_changelog(limit=limit)
                results["changelog"].extend(changelog)
        
        # Remove duplicates
        results["issues"] = list({issue['key']: issue for issue in results["issues"] if issue.get('key')}.values())
        results["comments"] = list({f"{comment['key']}-{comment['comment.id']}": comment for comment in results["comments"] if comment.get('key')}.values())
        results["changelog"] = list({f"{change['key']}-{change['id']}": change for change in results["changelog"] if change.get('key')}.values())
        
        total_found = len(results["issues"]) + len(results["comments"]) + len(results["changelog"])
        
        # Store in context
        tool_context.state["last_jira_incident_search"] = {
            "results": results,
            "search_terms": search_terms,
            "total_found": total_found,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Found {total_found} JIRA items")
        return {
            "results": results,
            "total_found": total_found,
            "message": f"Found {total_found} JIRA items"
        }
        
    except Exception as e:
        logger.error(f"Error searching JIRA: {e}")
        return {
            "message": f"Error searching JIRA: {str(e)}",
            "results": {"issues": [], "comments": [], "changelog": []}
        }

def get_incident_jira_timeline(
    tool_context: ToolContext,
    incident_id: str,
    jira_issue_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simple timeline of incident and related JIRA activity
    
    Args:
        incident_id: The incident ID
        jira_issue_key: Optional specific JIRA issue key
    
    Returns:
        Dictionary with timeline events
    """
    try:
        # Load incident data
        incidents_df = load_incident_data()
        incident_data = [row.to_dict() for _, row in incidents_df.iterrows() if row.get('number') == incident_id]
        
        if not incident_data:
            return {
                "incident_found": False,
                "message": f"Incident {incident_id} not found"
            }
        
        incident = incident_data[0]
        timeline = []
        
        # Add incident events
        timeline.append({
            "timestamp": incident.get('opened_at', ''),
            "event_type": "incident_opened",
            "source": "incident",
            "description": f"Incident {incident_id} opened: {incident.get('u_symptom', 'No description')}",
            "details": {
                "incident_number": incident.get('number', ''),
                "priority": incident.get('priority', ''),
                "category": incident.get('category', ''),
                "assignment_group": incident.get('assignment_group', '')
            }
        })
        
        # Add close event if available
        if incident.get('closed_at'):
            timeline.append({
                "timestamp": incident.get('closed_at', ''),
                "event_type": "incident_closed",
                "source": "incident",
                "description": f"Incident {incident_id} closed",
                "details": {
                    "resolution": incident.get('resolution', '')
                }
            })
        
        # Add related JIRA data if available
        try:
            jira_data = load_jira_data()
            
            # Add some JIRA issues (simplified)
            issues_df = jira_data.get('issues', pd.DataFrame())
            if not issues_df.empty:
                # Get recent issues or specific issue
                if jira_issue_key:
                    related_issues = [row.to_dict() for _, row in issues_df.iterrows() if row.get('key') == jira_issue_key]
                else:
                    related_issues = [row.to_dict() for _, row in issues_df.head(5).iterrows()]
                
                for issue in related_issues:
                    timeline.append({
                        "timestamp": issue.get('created', ''),
                        "event_type": "jira_issue_created",
                        "source": "jira",
                        "description": f"JIRA issue {issue.get('key')} created: {issue.get('summary', '')}",
                        "details": {
                            "jira_key": issue.get('key', ''),
                            "status": issue.get('status.name', ''),
                            "priority": issue.get('priority.name', '')
                        }
                    })
        except Exception as e:
            logger.warning(f"Could not add JIRA data to timeline: {e}")
        
        # Sort timeline by timestamp (simple sort)
        timeline.sort(key=lambda x: x.get('timestamp', ''))
        
        # Store in context
        tool_context.state["last_incident_timeline"] = {
            "incident_id": incident_id,
            "timeline": timeline,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Created timeline for incident {incident_id} with {len(timeline)} events")
        return {
            "incident_found": True,
            "incident_id": incident_id,
            "timeline": timeline,
            "total_events": len(timeline),
            "message": f"Created timeline with {len(timeline)} events"
        }
        
    except Exception as e:
        logger.error(f"Error creating timeline for incident {incident_id}: {e}")
        return {
            "incident_found": False,
            "message": f"Error creating timeline: {str(e)}"
        } 