"""
OpsMind Context Module

Unified context management and data access including:
- Real-time context management and processing
- Unified data access interface for all sources
- RAG context retrieval and filtering
- Live data stream processing and aggregation
"""

# Real-time context management
from .manager import RealTimeContextManager

# Unified data access interface
from .interface import get_context, configure, info, preset

# RAG context retrieval tools
from .retrieval import get_incident_context

__all__ = [
    # Real-time context management
    "RealTimeContextManager",
    
    # Unified data access
    "get_context",
    "configure", 
    "info",
    "preset",
    
    # RAG context retrieval
    "get_incident_context",
] 