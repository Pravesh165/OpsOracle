"""
Postmortem generation tools for OpsMind
"""
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

from google.adk.tools.tool_context import ToolContext
from opsmind.config import OUTPUT_DIR, logger, GCP_STORAGE_ENABLED
from opsmind.utils import upload_file_to_gcp, generate_download_link, list_postmortem_files_in_gcp
from opsmind.tools.guardrail import with_guardrail

@with_guardrail
async def generate_postmortem_content(
    tool_context: ToolContext,
    incident_id: str
) -> Dict[str, str]:
    """Generate postmortem content based on incident and Jira data"""
    try:
        # Import here to avoid circular import
        from opsmind.context import get_incident_context
        
        # Get incident context data
        context_result = await get_incident_context(tool_context, incident_id)
        
        if context_result["status"] != "success":
            return {"status": "error", "message": f"Failed to get context for incident {incident_id}"}
        
        relevant_context = context_result["context"]
        
        # Find specific incident data
        incident_data = None
        for item in relevant_context:
            if item.get("type") == "incident" and item.get("id") == incident_id:
                incident_data = item
                break
        
        # Collect related Jira data
        jira_issues = [item for item in relevant_context if item.get("type") == "jira_issue"]
        jira_comments = [item for item in relevant_context if item.get("type") == "jira_comment"]
        jira_changelog = [item for item in relevant_context if item.get("type") == "jira_changelog"]
        jira_links = [item for item in relevant_context if item.get("type") == "jira_link"]
        
        # Generate postmortem content
        postmortem_content = f"""# Incident Postmortem: {incident_id}

## Executive Summary
This postmortem analyzes incident {incident_id} based on available incident data and related Jira information.

## Incident Details
- **Incident ID**: {incident_id}
- **Date/Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Status**: {incident_data.get('state', 'Unknown') if incident_data else 'Data not found'}
- **Category**: {incident_data.get('category', 'Unknown') if incident_data else 'Data not found'}
- **Priority**: {incident_data.get('priority', 'Unknown') if incident_data else 'Data not found'}
- **Description**: {incident_data.get('short_description', 'No description available') if incident_data else 'Data not found'}

## Root Cause Analysis
"""
        
        if incident_data:
            postmortem_content += f"""
Based on the incident data:
- **Symptom**: {incident_data.get('symptom', 'Not specified')}
- **Resolution Code**: {incident_data.get('resolution', 'Not specified')}
- **Full Description**: {incident_data.get('description', 'No detailed description available')}
"""
        else:
            postmortem_content += f"""
Incident {incident_id} was not found in the available incident data. This postmortem is based on related information from the system.
"""

        postmortem_content += f"""

## Related Jira Issues
"""
        if jira_issues:
            for issue in jira_issues[:5]:  # Limit to top 5 most relevant
                postmortem_content += f"""
### {issue.get('key', 'Unknown')}
- **Summary**: {issue.get('summary', 'No summary')}
- **Status**: {issue.get('status', 'Unknown')}
- **Priority**: {issue.get('priority', 'Unknown')}
- **Assignee**: {issue.get('assignee', 'Unassigned')}
- **Description**: {issue.get('description', 'No description')[:200]}...
"""
        else:
            postmortem_content += "\nNo directly related Jira issues found in the current dataset.\n"

        postmortem_content += f"""

## Jira Comments & Discussions
"""
        if jira_comments:
            for comment in jira_comments[:3]:  # Limit to top 3 most relevant
                postmortem_content += f"""
**Issue**: {comment.get('issue_key', 'Unknown')}  
**Author**: {comment.get('author', 'Unknown')}  
**Date**: {comment.get('created', 'Unknown')}  
**Comment**: {comment.get('body', 'No content')[:300]}...

"""
        else:
            postmortem_content += "\nNo related Jira comments found in the current dataset.\n"

        postmortem_content += f"""

## Timeline & Changes
"""
        if jira_changelog:
            postmortem_content += "\n**Key Status Changes from Jira:**\n"
            for change in jira_changelog[:5]:  # Limit to top 5 most relevant
                postmortem_content += f"""
- **{change.get('created', 'Unknown date')}**: {change.get('field', 'Field')} changed from "{change.get('from_string', 'N/A')}" to "{change.get('to_string', 'N/A')}" by {change.get('author', 'Unknown')}
"""
        else:
            postmortem_content += "\nNo Jira changelog data found for related issues.\n"

        postmortem_content += f"""

## Issue Relationships
"""
        if jira_links:
            postmortem_content += "\n**Related Issue Links:**\n"
            for link in jira_links[:3]:  # Limit to top 3
                postmortem_content += f"""
- {link.get('source_key', 'Unknown')} {link.get('link_type', 'relates to')} {link.get('target_key', 'Unknown')}
"""
        else:
            postmortem_content += "\nNo issue links found in the current dataset.\n"

        postmortem_content += f"""

## Lessons Learned
Based on the available data and analysis:
- Review incident categorization and symptom documentation
- Ensure proper linkage between incidents and Jira tracking
- Consider improving data collection for future postmortem analysis

## Action Items
1. **Data Quality**: Improve incident data collection and Jira integration
2. **Process Review**: Ensure all incidents have proper Jira ticket tracking
3. **Documentation**: Enhance incident description and symptom recording
4. **Monitoring**: Implement better incident-to-issue correlation

## Recommendations
- Establish clearer incident-to-Jira workflow processes
- Improve data consistency across incident and issue tracking systems
- Regular review of incident patterns and Jira issue resolution times

---
*This postmortem was automatically generated from available incident and Jira data on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}*
"""
        
        return {
            "status": "success",
            "incident_id": incident_id,
            "content": postmortem_content,
            "message": f"Generated postmortem content for incident {incident_id}"
        }
        
    except Exception as e:
        logger.error(f"Error generating postmortem content: {e}")
        return {"status": "error", "message": str(e)}

