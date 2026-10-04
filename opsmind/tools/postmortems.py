"""
Postmortem generation tools for OpsMind
"""
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from google.adk.tools.tool_context import ToolContext
from opsmind.config import OUTPUT_DIR, logger, GCP_STORAGE_ENABLED
from opsmind.utils import upload_file_to_gcp, generate_download_link, list_postmortem_files_in_gcp
from opsmind.tools.guardrail import with_guardrail
from opsmind.tools.rca import (
    generate_rca,
    format_citations,
    extract_action_items,
    extract_lessons_learned,
)


@with_guardrail
async def generate_postmortem_content(
    tool_context: ToolContext,
    incident_id: str
) -> Dict[str, str]:
    """Generate LLM-grounded postmortem content with evidence citations."""
    try:
        from opsmind.context import get_incident_context

        context_result = await get_incident_context(tool_context, incident_id)
        if context_result["status"] != "success":
            return {"status": "error", "message": f"Failed to get context for incident {incident_id}"}

        relevant_context = context_result["context"]

        # Locate the specific incident record
        incident_data = next(
            (item for item in relevant_context
             if item.get("type") == "incident" and item.get("id") == incident_id),
            None,
        )

        # Partition evidence by type
        evidence_chunks: List[Dict[str, Any]] = [
            item for item in relevant_context
            if item.get("citation_id") or item.get("similarity_score")
        ]
        jira_issues = [i for i in relevant_context if i.get("type") == "jira_issue"]
        jira_comments = [i for i in relevant_context if i.get("type") == "jira_comment"]
        jira_changelog = [i for i in relevant_context if i.get("type") == "jira_changelog"]

        # Pull triage result from session state if available
        triage_result = (
            tool_context.state.get("incident_states", {}).get(incident_id)
        )

        # --- LLM-grounded RCA ---
        rca_result = generate_rca(
            incident_id=incident_id,
            evidence_chunks=evidence_chunks,
            triage_result=triage_result,
            incident_data=incident_data,
        )

        # --- Citation rendering ---
        all_citations = format_citations(evidence_chunks)
        rca_citations = format_citations(
            [{"citation_id": eid} for eid in rca_result.get("evidence_ids", [])]
        )

        # --- Dynamic action items + lessons ---
        similar_resolutions = [
            str(i.get("resolution") or i.get("resolution.name") or "")
            for i in jira_issues[:5]
        ]
        action_items = extract_action_items(rca_result, similar_resolutions)
        lessons = extract_lessons_learned(rca_result, incident_data)

        # --- Assemble markdown ---
        inc = incident_data or {}
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Triage block
        triage_block = ""
        if triage_result:
            triage_block = (
                f"- **Severity**: {triage_result.get('severity', 'N/A')} "
                f"({triage_result.get('urgency', 'N/A')})\n"
                f"- **Impact**: {triage_result.get('impact', 'N/A')}\n"
                f"- **Affected Service**: {triage_result.get('affected_service', 'N/A')}\n"
                f"- **Suggested Team**: {triage_result.get('suggested_team', 'N/A')}\n"
            )

        # Contributing factors block
        factors_block = ""
        for cf in rca_result.get("contributing_factors", [])[:4]:
            if isinstance(cf, dict):
                eid = cf.get("evidence_id", "")
                cite = f" [{eid}]" if eid else ""
                factors_block += f"- {cf.get('factor', '')} (confidence: {cf.get('confidence', 0):.0%}){cite}\n"
            elif isinstance(cf, str):
                factors_block += f"- {cf}\n"

        # Related Jira issues block
        jira_block = ""
        for issue in jira_issues[:5]:
            cid = issue.get("citation_id", "")
            cite = f" [{cid}]" if cid else ""
            jira_block += (
                f"### {issue.get('key', issue.get('id', 'Unknown'))}{cite}\n"
                f"- **Summary**: {issue.get('summary', 'No summary')}\n"
                f"- **Status**: {issue.get('status', issue.get('status.name', 'Unknown'))}\n"
                f"- **Priority**: {issue.get('priority', issue.get('priority.name', 'Unknown'))}\n\n"
            )
        if not jira_block:
            jira_block = "No directly related Jira issues found.\n"

        # Timeline block
        timeline_block = ""
        for change in jira_changelog[:5]:
            timeline_block += (
                f"- **{change.get('created', '?')}**: "
                f"{change.get('field', 'field')} changed "
                f"from \"{change.get('from_string', 'N/A')}\" "
                f"to \"{change.get('to_string', 'N/A')}\" "
                f"by {change.get('author', 'Unknown')}\n"
            )
        if not timeline_block:
            timeline_block = "No changelog data found.\n"

        # Action items block
        actions_block = "".join(f"{i+1}. {a}\n" for i, a in enumerate(action_items))

        # Lessons block
        lessons_block = "".join(f"- {l}\n" for l in lessons)

        postmortem_content = f"""# Incident Postmortem: {incident_id}

## Executive Summary
This postmortem analyzes incident {incident_id} using evidence-grounded root cause analysis.
RCA confidence: **{rca_result['confidence']:.0%}**. Evidence sources: {all_citations or 'keyword search'}

## Incident Details
- **Incident ID**: {incident_id}
- **Date/Time**: {inc.get('opened_at', now)}
- **Status**: {inc.get('state', 'Unknown')}
- **Category**: {inc.get('category', 'Unknown')}
- **Priority**: {inc.get('priority', 'Unknown')}
- **Description**: {inc.get('short_description', inc.get('symptom', 'No description available'))}
{triage_block}
## Root Cause Analysis

**Root Cause**: {rca_result['root_cause']} {rca_citations}

### Contributing Factors
{factors_block or 'No contributing factors identified.\n'}

## Related Jira Issues
{jira_block}
## Timeline & Changes
{timeline_block}
## Lessons Learned
{lessons_block}
## Action Items
{actions_block}
---
*Generated by OpsMind on {now}*
"""

        return {
            "status": "success",
            "incident_id": incident_id,
            "content": postmortem_content,
            "rca": rca_result,
            "citations": all_citations,
            "message": f"Generated postmortem for incident {incident_id} "
                        f"(RCA confidence {rca_result['confidence']:.0%})",
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