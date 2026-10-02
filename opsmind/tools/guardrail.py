"""
Simplified Guardrail Tools for OpsMind
"""

from typing import Dict, Any, Callable
from functools import wraps
from google.adk.tools.tool_context import ToolContext
from opsmind.config import logger
from opsmind.core.safety import (
    get_guardrail_manager, 
    initialize_default_guardrails,
    with_guardrails,
)


def with_guardrail(func: Callable) -> Callable:
    """
    Simplified decorator that applies guardrails to any function.
    
    This decorator automatically:
    - Validates input data
    - Applies rate limiting
    - Ensures UI content escaping
    - Blocks execution if strict guardrails fail
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # Initialize guardrails if not already done
            manager = get_guardrail_manager()
            if not manager.guardrails:
                initialize_default_guardrails()
            
            # Create validation context
            context = {
                'function_name': func.__name__,
                'args': args,
                'kwargs': kwargs,
                'data': kwargs.get('data', {})
            }
            
            # Run all guardrails
            result = await manager.check_all(context)
            
            # Block if strict failures
            if result['status'] == 'blocked':
                logger.warning(f"Guardrails blocked execution for {func.__name__}")
                error_msg = f"Guardrails blocked execution: {result['failed']} failed checks"
                if hasattr(func, '__annotations__') and func.__annotations__.get('return') == Dict[str, Any]:
                    return {
                        'status': 'error',
                        'safe': False,
                        'message': error_msg
                    }
                else:
                    raise RuntimeError(error_msg)
            
            # Log any non-blocking failures
            if result['failed'] > 0:
                logger.warning(f"Guardrail warnings for {func.__name__}: {result['failed']} non-strict checks failed")
            
            # Execute function if guardrails pass
            return await func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Guardrail error for {func.__name__}: {e}")
            if hasattr(func, '__annotations__') and func.__annotations__.get('return') == Dict[str, Any]:
                return {
                    'status': 'error',
                    'safe': False,
                    'message': f"Guardrail error: {str(e)}"
                }
            else:
                raise
    
    return wrapper


# === ESSENTIAL MONITORING FUNCTIONS ===

def check_guardrails_health(tool_context: ToolContext) -> Dict[str, Any]:
    """Check comprehensive status of all guardrails"""
    try:
        manager = get_guardrail_manager()
        
        if not manager.guardrails:
            initialize_default_guardrails()
        
        stats = manager.get_stats()
        
        return {
            "status": "success",
            "total_guardrails": stats["total_guardrails"],
            "enabled_guardrails": stats["enabled_guardrails"],
            "guardrail_checks": stats["guardrail_checks"],
            "safety_status": "healthy" if stats["enabled_guardrails"] > 0 else "no_guardrails",
            "message": f"Health check complete. {stats['enabled_guardrails']} guardrails enabled."
        }
        
    except Exception as e:
        logger.error(f"Error checking guardrails health: {e}")
        return {
            "status": "error",
            "message": f"Failed to check guardrails health: {str(e)}"
        }


def get_system_resources(tool_context: ToolContext) -> Dict[str, Any]:
    """Get system resource information"""
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        resources = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "available_memory": memory.available,
            "total_memory": memory.total,
            "status": "healthy" if cpu_percent < 80 and memory.percent < 80 else "high_usage"
        }
        
        return {
            "status": "success",
            "resources": resources,
            "message": f"System: CPU {cpu_percent}%, Memory {memory.percent}%"
        }
        
    except Exception as e:
        logger.error(f"Error getting system resources: {e}")
        return {
            "status": "error",
            "message": f"Failed to get system resources: {str(e)}"
        }


def initialize_guardrails(tool_context: ToolContext) -> Dict[str, Any]:
    """Initialize the guardrail system"""
    try:
        initialize_default_guardrails()
        manager = get_guardrail_manager()
        
        stats = manager.get_stats()
        
        return {
            "status": "success",
            "initialized_guardrails": stats["total_guardrails"],
            "enabled_guardrails": stats["enabled_guardrails"],
            "types": ["validation", "rate_limiting", "ui_content_escaping"],
            "message": f"Initialized {stats['total_guardrails']} guardrails successfully"
        }
        
    except Exception as e:
        logger.error(f"Error initializing guardrails: {e}")
        return {
            "status": "error",
            "message": f"Failed to initialize guardrails: {str(e)}"
        }


# === SIMPLIFIED MONITORING HELPERS ===

def monitor_safety_status(tool_context: ToolContext) -> str:
    """Simple safety status for agent use"""
    try:
        result = check_guardrails_health(tool_context)
        
        if result['status'] == 'success':
            return f"Safety: {result['enabled_guardrails']} guardrails enabled - {result['safety_status']}"
        else:
            return f"Safety check failed: {result['message']}"
        
    except Exception as e:
        logger.error(f"Error monitoring safety: {e}")
        return f"Safety monitoring error: {str(e)}"


def check_system_health(tool_context: ToolContext) -> str:
    """Simple system health for agent use"""
    try:
        result = get_system_resources(tool_context)
        
        if result['status'] == 'success':
            resources = result['resources']
            return f"System: CPU {resources['cpu_percent']}%, Memory {resources['memory_percent']}% - {resources['status']}"
        else:
            return f"System check failed: {result['message']}"
        
    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return f"System health check error: {str(e)}" 