@with_guardrail
async def save_postmortem(
    tool_context: ToolContext,
    incident_id: str,
    postmortem_content: str
) -> Dict[str, Any]:
    """Save postmortem to GCP Cloud Storage and return download link"""
    try:
        filename = f"postmortem_{incident_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        if GCP_STORAGE_ENABLED:
            # Upload to GCP Cloud Storage
            upload_result = upload_file_to_gcp(
                file_content=postmortem_content,
                filename=filename,
                content_type="text/markdown"
            )
            
            if upload_result["status"] == "success":
                # Generate download link
                download_result = generate_download_link(
                    blob_path=upload_result["blob_path"],
                    expiration_hours=24
                )
                
                if download_result["status"] == "success":
                    logger.info(f"Saved postmortem to GCP Storage: {filename}")
                    return {
                        "status": "success",
                        "filename": filename,
                        "download_url": download_result["download_url"],
                        "download_expiration": download_result["expiration_time"],
                        "bucket_name": upload_result["bucket_name"],
                        "blob_path": upload_result["blob_path"],
                        "content": postmortem_content,
                        "message": f"Postmortem saved to GCP Storage and available for download"
                    }
                else:
                    logger.error(f"Failed to generate download link: {download_result['message']}")
                    return {
                        "status": "success",
                        "filename": filename,
                        "download_url": None,
                        "bucket_name": upload_result["bucket_name"],
                        "blob_path": upload_result["blob_path"],
                        "content": postmortem_content,
                        "message": f"Postmortem saved to GCP Storage but download link generation failed"
                    }
            else:
                logger.error(f"Failed to upload to GCP Storage: {upload_result['message']}")
                # Fallback to local storage
                return _save_postmortem_local(filename, postmortem_content)
        else:
            # GCP Storage disabled, use local storage
            return _save_postmortem_local(filename, postmortem_content)
            
    except Exception as e:
        logger.error(f"Error saving postmortem: {e}")
        return {"status": "error", "message": str(e)}

