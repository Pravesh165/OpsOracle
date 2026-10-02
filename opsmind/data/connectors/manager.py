"""
Connector Manager for coordinating multiple real-time data connectors
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import logging

from .base import BaseConnector, DataRecord, ConnectorConfig

logger = logging.getLogger(__name__)

class ConnectorManager:
    """Manages multiple data connectors and aggregates their data"""
    
    def __init__(self):
        self.connectors: Dict[str, BaseConnector] = {}
        self.data_buffer: List[DataRecord] = []
        self.buffer_max_size = 1000
        self.data_callbacks: List[Callable[[List[DataRecord]], None]] = []
        self.error_callbacks: List[Callable[[str, Exception], None]] = []
        self._running = False
    
    def add_connector(self, connector: BaseConnector) -> None:
        """Add a connector to the manager"""
        if connector.config.name in self.connectors:
            logger.warning(f"Connector {connector.config.name} already exists, replacing")
        
        self.connectors[connector.config.name] = connector
        
        # Set up callbacks
        connector.add_data_callback(self._handle_connector_data)
        connector.add_error_callback(lambda e: self._handle_connector_error(connector.config.name, e))
        
        logger.info(f"Added connector: {connector.config.name}")
    
    def remove_connector(self, name: str) -> None:
        """Remove a connector from the manager"""
        if name in self.connectors:
            connector = self.connectors[name]
            asyncio.create_task(connector.stop())
            del self.connectors[name]
            logger.info(f"Removed connector: {name}")
    
    async def start_all(self) -> None:
        """Start all enabled connectors"""
        self._running = True
        
        start_tasks = []
        for connector in self.connectors.values():
            if connector.config.enabled:
                start_tasks.append(connector.start())
        
        if start_tasks:
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                connector_name = list(self.connectors.keys())[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to start connector {connector_name}: {result}")
                else:
                    logger.info(f"Started connector: {connector_name}")
    
    async def stop_all(self) -> None:
        """Stop all connectors"""
        self._running = False
        
        stop_tasks = []
        for connector in self.connectors.values():
            stop_tasks.append(connector.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
            logger.info("All connectors stopped")
    
    def _handle_connector_data(self, records: List[DataRecord]) -> None:
        """Handle data from connectors"""
        if not self._running:
            return
        
        # Add to buffer
        self.data_buffer.extend(records)
        
        # Trim buffer if it gets too large
        if len(self.data_buffer) > self.buffer_max_size:
            self.data_buffer = self.data_buffer[-self.buffer_max_size:]
        
        # Notify callbacks
        for callback in self.data_callbacks:
            try:
                callback(records)
            except Exception as e:
                logger.error(f"Error in data callback: {e}")
        
        logger.debug(f"Processed {len(records)} records, buffer size: {len(self.data_buffer)}")
    
    def _handle_connector_error(self, connector_name: str, error: Exception) -> None:
        """Handle connector errors"""
        logger.error(f"Connector {connector_name} error: {error}")
        
        for callback in self.error_callbacks:
            try:
                callback(connector_name, error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    def add_data_callback(self, callback: Callable[[List[DataRecord]], None]) -> None:
        """Add a callback for aggregated data"""
        self.data_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str, Exception], None]) -> None:
        """Add a callback for connector errors"""
        self.error_callbacks.append(callback)
    
    def get_recent_data(self, limit: int = 100, record_type: Optional[str] = None) -> List[DataRecord]:
        """Get recent data from the buffer"""
        filtered_data = self.data_buffer
        
        if record_type:
            filtered_data = [r for r in filtered_data if r.type == record_type]
        
        # Sort by timestamp (most recent first) and limit
        filtered_data.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered_data[:limit]
    
    def get_connector_status(self) -> Dict[str, Any]:
        """Get status of all connectors"""
        status = {}
        for name, connector in self.connectors.items():
            status[name] = connector.get_status()
        
        return {
            'connectors': status,
            'manager_running': self._running,
            'buffer_size': len(self.data_buffer),
            'total_connectors': len(self.connectors),
            'active_connectors': len([c for c in self.connectors.values() if c.status.value == 'running'])
        }
    
    def export_data(self, filename: Optional[str] = None) -> str:
        """Export buffer data to JSON"""
        if not filename:
            filename = f"connector_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'records': [record.to_dict() for record in self.data_buffer]
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Exported {len(self.data_buffer)} records to {filename}")
        return filename
    
    def clear_buffer(self) -> None:
        """Clear the data buffer"""
        buffer_size = len(self.data_buffer)
        self.data_buffer.clear()
        logger.info(f"Cleared buffer with {buffer_size} records") 