"""
Base connector interface for real-time data loading
"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ConnectorStatus(Enum):
    """Connector status enumeration"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"

@dataclass
class ConnectorConfig:
    """Configuration for connectors"""
    name: str
    connector_type: str
    enabled: bool = True
    poll_interval: int = 60  # seconds
    max_retries: int = 3
    retry_delay: int = 5  # seconds
    batch_size: int = 100
    connection_params: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)
    transform_config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DataRecord:
    """Standardized data record format"""
    id: str
    source: str
    type: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'source': self.source,
            'type': self.type,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'metadata': self.metadata
        }

class BaseConnector(ABC):
    """Base class for all real-time data connectors"""
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.status = ConnectorStatus.STOPPED
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.data_callbacks: List[Callable[[List[DataRecord]], None]] = []
        self.error_callbacks: List[Callable[[Exception], None]] = []
        
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to data source"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to data source"""
        pass
    
    @abstractmethod
    async def fetch_data(self) -> AsyncGenerator[List[DataRecord], None]:
        """Fetch data from source - yields batches of records"""
        pass
    
    async def start(self) -> None:
        """Start the connector"""
        if self.status == ConnectorStatus.RUNNING:
            logger.warning(f"Connector {self.config.name} is already running")
            return
            
        self.status = ConnectorStatus.STARTING
        self._stop_event.clear()
        
        try:
            if await self.connect():
                self.status = ConnectorStatus.RUNNING
                self._task = asyncio.create_task(self._run_loop())
                logger.info(f"Connector {self.config.name} started successfully")
            else:
                self.status = ConnectorStatus.ERROR
                raise ConnectionError(f"Failed to connect {self.config.name}")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            logger.error(f"Error starting connector {self.config.name}: {e}")
            await self._handle_error(e)
            raise
    
    async def stop(self) -> None:
        """Stop the connector"""
        if self.status == ConnectorStatus.STOPPED:
            return
            
        self.status = ConnectorStatus.STOPPING
        self._stop_event.set()
        
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning(f"Connector {self.config.name} did not stop gracefully")
        
        await self.disconnect()
        self.status = ConnectorStatus.STOPPED
        logger.info(f"Connector {self.config.name} stopped")
    
    async def _run_loop(self) -> None:
        """Main data fetching loop"""
        retry_count = 0
        
        while not self._stop_event.is_set():
            try:
                # Get data generator and iterate through batches
                data_generator = self.fetch_data()
                async for records in data_generator:
                    if self._stop_event.is_set():
                        break
                        
                    if records:
                        await self._process_records(records)
                        retry_count = 0  # Reset retry count on success
                
                # Wait for next poll interval
                await asyncio.wait_for(
                    self._stop_event.wait(), 
                    timeout=self.config.poll_interval
                )
                
            except asyncio.TimeoutError:
                # Normal timeout from poll interval
                continue
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in {self.config.name} fetch loop: {e}")
                
                if retry_count >= self.config.max_retries:
                    self.status = ConnectorStatus.ERROR
                    await self._handle_error(e)
                    break
                
                # Wait before retry
                await asyncio.sleep(self.config.retry_delay)
    
    async def _process_records(self, records: List[DataRecord]) -> None:
        """Process fetched records"""
        try:
            # Apply filters if configured
            filtered_records = self._apply_filters(records)
            
            # Apply transformations if configured
            transformed_records = self._apply_transforms(filtered_records)
            
            # Notify callbacks
            for callback in self.data_callbacks:
                try:
                    callback(transformed_records)
                except Exception as e:
                    logger.error(f"Error in data callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing records in {self.config.name}: {e}")
            await self._handle_error(e)
    
    def _apply_filters(self, records: List[DataRecord]) -> List[DataRecord]:
        """Apply configured filters to records"""
        if not self.config.filters:
            return records
            
        filtered = []
        for record in records:
            include = True
            
            # Apply filters based on configuration
            for filter_key, filter_value in self.config.filters.items():
                if filter_key in record.data:
                    if isinstance(filter_value, list):
                        if record.data[filter_key] not in filter_value:
                            include = False
                            break
                    elif record.data[filter_key] != filter_value:
                        include = False
                        break
            
            if include:
                filtered.append(record)
                
        return filtered
    
    def _apply_transforms(self, records: List[DataRecord]) -> List[DataRecord]:
        """Apply configured transformations to records"""
        # Basic transformation support - can be extended
        return records
    
    async def _handle_error(self, error: Exception) -> None:
        """Handle connector errors"""
        for callback in self.error_callbacks:
            try:
                callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    def add_data_callback(self, callback: Callable[[List[DataRecord]], None]) -> None:
        """Add a callback for new data"""
        self.data_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """Add a callback for errors"""
        self.error_callbacks.append(callback)
    
    def get_status(self) -> Dict[str, Any]:
        """Get connector status information"""
        return {
            'name': self.config.name,
            'type': self.config.connector_type,
            'status': self.status.value,
            'enabled': self.config.enabled,
            'config': self.config.__dict__
        } 