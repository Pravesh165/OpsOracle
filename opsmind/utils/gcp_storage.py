"""
GCP Cloud Storage utilities for OpsMind
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError
from opsmind.config import (
    GCP_BUCKET_NAME, 
    GCP_PROJECT_ID, 
    GCP_STORAGE_ENABLED,
    GCP_POSTMORTEM_FOLDER,
    GCP_FILE_EXPIRATION_DAYS,
    logger
)

def get_storage_client() -> Optional[storage.Client]:
    """Get authenticated GCP Storage client"""
    try:
        if GCP_PROJECT_ID:
            client = storage.Client(project=GCP_PROJECT_ID)
        else:
            # Use default project from environment
            client = storage.Client()
        return client
    except Exception as e:
        logger.error(f"Failed to create GCP Storage client: {e}")
        return None

def upload_file_to_gcp(
    file_content: str,
    filename: str,
    content_type: str = "text/markdown"
) -> Dict[str, Any]:
    """Upload file content to GCP Cloud Storage"""
    if not GCP_STORAGE_ENABLED:
        return {
            "status": "error",
            "message": "GCP Storage is not enabled"
        }
    
    try:
        client = get_storage_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to create GCP Storage client"
            }
        
        # Get bucket
        try:
            bucket = client.bucket(GCP_BUCKET_NAME)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to access bucket {GCP_BUCKET_NAME}: {e}"
            }
        
        # Create blob path
        blob_path = f"{GCP_POSTMORTEM_FOLDER}/{filename}"
        blob = bucket.blob(blob_path)
        
        # Set metadata
        blob.metadata = {
            "uploaded_by": "opsmind",
            "upload_time": datetime.now().isoformat(),
            "content_type": content_type
        }
        
        # Upload content
        blob.upload_from_string(
            file_content,
            content_type=content_type
        )
        
        logger.info(f"Successfully uploaded {filename} to GCP Storage")
        
        return {
            "status": "success",
            "bucket_name": GCP_BUCKET_NAME,
            "blob_path": blob_path,
            "filename": filename,
            "size": len(file_content),
            "upload_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to upload file to GCP Storage: {e}")
        return {
            "status": "error",
            "message": f"Upload failed: {str(e)}"
        }

def generate_download_link(
    blob_path: str,
    expiration_hours: int = 24
) -> Dict[str, Any]:
    """Generate a signed download URL for the file"""
    if not GCP_STORAGE_ENABLED:
        return {
            "status": "error",
            "message": "GCP Storage is not enabled"
        }
    
    try:
        client = get_storage_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to create GCP Storage client"
            }
        
        bucket = client.bucket(GCP_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        
        # Generate signed URL
        expiration_time = datetime.now() + timedelta(hours=expiration_hours)
        
        download_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        return {
            "status": "success",
            "download_url": download_url,
            "expiration_time": expiration_time.isoformat(),
            "expiration_hours": expiration_hours
        }
        
    except Exception as e:
        logger.error(f"Failed to generate download link: {e}")
        return {
            "status": "error",
            "message": f"Download link generation failed: {str(e)}"
        }

def list_postmortem_files_in_gcp() -> Dict[str, Any]:
    """List all postmortem files in GCP Storage"""
    if not GCP_STORAGE_ENABLED:
        return {
            "status": "error",
            "message": "GCP Storage is not enabled"
        }
    
    try:
        client = get_storage_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to create GCP Storage client"
            }
        
        bucket = client.bucket(GCP_BUCKET_NAME)
        
        # List blobs with the postmortem prefix
        blobs = bucket.list_blobs(prefix=f"{GCP_POSTMORTEM_FOLDER}/")
        
        files_info = []
        for blob in blobs:
            # Skip directory markers
            if blob.name.endswith('/'):
                continue
                
            file_info = {
                "filename": blob.name.split('/')[-1],
                "blob_path": blob.name,
                "size": blob.size,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "updated": blob.updated.isoformat() if blob.updated else None,
                "content_type": blob.content_type
            }
            files_info.append(file_info)
        
        # Sort by creation time (newest first)
        files_info.sort(key=lambda x: x['created'] or '', reverse=True)
        
        return {
            "status": "success",
            "files": files_info,
            "count": len(files_info),
            "bucket_name": GCP_BUCKET_NAME
        }
        
    except Exception as e:
        logger.error(f"Failed to list files in GCP Storage: {e}")
        return {
            "status": "error",
            "message": f"File listing failed: {str(e)}"
        }

def delete_file_from_gcp(blob_path: str) -> Dict[str, Any]:
    """Delete a file from GCP Storage"""
    if not GCP_STORAGE_ENABLED:
        return {
            "status": "error",
            "message": "GCP Storage is not enabled"
        }
    
    try:
        client = get_storage_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to create GCP Storage client"
            }
        
        bucket = client.bucket(GCP_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        
        # Check if file exists
        if not blob.exists():
            return {
                "status": "error",
                "message": f"File not found: {blob_path}"
            }
        
        # Delete the file
        blob.delete()
        
        logger.info(f"Successfully deleted {blob_path} from GCP Storage")
        
        return {
            "status": "success",
            "message": f"File {blob_path} deleted successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to delete file from GCP Storage: {e}")
        return {
            "status": "error",
            "message": f"Delete failed: {str(e)}"
        }

def get_file_content_from_gcp(blob_path: str) -> Dict[str, Any]:
    """Get file content from GCP Storage"""
    if not GCP_STORAGE_ENABLED:
        return {
            "status": "error",
            "message": "GCP Storage is not enabled"
        }
    
    try:
        client = get_storage_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to create GCP Storage client"
            }
        
        bucket = client.bucket(GCP_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        
        # Check if file exists
        if not blob.exists():
            return {
                "status": "error",
                "message": f"File not found: {blob_path}"
            }
        
        # Download content
        content = blob.download_as_text()
        
        return {
            "status": "success",
            "content": content,
            "filename": blob_path.split('/')[-1],
            "size": blob.size,
            "content_type": blob.content_type
        }
        
    except Exception as e:
        logger.error(f"Failed to get file content from GCP Storage: {e}")
        return {
            "status": "error",
            "message": f"Content retrieval failed: {str(e)}"
        } 