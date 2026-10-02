"""
Data Manager - Plug and Play data sources for OpsMind RAG

Mix and match data sources: CSV files, real-time connectors, etc.
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from opsmind.data.loader import load_incident_data, load_jira_data
from opsmind.data.connectors import ConnectorManager, JiraConnector, ConnectorConfig, DataRecord
from opsmind.config import logger
from opsmind.utils import safe_get
from opsmind.context import RealTimeContextManager



class SourceType(Enum):
    """Data source types"""
    CSV_STATIC = "csv_static"
    JIRA_REALTIME = "jira_realtime"
    JIRA_CSV = "jira_csv"
    INCIDENTS_CSV = "incidents_csv"

@dataclass
class SourceConfig:
    """Data source configuration"""
    name: str
    type: SourceType
    enabled: bool = True
    priority: int = 1
    config_params: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)

class DataManager:
    """
    Unified data manager for all sources
    
    Usage:
        manager = DataManager()
        manager.add_csv("incidents", SourceType.INCIDENTS_CSV)
        manager.add_jira_stream(jira_config)
        await manager.start()
        context = manager.query("database issues")
    """
    
    def __init__(self):
        self.sources: Dict[str, SourceConfig] = {}
        self.csv_cache: Dict[str, Any] = {}
        self.realtime_manager: Optional["RealTimeContextManager"] = None
        self.context: List[Dict[str, Any]] = []
        self.max_context_size = 1000
        self.callbacks: List[Callable[[List[Dict[str, Any]]], None]] = []
        self._running = False
        
    def add_csv(self, name: str, source_type: SourceType, **kwargs) -> None:
        """Add CSV data source"""
        config = SourceConfig(
            name=name,
            type=source_type,
            enabled=kwargs.get('enabled', True),
            priority=kwargs.get('priority', 1),
            config_params=kwargs.get('config_params', {}),
            filters=kwargs.get('filters', {})
        )
        
        self.sources[name] = config
        logger.info(f"Added CSV source: {name}")
        
    def add_jira_stream(self, connector_config: ConnectorConfig, **kwargs) -> None:
        """Add real-time JIRA stream"""
        config = SourceConfig(
            name=connector_config.name,
            type=SourceType.JIRA_REALTIME,
            enabled=kwargs.get('enabled', True),
            priority=kwargs.get('priority', 2),
            config_params={'connector_config': connector_config},
            filters=kwargs.get('filters', {})
        )
        
        self.sources[connector_config.name] = config
        logger.info(f"Added JIRA stream: {connector_config.name}")
        
    async def start(self) -> None:
        """Start all enabled sources"""
        try:
            self._running = True
            await self._load_csv_sources()
            await self._start_streams()
            self._build_context()
            logger.info(f"Started data manager with {len(self.sources)} sources")
        except Exception as e:
            logger.error(f"Failed to start data manager: {e}")
            self._running = False
            raise
    
    async def stop(self) -> None:
        """Stop all sources"""
        try:
            self._running = False
            if self.realtime_manager:
                await self.realtime_manager.stop()
            logger.info("Stopped data manager")
        except Exception as e:
            logger.error(f"Error stopping data manager: {e}")
    
    async def _load_csv_sources(self) -> None:
        """Load CSV sources"""
        for name, config in self.sources.items():
            if not config.enabled:
                continue
                
            try:
                if config.type == SourceType.INCIDENTS_CSV:
                    self.csv_cache[name] = load_incident_data()
                    logger.info(f"Loaded incidents: {len(self.csv_cache[name])} records")
                    
                elif config.type == SourceType.JIRA_CSV:
                    self.csv_cache[name] = load_jira_data()
                    total = sum(len(df) for df in self.csv_cache[name].values())
                    logger.info(f"Loaded JIRA CSV: {total} records")
                    
            except Exception as e:
                logger.error(f"Failed to load CSV {name}: {e}")
    
    async def _start_streams(self) -> None:
        """Start real-time streams"""
        streams = [
            (name, config) for name, config in self.sources.items() 
            if config.enabled and config.type == SourceType.JIRA_REALTIME
        ]
        
        if not streams:
            return
            
        self.realtime_manager = RealTimeContextManager()
        
        for name, config in streams:
            try:
                connector_config = config.config_params['connector_config']
                self.realtime_manager.add_jira_connector(connector_config)
            except Exception as e:
                logger.error(f"Failed to add stream {name}: {e}")
        
        self.realtime_manager.add_update_callback(self._handle_stream_update)
        await self.realtime_manager.start()
        
    def _handle_stream_update(self, new_context: List[Dict[str, Any]]) -> None:
        """Handle real-time updates"""
        try:
            self.context.extend(new_context)
            
            if len(self.context) > self.max_context_size:
                self.context = self.context[-self.max_context_size:]
            
            for callback in self.callbacks:
                try:
                    callback(new_context)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling stream update: {e}")
    
    def _build_context(self) -> None:
        """Build context from CSV sources"""
        try:
            csv_context = []
            
            # Process incidents
            self._process_incident_csv(csv_context)
            
            # Process JIRA CSV
            self._process_jira_csv(csv_context)
            
            self.context.extend(csv_context)
            logger.info(f"Built context with {len(csv_context)} CSV items")
            
        except Exception as e:
            logger.error(f"Error building context: {e}")
    
    def _process_incident_csv(self, csv_context: List[Dict[str, Any]]) -> None:
        """Process incident CSV data"""
        for name, config in self.sources.items():
            if not config.enabled or config.type != SourceType.INCIDENTS_CSV:
                continue
                
            df = self.csv_cache.get(name)
            if df is not None and not df.empty:
                for _, row in df.head(200).iterrows():
                    item = {
                        "type": "incident",
                        "source": name,
                        "priority": config.priority,
                        "id": safe_get(row, "number"),
                        "state": safe_get(row, "incident_state"),
                        "category": safe_get(row, "category"),
                        "symptom": safe_get(row, "u_symptom"),
                        "priority_level": safe_get(row, "priority"),
                        "resolution": safe_get(row, "closed_code"),
                        "short_description": safe_get(row, "short_description"),
                        "description": safe_get(row, "description"),
                        "content": f"{safe_get(row, 'short_description')} {safe_get(row, 'description')}",
                        "timestamp": datetime.now().isoformat()
                    }
                    csv_context.append(item)
    
    def _process_jira_csv(self, csv_context: List[Dict[str, Any]]) -> None:
        """Process JIRA CSV data"""
        for name, config in self.sources.items():
            if not config.enabled or config.type != SourceType.JIRA_CSV:
                continue
                
            jira_data = self.csv_cache.get(name, {})
            
            # Process Issues
            issues_df = jira_data.get('issues')
            if issues_df is not None and not issues_df.empty:
                for _, row in issues_df.head(200).iterrows():
                    item = {
                        "type": "jira_issue",
                        "source": name,
                        "priority": config.priority,
                        "id": safe_get(row, "key"),
                        "summary": safe_get(row, "summary"),
                        "status": safe_get(row, "status.name"),
                        "priority_level": safe_get(row, "priority.name"),
                        "assignee": safe_get(row, "assignee.displayName"),
                        "reporter": safe_get(row, "reporter.displayName"),
                        "description": safe_get(row, "description"),
                        "content": f"{safe_get(row, 'summary')} {safe_get(row, 'description')}",
                        "timestamp": safe_get(row, "updated", datetime.now().isoformat())
                    }
                    csv_context.append(item)
            
            # Process Comments
            comments_df = jira_data.get('comments')
            if comments_df is not None and not comments_df.empty:
                for _, row in comments_df.head(100).iterrows():
                    item = {
                        "type": "jira_comment",
                        "source": name,
                        "priority": config.priority,
                        "id": f"comment_{safe_get(row, 'id')}",
                        "issue_key": safe_get(row, "issue_key"),
                        "author": safe_get(row, "author.displayName"),
                        "body": safe_get(row, "body"),
                        "content": safe_get(row, "body"),
                        "timestamp": safe_get(row, "created", datetime.now().isoformat())
                    }
                    csv_context.append(item)
    
    def query(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Query all data sources"""
        try:
            if not self._running:
                return {"status": "error", "message": "Manager not running"}
            
            all_context = self.context.copy()
            
            # Add real-time context
            if self.realtime_manager:
                realtime_context = self.realtime_manager.get_recent_context(limit=limit//2)
                all_context.extend(realtime_context)
            
            # Score and filter
            query_lower = query.lower()
            keywords = query_lower.split()
            
            relevant = []
            for item in all_context:
                content = item.get('content', '')
                text = f"{content} {str(item)}".lower()
                
                matches = sum(1 for keyword in keywords if keyword in text)
                if matches > 0:
                    scored_item = item.copy()
                    base_score = matches
                    priority_boost = item.get('priority', 1)
                    scored_item["relevance_score"] = base_score * priority_boost
                    relevant.append(scored_item)
            
            relevant.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            active_sources = [name for name, config in self.sources.items() if config.enabled]
            
            return {
                "status": "success",
                "context": relevant[:limit],
                "total_found": len(relevant),
                "active_sources": active_sources,
                "has_realtime": self.realtime_manager is not None,
                "context_size": len(all_context)
            }
            
        except Exception as e:
            logger.error(f"Error in query: {e}")
            return {"status": "error", "message": str(e)}
    
    def status(self) -> Dict[str, Any]:
        """Get manager status"""
        source_status = {}
        
        for name, config in self.sources.items():
            info = {
                "type": config.type.value,
                "enabled": config.enabled,
                "priority": config.priority
            }
            
            if config.type in [SourceType.INCIDENTS_CSV, SourceType.JIRA_CSV]:
                data = self.csv_cache.get(name)
                if isinstance(data, dict):
                    info["record_count"] = sum(len(df) for df in data.values())
                else:
                    info["record_count"] = len(data) if data is not None else 0
            
            source_status[name] = info
        
        if self.realtime_manager:
            rt_status = self.realtime_manager.get_status()
            source_status["realtime_manager"] = rt_status
        
        return {
            "running": self._running,
            "total_sources": len(self.sources),
            "enabled_sources": len([c for c in self.sources.values() if c.enabled]),
            "context_size": len(self.context),
            "sources": source_status
        }
    
    def enable(self, name: str) -> None:
        """Enable a source"""
        if name in self.sources:
            self.sources[name].enabled = True
            logger.info(f"Enabled: {name}")
        
    def disable(self, name: str) -> None:
        """Disable a source"""
        if name in self.sources:
            self.sources[name].enabled = False
            logger.info(f"Disabled: {name}")
    
    def add_callback(self, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Add update callback"""
        self.callbacks.append(callback)

# Global instance
_manager: Optional[DataManager] = None

def get_manager() -> DataManager:
    """Get global data manager"""
    global _manager
    if _manager is None:
        _manager = DataManager()
    return _manager 