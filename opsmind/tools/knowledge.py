"""
Knowledge Repository Tools for OpsMind - SRE/DevOps Knowledge Base
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from google.adk.tools.tool_context import ToolContext
from opsmind.config import logger
from opsmind.data.loader import (
    load_incident_data,
    load_jira_data
)
from opsmind.context import get_incident_context
from opsmind.utils import safe_get
from opsmind.tools.guardrail import with_guardrail
import pandas as pd


@with_guardrail
async def search_knowledge_base(
    tool_context: ToolContext,
    query: str,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Simple fuzzy search across the knowledge base
    
    Args:
        query: The search query
        limit: Maximum number of results per data source
    
    Returns:
        Dictionary with search results from all data sources
    """
    try:
        logger.info(f"Searching knowledge base for: {query}")
        
        # Simple search terms from query
        search_terms = _extract_simple_terms(query)
        
        results = {
            "query": query,
            "search_terms": search_terms,
            "results": {},
            "total_results": 0,
            "search_timestamp": datetime.now().isoformat()
        }
        
        # Search all data sources
        incidents = _search_incidents_simple(search_terms, limit)
        jira_issues = _search_jira_issues_simple(search_terms, limit)
        jira_comments = _search_jira_comments_simple(search_terms, limit)
        jira_changelog = _search_jira_changelog_simple(search_terms, limit)
        
        results["results"] = {
            "incidents": incidents,
            "jira_issues": jira_issues,
            "jira_comments": jira_comments,
            "jira_changelog": jira_changelog
        }
        
        results["total_results"] = len(incidents) + len(jira_issues) + len(jira_comments) + len(jira_changelog)
        
        # Store results in context
        tool_context.state["last_knowledge_search"] = results
        
        # Generate simple summary
        results["summary"] = _generate_simple_summary(results)
        
        logger.info(f"Knowledge base search completed: {results['total_results']} total results")
        return results
        
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return {
            "query": query,
            "error": str(e),
            "total_results": 0,
            "search_timestamp": datetime.now().isoformat()
        }


@with_guardrail
async def answer_devops_question(
    tool_context: ToolContext,
    question: str,
    search_limit: int = 15
) -> Dict[str, Any]:
    """
    Answer a DevOps/SRE question using the knowledge base
    
    Args:
        question: The DevOps/SRE question to answer
        search_limit: Limit for knowledge base search
    
    Returns:
        Dictionary with answer and supporting evidence
    """
    try:
        logger.info(f"Answering DevOps question: {question}")
        
        # Search the knowledge base
        search_results = await search_knowledge_base(
            tool_context=tool_context,
            query=question,
            limit=search_limit
        )
        
        # Analyze results and generate answer
        answer_data = _analyze_results_for_answer(question, search_results)
        
        # Simple confidence check
        has_sufficient_info = (
            search_results["total_results"] > 0 and 
            answer_data["confidence"] > 0.2
        )
        
        if has_sufficient_info:
            return {
                "question": question,
                "answer_found": True,
                "answer": answer_data["answer"],
                "confidence": answer_data["confidence"],
                "supporting_evidence": answer_data["evidence"],
                "search_results": search_results,
                "fallback_needed": False,
                "source": "knowledge_base"
            }
        else:
            return {
                "question": question,
                "answer_found": False,
                "message": "Insufficient information found in knowledge base. Web search recommended.",
                "partial_answer": answer_data["answer"] if answer_data["answer"] else None,
                "confidence": answer_data["confidence"],
                "supporting_evidence": answer_data["evidence"],
                "search_results": search_results,
                "fallback_needed": True,
                "source": "knowledge_base_insufficient"
            }
        
    except Exception as e:
        logger.error(f"Error answering DevOps question: {e}")
        return {
            "question": question,
            "answer_found": False,
            "error": str(e),
            "fallback_needed": True,
            "source": "error"
        }