def _save_postmortem_local(filename: str, postmortem_content: str) -> Dict[str, Any]:
    """Fallback function to save postmortem locally"""
    try:
        output_dir = Path(OUTPUT_DIR)
        output_dir.mkdir(exist_ok=True)
        
        filepath = output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(postmortem_content)
        
        logger.info(f"Saved postmortem locally to {filepath}")
        return {
            "status": "success", 
            "filepath": str(filepath),
            "filename": filename,
            "download_url": None,
            "content": postmortem_content,
            "message": f"Postmortem saved locally to {filename} (GCP Storage unavailable)"
        }
    except Exception as e:
        logger.error(f"Error saving postmortem locally: {e}")
        return {"status": "error", "message": str(e)}

@with_guardrail
async def list_postmortem_files(
    tool_context: ToolContext,
    show_content: bool = False
) -> Dict[str, Any]:
    """List existing postmortem files from GCP storage (and local as fallback)"""
    try:
        if GCP_STORAGE_ENABLED:
            # List files from GCP Storage
            gcp_result = list_postmortem_files_in_gcp()
            
            if gcp_result["status"] == "success":
                files_info = gcp_result["files"]
                
                # If show_content is requested, fetch content for each file
                if show_content:
                    from opsmind.utils import get_file_content_from_gcp
                    for file_info in files_info:
                        content_result = get_file_content_from_gcp(file_info["blob_path"])
                        if content_result["status"] == "success":
                            file_info["content"] = content_result["content"]
                        else:
                            file_info["content"] = f"Error loading content: {content_result['message']}"
                
                # Generate download links for each file
                for file_info in files_info:
                    download_result = generate_download_link(
                        blob_path=file_info["blob_path"],
                        expiration_hours=24
                    )
                    if download_result["status"] == "success":
                        file_info["download_url"] = download_result["download_url"]
                        file_info["download_expiration"] = download_result["expiration_time"]
                    else:
                        file_info["download_url"] = None
                        file_info["download_error"] = download_result["message"]
                
                return {
                    "status": "success",
                    "files": files_info,
                    "count": len(files_info),
                    "source": "gcp_storage",
                    "bucket_name": gcp_result.get("bucket_name"),
                    "message": f"Found {len(files_info)} postmortem files in GCP Storage"
                }
            else:
                logger.warning(f"Failed to list GCP files: {gcp_result['message']}")
                # Fallback to local storage
                return _list_postmortem_files_local(show_content)
        else:
            # GCP Storage disabled, use local storage
            return _list_postmortem_files_local(show_content)
            
    except Exception as e:
        logger.error(f"Error listing postmortem files: {e}")
        return {"status": "error", "message": str(e)}

def _list_postmortem_files_local(show_content: bool = False) -> Dict[str, Any]:
    """Fallback function to list postmortem files locally"""
    try:
        output_dir = Path(OUTPUT_DIR)
        if not output_dir.exists():
            return {"status": "success", "files": [], "message": "No postmortem files found - output directory doesn't exist yet"}
        
        postmortem_files = list(output_dir.glob("postmortem_*.md"))
        files_info = []
        
        for filepath in sorted(postmortem_files, key=lambda x: x.stat().st_mtime, reverse=True):
            file_info = {
                "filename": filepath.name,
                "filepath": str(filepath),
                "size": filepath.stat().st_size,
                "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                "download_url": None  # No download URL for local files
            }
            
            if show_content:
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_info["content"] = f.read()
            
            files_info.append(file_info)
        
        return {
            "status": "success",
            "files": files_info,
            "count": len(files_info),
            "source": "local_storage",
            "message": f"Found {len(files_info)} postmortem files locally (GCP Storage unavailable)"
        }
    except Exception as e:
        logger.error(f"Error listing local postmortem files: {e}")
        return {"status": "error", "message": str(e)} 