"""Real-time Context Manager - Handles live data streams

Manages real-time data connectors and provides unified context updates
for the RAG system.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from opsmind.config import logger
from opsmind.data.connectors import (ConnectorConfig, ConnectorManager,
                                     DataRecord, JiraConnector)
from opsmind.data.connectors.jira import create_jira_connector


class RealTimeContextManager:
    """Manages real-time data connectors and aggregates their data"""
    
    def __init__(self):
        self.connector_manager = ConnectorManager()
        self.context_buffer: List[Dict[str, Any]] = []
        self.max_context_size = 1000
        self.callbacks: List[Callable[[List[Dict[str, Any]]], None]] = []

        # Set up connector manager callbacks
        self.connector_manager.add_data_callback(self._process_data)
        self.connector_manager.add_error_callback(self._handle_error)

    def add_jira_connector(self, config: ConnectorConfig) -> None:
        """Add JIRA connector using environment configuration"""
        
        try:
            # Use factory function to create properly configured connector
            jira_connector = create_jira_connector(config.name)
            if jira_connector:
                self.connector_manager.add_connector(jira_connector)
                logger.info("Added JIRA connector: %s", config.name)
            else:
                logger.warning("Could not create JIRA connector: %s", config.name)
        except Exception as e:
            logger.error("Failed to add JIRA connector: %s", e)
            raise

    def _process_data(self, records: List[DataRecord]) -> None:
        """Convert connector data to context format"""
        
        try:
            items = []

            for record in records:
                item = self._record_to_context(record)
                if item:
                    items.append(item)

            self.context_buffer.extend(items)

            if len(self.context_buffer) > self.max_context_size:
                self.context_buffer = self.context_buffer[-self.max_context_size:]

            for callback in self.callbacks:
                try:
                    callback(items)
                except Exception as e:
                    logger.error("Error in callback: %s", e)

            logger.debug("Processed %s real-time records", len(items))

        except Exception as e:
            logger.error("Error processing real-time data: %s", e)

    def _handle_error(self, connector_name: str, error: Exception) -> None:
        """Handle connector errors"""
        
        logger.error("Real-time connector %s error: %s", connector_name, error)

    def _record_to_context(self, record: DataRecord) -> Optional[Dict[str, Any]]:
        """Convert DataRecord to context item"""
        
        try:
            base_item = {
                "id": record.id,
                "source": record.source,
                "timestamp": record.timestamp.isoformat(),
                "metadata": record.metadata
            }

            if record.type == "issue":
                return {
                    **base_item,
                    "type": "jira_issue",
                    "key": record.data.get("key", ""),
                    "summary": record.data.get("summary", ""),
                    "description": record.data.get("description", ""),
                    "status": record.data.get("status", ""),
                    "priority": record.data.get("priority", ""),
                    "assignee": record.data.get("assignee", ""),
                    "reporter": record.data.get("reporter", ""),
                    "jira_url": record.metadata.get("jira_url", ""),
                    "content": f"{record.data.get('summary', '')} {record.data.get('description', '')}"
                }

            elif record.type == "comment":
                return {
                    **base_item,
                    "type": "jira_comment",
                    "issue_key": record.data.get("issue_key", ""),
                    "author": record.data.get("author", ""),
                    "body": record.data.get("body", ""),
                    "created": record.data.get("created", ""),
                    "jira_url": record.metadata.get("jira_url", ""),
                    "content": record.data.get("body", "")
                }

            elif record.type == "changelog":
                return {
                    **base_item,
                    "type": "jira_changelog",
                    "issue_key": record.data.get("issue_key", ""),
                    "field": record.data.get("field", ""),
                    "from_string": record.data.get("from_string", ""),
                    "to_string": record.data.get("to_string", ""),
                    "author": record.data.get("author", ""),
                    "created": record.data.get("created", ""),
                    "jira_url": record.metadata.get("jira_url", ""),
                    "content": f"Field {record.data.get('field', '')} changed from {record.data.get('from_string', '')} to {record.data.get('to_string', '')}"
                }

            elif record.type == "worklog":
                return {
                    **base_item,
                    "type": "jira_worklog",
                    "issue_key": record.data.get("issue_key", ""),
                    "author": record.data.get("author", ""),
                    "time_spent": record.data.get("time_spent", ""),
                    "comment": record.data.get("comment", ""),
                    "created": record.data.get("created", ""),
                    "jira_url": record.metadata.get("jira_url", ""),
                    "content": f"Work logged: {record.data.get('time_spent', '')} - {record.data.get('comment', '')}"
                }

            return None

        except Exception as e:
            logger.error("Error converting record: %s", e)
            return None

    async def start(self) -> None:
        """Start real-time manager"""
        
        try:
            await self.connector_manager.start_all()
            logger.info("Real-time manager started")
        except Exception as e:
            logger.error("Failed to start real-time manager: %s", e)
            raise

    async def stop(self) -> None:
        """Stop real-time manager"""
        
        try:
            await self.connector_manager.stop_all()
            logger.info("Real-time manager stopped")
        except Exception as e:
            logger.error("Error stopping real-time manager: %s", e)

    def get_recent_context(self, limit: int = 50, context_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent context items"""
        
        filtered = self.context_buffer

        if context_type:
            filtered = [item for item in filtered if item.get("type") == context_type]

        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return filtered[:limit]

    def add_update_callback(self, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Add callback for updates"""
        
        self.callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get status"""
        
        return {
            "connector_status": self.connector_manager.get_connector_status(),
            "context_buffer_size": len(self.context_buffer),
            "max_context_size": self.max_context_size,
            "callbacks_count": len(self.callbacks)
        }
