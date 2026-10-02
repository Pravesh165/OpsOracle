"""Context and RAG tools for OpsMind"""

import pandas as pd
from typing import Any, Dict

import numpy as np
from google.adk.tools.tool_context import ToolContext

from opsmind.config import logger
from opsmind.data import load_incident_data, load_jira_data
from opsmind.utils import safe_get
from opsmind.tools.guardrail import with_guardrail


@with_guardrail
async def get_incident_context(
    tool_context: ToolContext,
    query: str
) -> Dict[str, Any]:
    """Get incident context for RAG-based queries with enhanced Jira data"""
    try:
        # Load data if not already in state
        if "incident_memory" not in tool_context.state:
            incident_df = load_incident_data()
            jira_data = load_jira_data()

            # Create simple context from incident data
            incident_context = []
            for _, row in incident_df.head(100).iterrows():  # Limit for MVP
                context_entry = {
                    "type": "incident",
                    "id": safe_get(row, "number"),
                    "state": safe_get(row, "incident_state"),
                    "category": safe_get(row, "category"),
                    "symptom": safe_get(row, "u_symptom"),
                    "priority": safe_get(row, "priority"),
                    "resolution": safe_get(row, "closed_code"),
                    "short_description": safe_get(row, "short_description"),
                    "description": safe_get(row, "description")
                }
                incident_context.append(context_entry)

            # Enhanced Jira context with multiple data sources
            jira_context = []

            # Process Jira issues
            issues_df = jira_data.get('issues', pd.DataFrame())
            for _, row in issues_df.head(100).iterrows():  # Limit for MVP
                context_entry = {
                    "type": "jira_issue",
                    "key": safe_get(row, "key"),
                    "summary": safe_get(row, "summary"),
                    "priority": safe_get(row, "priority.name"),
                    "status": safe_get(row, "status.name"),
                    "resolution": safe_get(row, "resolution.description"),
                    "description": safe_get(row, "description"),
                    "assignee": safe_get(row, "assignee.displayName"),
                    "reporter": safe_get(row, "reporter.displayName"),
                    "created": safe_get(row, "created"),
                    "updated": safe_get(row, "updated")
                }
                jira_context.append(context_entry)

            # Process Jira comments
            comments_df = jira_data.get('comments', pd.DataFrame())
            for _, row in comments_df.head(50).iterrows():  # Limit comments
                context_entry = {
                    "type": "jira_comment",
                    "issue_key": safe_get(row, "issue_key"),
                    "author": safe_get(row, "author.displayName"),
                    "body": safe_get(row, "body"),
                    "created": safe_get(row, "created"),
                    "updated": safe_get(row, "updated")
                }
                jira_context.append(context_entry)

            # Process Jira changelog
            changelog_df = jira_data.get('changelog', pd.DataFrame())
            for _, row in changelog_df.head(50).iterrows():  # Limit changelog
                context_entry = {
                    "type": "jira_changelog",
                    "issue_key": safe_get(row, "issue_key"),
                    "author": safe_get(row, "author.displayName"),
                    "field": safe_get(row, "field"),
                    "from_string": safe_get(row, "fromString"),
                    "to_string": safe_get(row, "toString"),
                    "created": safe_get(row, "created")
                }
                jira_context.append(context_entry)

            # Process Jira issue links
            issuelinks_df = jira_data.get('issuelinks', pd.DataFrame())
            for _, row in issuelinks_df.head(50).iterrows():  # Limit links
                context_entry = {
                    "type": "jira_link",
                    "source_key": safe_get(row, "sourceIssueKey"),
                    "target_key": safe_get(row, "targetIssueKey"),
                    "link_type": safe_get(row, "linkType.name"),
                    "direction": safe_get(row, "linkType.inward")
                }
                jira_context.append(context_entry)

            # Combine all context
            all_context = incident_context + jira_context
            tool_context.state["incident_memory"] = all_context
            logger.info("Loaded %s incidents and %s Jira items into memory", len(incident_context), len(jira_context))

        # Enhanced context search based on query keywords
        context = tool_context.state["incident_memory"]
        relevant_context = []

        query_lower = query.lower()
        query_keywords = query_lower.split()

        for item in context:
            item_text = str(item).lower()
            # Score relevance based on keyword matches
            matches = sum(1 for keyword in query_keywords if keyword in item_text)
            if matches > 0:
                item_with_score = item.copy()
                item_with_score["relevance_score"] = matches
                relevant_context.append(item_with_score)

        # Sort by relevance score and return top results
        relevant_context.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        return {
            "status": "success",
            "context": relevant_context[:15],  # Return top 15 most relevant items
            "total_found": len(relevant_context),
            "jira_enabled": True,
            "data_sources": ["incidents", "jira_issues", "jira_comments", "jira_changelog", "jira_links"]
        }
    except Exception as e:
        logger.error("Error getting incident context: %s", e)
        return {"status": "error", "message": str(e)}
