"""
Compatibility layer for ADK framework
This module maintains backward compatibility while using the new modular structure
"""

# Import the root from our new modular structure
from .core.agents import root

# Export for ADK framework compatibility
# ADK framework expects 'root_agent' attribute but we want to keep it as 'root'
root_agent = root  # Alias for ADK compatibility

__all__ = ['root', 'root_agent'] 