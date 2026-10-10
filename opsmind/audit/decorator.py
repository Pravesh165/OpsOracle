"""
Decorator for transparent structured audit logging on tools and functions.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import Any, Callable, Dict, Optional

from opsmind.audit.logger import AuditLogger


def _extract_session_id(args: tuple, kwargs: dict) -> str:
    """Attempt to extract session_id from ToolContext or kwargs."""
    for arg in args:
        # Check if arg has session_id directly or through session object
        if hasattr(arg, "session_id") and getattr(arg, "session_id"):
            return str(getattr(arg, "session_id"))
        if hasattr(arg, "state") and isinstance(arg.state, dict):
            if "session_id" in arg.state:
                return str(arg.state["session_id"])
    if "session_id" in kwargs:
        return str(kwargs["session_id"])
    return "session_unknown"


def _summarize_args(func: Callable, args: tuple, kwargs: dict) -> Dict[str, Any]:
    """Capture a serializable summary of arguments, excluding ToolContext/self."""
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        summary: Dict[str, Any] = {}
        for param_name, param_val in bound.arguments.items():
            if param_name in ("self", "tool_context", "cls"):
                continue
            # Store representation or direct value if primitive
            if isinstance(param_val, (str, int, float, bool, type(None))):
                summary[param_name] = param_val
            elif isinstance(param_val, dict):
                # Truncate large dicts for summary
                summary[param_name] = {k: str(v)[:100] for k, v in list(param_val.items())[:10]}
            elif isinstance(param_val, (list, tuple)):
                summary[param_name] = [str(x)[:100] for x in param_val[:5]]
            else:
                summary[param_name] = str(param_val)[:100]
        return summary
    except Exception:
        return {"raw_kwargs": {k: str(v)[:100] for k, v in kwargs.items()}}


def audit_action(action_type: str, tool_name: Optional[str] = None):
    """
    Decorator that records an audit log entry on tool execution.
    Handles both async and sync functions safely.
    """
    def decorator(func: Callable) -> Callable:
        resolved_tool_name = tool_name or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                logger = AuditLogger.get_instance()
                start_time = time.perf_counter()
                session_id = _extract_session_id(args, kwargs)
                args_summary = _summarize_args(func, args, kwargs)
                result_code = "success"
                extra = {}

                try:
                    result = await func(*args, **kwargs)
                    if isinstance(result, dict) and result.get("status") in ("error", "failed"):
                        result_code = str(result.get("status"))
                    return result
                except Exception as exc:
                    result_code = "exception"
                    extra["error"] = str(exc)
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.log_event(
                        action=action_type,
                        tool=resolved_tool_name,
                        args_summary=args_summary,
                        result_code=result_code,
                        duration_ms=duration_ms,
                        session_id=session_id,
                        extra=extra if extra else None,
                    )
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                logger = AuditLogger.get_instance()
                start_time = time.perf_counter()
                session_id = _extract_session_id(args, kwargs)
                args_summary = _summarize_args(func, args, kwargs)
                result_code = "success"
                extra = {}

                try:
                    result = func(*args, **kwargs)
                    if isinstance(result, dict) and result.get("status") in ("error", "failed"):
                        result_code = str(result.get("status"))
                    return result
                except Exception as exc:
                    result_code = "exception"
                    extra["error"] = str(exc)
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.log_event(
                        action=action_type,
                        tool=resolved_tool_name,
                        args_summary=args_summary,
                        result_code=result_code,
                        duration_ms=duration_ms,
                        session_id=session_id,
                        extra=extra if extra else None,
                    )
            return sync_wrapper

    return decorator