@with_guardrail
async def find_similar_issues(
    tool_context: ToolContext,
    issue_description: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Find similar issues from historical data
    
    Args:
        issue_description: Description of the current issue
        limit: Maximum number of similar issues to return
    
    Returns:
        Dictionary with similar issues and their resolutions
    """
    try:
        logger.info(f"Finding similar issues for: {issue_description}")
        
        # Search for similar incidents and issues
        search_results = await search_knowledge_base(
            tool_context=tool_context,
            query=issue_description,
            limit=limit
        )
        
        # Extract similar issues with resolutions
        similar_issues = []
        
        # Process incidents
        for incident in search_results["results"].get("incidents", []):
            if incident.get("resolution"):
                similar_issues.append({
                    "type": "incident",
                    "id": incident.get("number"),
                    "title": incident.get("short_description", ""),
                    "description": incident.get("description", ""),
                    "resolution": incident.get("resolution", ""),
                    "category": incident.get("category", ""),
                    "priority": incident.get("priority", "")
                })
        
        # Process JIRA issues
        for issue in search_results["results"].get("jira_issues", []):
            if issue.get("status.name") in ["Resolved", "Closed", "Done"]:
                similar_issues.append({
                    "type": "jira_issue",
                    "id": issue.get("key"),
                    "title": issue.get("summary", ""),
                    "description": issue.get("description", ""),
                    "resolution": issue.get("resolution.name", ""),
                    "status": issue.get("status.name", ""),
                    "priority": issue.get("priority.name", "")
                })
        
        # Simple sort by resolution length (basic relevance)
        similar_issues.sort(key=lambda x: len(str(x.get("resolution", ""))), reverse=True)
        
        return {
            "query": issue_description,
            "similar_issues": similar_issues[:limit],
            "total_found": len(similar_issues),
            "search_results": search_results
        }
        
    except Exception as e:
        logger.error(f"Error finding similar issues: {e}")
        return {
            "query": issue_description,
            "similar_issues": [],
            "total_found": 0,
            "error": str(e)
        }


@with_guardrail
async def get_historical_patterns(
    tool_context: ToolContext,
    pattern_type: str = "all",
    time_period_days: int = 365
) -> Dict[str, Any]:
    """
    Get historical patterns from the knowledge base
    
    Args:
        pattern_type: Type of patterns to analyze (all, incidents, jira)
        time_period_days: Time period to analyze (defaults to analyzing all available data)
    
    Returns:
        Dictionary with historical patterns
    """
    try:
        logger.info(f"Analyzing historical patterns: {pattern_type}")
        
        patterns = {
            "pattern_type": pattern_type,
            "time_period_days": time_period_days,
            "analysis_timestamp": datetime.now().isoformat(),
            "patterns": {}
        }
        
        # Analyze patterns based on type
        if pattern_type in ["all", "incidents"]:
            patterns["patterns"]["incidents"] = _analyze_incident_patterns_comprehensive()
        
        if pattern_type in ["all", "jira"]:
            patterns["patterns"]["jira"] = _analyze_jira_patterns_comprehensive()
        
        return patterns
        
    except Exception as e:
        logger.error(f"Error analyzing historical patterns: {e}")
        return {
            "pattern_type": pattern_type,
            "error": str(e),
            "analysis_timestamp": datetime.now().isoformat()
        }


# === SIMPLIFIED HELPER FUNCTIONS ===

def _extract_simple_terms(query: str) -> List[str]:
    """Extract simple search terms from query"""
    # Simple word extraction, more flexible
    words = re.findall(r'\b\w+\b', query.lower())
    
    # Filter out very short words and common stop words
    stop_words = {'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
    'to', 'for', 'of', 'with', 'by', 'the', 'is', 'are', 'was', 'were', 
    'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 
    'would', 'could', 'should', 'may', 'might', 'can', 'that', 'this', 
    'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 
    'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their'}
    
    terms = [word for word in words if len(word) > 2 and word not in stop_words]
    
    return list(set(terms))


def _search_incidents_simple(terms: List[str], limit: int) -> List[Dict[str, Any]]:
    """Simple incident search"""
    try:
        incidents_df = load_incident_data()
        if incidents_df.empty:
            return []
        
        # Simple search across key fields
        if not terms:
            return [row.to_dict() for _, row in incidents_df.head(limit).iterrows()]
        
        search_mask = pd.Series([False] * len(incidents_df))
        search_columns = ['u_symptom', 'short_description', 'description', 'category', 'subcategory', 'resolution']
        
        for term in terms:
            for col in search_columns:
                if col in incidents_df.columns:
                    mask = incidents_df[col].astype(str).str.contains(term, case=False, na=False)
                    search_mask = search_mask | mask
        
        filtered_df = incidents_df[search_mask].head(limit)
        return [row.to_dict() for _, row in filtered_df.iterrows()]
        
    except Exception as e:
        logger.warning(f"Error searching incidents: {e}")
        return []


def _search_jira_issues_simple(terms: List[str], limit: int) -> List[Dict[str, Any]]:
    """Simple JIRA issues search"""
    try:
        jira_data = load_jira_data()
        issues_df = jira_data.get('issues', pd.DataFrame())
        
        if issues_df.empty:
            return []
        
        if not terms:
            return [row.to_dict() for _, row in issues_df.head(limit).iterrows()]
        
        search_mask = pd.Series([False] * len(issues_df))
        search_columns = ['summary', 'description', 'status.name', 'priority.name']
        
        for term in terms:
            for col in search_columns:
                if col in issues_df.columns:
                    mask = issues_df[col].astype(str).str.contains(term, case=False, na=False)
                    search_mask = search_mask | mask
        
        filtered_df = issues_df[search_mask].head(limit)
        return [row.to_dict() for _, row in filtered_df.iterrows()]
        
    except Exception as e:
        logger.warning(f"Error searching JIRA issues: {e}")
        return []


def _search_jira_comments_simple(terms: List[str], limit: int) -> List[Dict[str, Any]]:
    """Simple JIRA comments search"""
    try:
        jira_data = load_jira_data()
        comments_df = jira_data.get('comments', pd.DataFrame())
        
        if comments_df.empty:
            return []
        
        if not terms:
            return [row.to_dict() for _, row in comments_df.head(limit).iterrows()]
        
        search_mask = pd.Series([False] * len(comments_df))
        
        for term in terms:
            # Use the correct column name from the CSV
            body_col = 'comment.body' if 'comment.body' in comments_df.columns else 'body'
            mask = comments_df[body_col].astype(str).str.contains(term, case=False, na=False)
            search_mask = search_mask | mask
        
        filtered_df = comments_df[search_mask].head(limit)
        return [row.to_dict() for _, row in filtered_df.iterrows()]
        
    except Exception as e:
        logger.warning(f"Error searching JIRA comments: {e}")
        return []


def _search_jira_changelog_simple(terms: List[str], limit: int) -> List[Dict[str, Any]]:
    """Simple JIRA changelog search"""
    try:
        jira_data = load_jira_data()
        changelog_df = jira_data.get('changelog', pd.DataFrame())
        
        if changelog_df.empty:
            return []
        
        if not terms:
            return [row.to_dict() for _, row in changelog_df.head(limit).iterrows()]
        
        search_mask = pd.Series([False] * len(changelog_df))
        search_columns = ['field', 'fromString', 'toString', 'author']
        
        for term in terms:
            for col in search_columns:
                if col in changelog_df.columns:
                    mask = changelog_df[col].astype(str).str.contains(term, case=False, na=False)
                    search_mask = search_mask | mask
        
        filtered_df = changelog_df[search_mask].head(limit)
        return [row.to_dict() for _, row in filtered_df.iterrows()]
        
    except Exception as e:
        logger.warning(f"Error searching JIRA changelog: {e}")
        return []


def _analyze_results_for_answer(question: str, search_results: Dict[str, Any]) -> Dict[str, Any]:
    """Simple answer analysis from search results"""
    evidence = []
    confidence = 0.0
    
    # Analyze incidents (simplified)
    incidents = search_results["results"].get("incidents", [])
    for incident in incidents[:2]:  # Top 2 most relevant
        if incident.get("resolution"):
            evidence.append({
                "type": "incident",
                "id": incident.get("number"),
                "title": incident.get("short_description", ""),
                "resolution": incident.get("resolution", ""),
                "category": incident.get("category", "")
            })
            confidence += 0.3
    
    # Analyze JIRA issues (simplified)
    jira_issues = search_results["results"].get("jira_issues", [])
    for issue in jira_issues[:2]:  # Top 2 most relevant
        if issue.get("resolution.name"):
            evidence.append({
                "type": "jira_issue",
                "id": issue.get("key"),
                "title": issue.get("summary", ""),
                "resolution": issue.get("resolution.name", ""),
                "status": issue.get("status.name", "")
            })
            confidence += 0.3
    
    # Analyze comments (simplified)
    comments = search_results["results"].get("jira_comments", [])
    for comment in comments[:1]:  # Top 1 most relevant
        body_text = str(comment.get("comment.body", comment.get("body", "")))
        if len(body_text) > 30:
            evidence.append({
                "type": "jira_comment",
                "issue_key": comment.get("key", comment.get("issue", "")),
                "author": comment.get("comment.author", comment.get("author", "")),
                "content": body_text[:150] + "..." if len(body_text) > 150 else body_text
            })
            confidence += 0.2
    
    # Generate simple answer
    if evidence:
        answer = f"Based on historical data:\n\n"
        
        for i, item in enumerate(evidence, 1):
            if item["type"] == "incident":
                answer += f"{i}. **Incident {item['id']}**: {item['title']}\n"
                answer += f"   Resolution: {item['resolution']}\n\n"
            elif item["type"] == "jira_issue":
                answer += f"{i}. **JIRA Issue {item['id']}**: {item['title']}\n"
                answer += f"   Resolution: {item['resolution']}\n\n"
            elif item["type"] == "jira_comment":
                answer += f"{i}. **Comment**: {item['content']}\n\n"
    else:
        answer = "No specific solutions found in the knowledge base."
        confidence = 0.0
    
    return {
        "answer": answer,
        "confidence": min(confidence, 1.0),
        "evidence": evidence
    }


def _generate_simple_summary(results: Dict[str, Any]) -> str:
    """Generate simple summary of search results"""
    total = results["total_results"]
    
    if total == 0:
        return "No results found in the knowledge base."
    
    summary = f"Found {total} relevant items:\n"
    
    for source, items in results["results"].items():
        if items:
            summary += f"- {len(items)} {source.replace('_', ' ').title()}\n"
    
    return summary


def _analyze_incident_patterns_comprehensive() -> Dict[str, Any]:
    """Enhanced incident pattern analysis with proper date handling"""
    try:
        incidents_df = load_incident_data()
        if incidents_df.empty:
            return {
                "error": "No incident data available",
                "message": "The knowledge base contains no incident data to analyze patterns."
            }
        
        # Try to parse dates to get actual data range
        try:
            incidents_df['opened_at_dt'] = pd.to_datetime(incidents_df['opened_at'], format='%d/%m/%Y %H:%M', errors='coerce')
            valid_dates = incidents_df[incidents_df['opened_at_dt'].notna()]
            
            if not valid_dates.empty:
                start_date = valid_dates['opened_at_dt'].min()
                end_date = valid_dates['opened_at_dt'].max()
                date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                total_days = (end_date - start_date).days
            else:
                date_range = "Unable to determine date range"
                total_days = 0
        except Exception:
            date_range = "Unable to determine date range"
            total_days = 0
        
        # Basic pattern analysis
        patterns = {
            "total_incidents": len(incidents_df),
            "unique_incidents": incidents_df['number'].nunique(),
            "data_range": date_range,
            "total_days": total_days,
            "top_categories": incidents_df['category'].value_counts().head(10).to_dict() if 'category' in incidents_df.columns else {},
            "priority_distribution": incidents_df['priority'].value_counts().to_dict() if 'priority' in incidents_df.columns else {},
            "state_distribution": incidents_df['incident_state'].value_counts().to_dict() if 'incident_state' in incidents_df.columns else {},
            "message": f"Successfully analyzed {len(incidents_df)} incident records covering {total_days} days of historical data."
        }
        
        return patterns
        
    except Exception as e:
        logger.error(f"Error in incident pattern analysis: {e}")
        return {
            "error": str(e),
            "message": "An error occurred while analyzing incident patterns."
        }


def _analyze_jira_patterns_comprehensive() -> Dict[str, Any]:
    """Enhanced JIRA pattern analysis with proper date handling"""
    try:
        jira_data = load_jira_data()
        issues_df = jira_data.get('issues', pd.DataFrame())
        comments_df = jira_data.get('comments', pd.DataFrame())
        changelog_df = jira_data.get('changelog', pd.DataFrame())
        
        if issues_df.empty:
            return {
                "error": "No JIRA data available",
                "message": "The knowledge base contains no JIRA data to analyze patterns."
            }
        
        # Try to parse dates to get actual data range
        try:
            issues_df['created_dt'] = pd.to_datetime(issues_df['created'], errors='coerce')
            valid_dates = issues_df[issues_df['created_dt'].notna()]
            
            if not valid_dates.empty:
                start_date = valid_dates['created_dt'].min()
                end_date = valid_dates['created_dt'].max()
                date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                total_days = (end_date - start_date).days
            else:
                date_range = "Unable to determine date range"
                total_days = 0
        except Exception:
            date_range = "Unable to determine date range"
            total_days = 0
        
        # Basic pattern analysis
        patterns = {
            "total_issues": len(issues_df),
            "data_range": date_range,
            "total_days": total_days,
            "top_statuses": issues_df['status.name'].value_counts().head(10).to_dict() if 'status.name' in issues_df.columns else {},
            "top_priorities": issues_df['priority.name'].value_counts().head(10).to_dict() if 'priority.name' in issues_df.columns else {},
            "issue_types": issues_df['issuetype.name'].value_counts().to_dict() if 'issuetype.name' in issues_df.columns else {},
            "projects": issues_df['project.name'].value_counts().to_dict() if 'project.name' in issues_df.columns else {},
            "comments_count": len(comments_df),
            "changelog_count": len(changelog_df),
            "message": f"Successfully analyzed {len(issues_df)} JIRA issues, {len(comments_df)} comments, and {len(changelog_df)} changelog entries covering {total_days} days of historical data."
        }
        
        return patterns
        
    except Exception as e:
        logger.error(f"Error in JIRA pattern analysis: {e}")
        return {
            "error": str(e),
            "message": "An error occurred while analyzing JIRA patterns."
        } 