"""
Core package for OpsMind agents and main functionality
"""
from .agents import (
    listener,
    synthesizer, 
    writer,
    pipeline,
    search,
    root,
)



# Initialize guardrails on module import
from .safety import initialize_default_guardrails

# Initialize default guardrails when the module is imported
try:
    initialize_default_guardrails()
except Exception as e:
    # Don't fail module import if guardrails can't be initialized
    import logging
    logging.getLogger(__name__).warning(f"Failed to initialize default guardrails: {e}")

__all__ = [
    'listener',
    'synthesizer',
    'writer', 
    'pipeline',
    'search',
    'root',

] 