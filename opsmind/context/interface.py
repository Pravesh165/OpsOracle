"""
Context Management Tools - Unified interface for data access

Provides a clean interface for tools to access data without 
needing to know about the underlying data sources.
"""

from typing import Any, Dict, List, Optional
from google.adk.tools.tool_context import ToolContext
from opsmind.data.manager import get_manager, SourceType
from opsmind.data.connectors import ConnectorConfig
from opsmind.data.connectors.jira import create_jira_connector
from opsmind.config import logger, get_jira_config
from opsmind.config.settings import PRESETS


def get_context(
    tool_context: ToolContext,
    query: str,
    limit: int = 15
) -> Dict[str, Any]:
    """
    Get context from all configured data sources
    
    Works with CSV files, real-time streams, and future sources.
    Automatically falls back to CSV-only if streams unavailable.
    """
    try:
        manager = get_manager()
        
        # Auto-initialize with CSV if not running
        if not manager._running:
            logger.info("Auto-initializing with CSV sources...")
            
            manager.add_csv("incidents", SourceType.INCIDENTS_CSV)
            manager.add_csv("jira", SourceType.JIRA_CSV)
            
            # Try to add Jira real-time connector if configured
            jira_connector = create_jira_connector()
            if jira_connector:
                config = ConnectorConfig(
                    name="jira_realtime",
                    connector_type="jira",
                    **get_jira_config()
                )
                manager.add_jira_stream(config)
                logger.info("Added Jira real-time connector")
            
            # Try async start
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(manager.start())
                    logger.info("Started manager in background")
                else:
                    asyncio.run(manager.start())
            except Exception as e:
                logger.error(f"Could not start manager: {e}")
                return {"status": "error", "message": f"Failed to initialize data sources: {e}"}
        
        result = manager.query(query, limit=limit)
        
        if result["status"] == "success":
            logger.info(f"Retrieved {len(result['context'])} items from {len(result['active_sources'])} sources")
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        return {"status": "error", "message": str(e)}

def configure(
    csv_incidents: bool = True,
    csv_jira: bool = True,
    jira_stream: bool = False,
    jira_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Configure data sources
    
    Args:
        csv_incidents: Enable incident CSV
        csv_jira: Enable JIRA CSV  
        jira_stream: Enable real-time JIRA
        jira_config: JIRA connector config (optional, uses env vars if not provided)
    """
    try:
        manager = get_manager()
        
        if csv_incidents:
            manager.add_csv("incidents", SourceType.INCIDENTS_CSV)
        
        if csv_jira:
            manager.add_csv("jira", SourceType.JIRA_CSV)
        
        if jira_stream:
            # Use factory function to create connector
            jira_connector = create_jira_connector("jira_stream", **(jira_config or {}))
            if jira_connector:
                config = ConnectorConfig(
                    name="jira_stream",
                    connector_type="jira",
                    **get_jira_config()
                )
                manager.add_jira_stream(config)
            else:
                logger.warning("Could not create Jira connector - check configuration")
        
        return {
            "status": "success",
            "message": "Sources configured",
            "sources": manager.status()
        }
        
    except Exception as e:
        logger.error(f"Error configuring sources: {e}")
        return {"status": "error", "message": str(e)}

def info() -> Dict[str, Any]:
    """Get data sources info"""
    try:
        manager = get_manager()
        return manager.status()
    except Exception as e:
        return {"error": str(e)}


def preset(name: str, jira_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply a preset configuration"""
    if name not in PRESETS:
        return {"status": "error", "message": f"Unknown preset: {name}. Available: {list(PRESETS.keys())}"}
    
    config = PRESETS[name]["config"].copy()
    if jira_config:
        config["jira_config"] = jira_config
    
    return configure(**config) 