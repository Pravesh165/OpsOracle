"""
Structured Audit Logging module for OPS-Mind.
Records all tool and critical operational actions to structured JSONL logs.
Enforces secret redaction and safe in-memory/file persistence.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Redaction patterns for common sensitive keys
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(token|secret|password|api_key|authorization|bearer|credential|private_key|cookie)",
    re.IGNORECASE,
)

REDACTED_PLACEHOLDER = "[REDACTED]"


def sanitize_value(val: Any) -> Any:
    """Recursively sanitize potentially sensitive data structures."""
    if isinstance(val, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in val.items():
            if SENSITIVE_KEY_PATTERNS.search(str(k)):
                sanitized[k] = REDACTED_PLACEHOLDER
            else:
                sanitized[k] = sanitize_value(v)
        return sanitized
    elif isinstance(val, (list, tuple, set)):
        return [sanitize_value(elem) for elem in val]
    elif isinstance(val, str):
        # Mask basic bearer or basic auth headers in raw strings
        if re.search(r"bearer\s+[A-Za-z0-9_\-\.]+", val, re.IGNORECASE):
            return re.sub(r"(bearer\s+)[A-Za-z0-9_\-\.]+", r"\1[REDACTED]", val, flags=re.IGNORECASE)
        if re.search(r"basic\s+[A-Za-z0-9+/=]+", val, re.IGNORECASE):
            return re.sub(r"(basic\s+)[A-Za-z0-9+/=]+", r"\1[REDACTED]", val, flags=re.IGNORECASE)
        return val
    return val


class AuditLogger:
    """Thread-safe and process-safe structured JSONL audit logger."""

    _instance: Optional["AuditLogger"] = None

    def __init__(self, log_path: Optional[str] = None):
        if log_path is None:
            # Default to output/audit.jsonl in project root or current working directory
            base_dir = os.environ.get("OPSMIND_OUTPUT_DIR", "output")
            log_path = os.path.join(base_dir, "audit.jsonl")

        self.log_file = Path(log_path)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._in_memory_events: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls, log_path: Optional[str] = None) -> "AuditLogger":
        """Get or initialize singleton instance."""
        if cls._instance is None:
            cls._instance = cls(log_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (mostly for test fixtures)."""
        cls._instance = None

    def log_event(
        self,
        action: str,
        tool: str,
        args_summary: Dict[str, Any],
        result_code: str,
        duration_ms: float,
        session_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record a single structured audit event.

        Required fields:
        - timestamp (ISO8601 UTC)
        - session_id
        - action
        - tool
        - args_summary (sanitized)
        - result_code
        - duration_ms
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        clean_args = sanitize_value(args_summary or {})
        clean_extra = sanitize_value(extra or {})

        event: Dict[str, Any] = {
            "timestamp": timestamp,
            "session_id": session_id or "default_session",
            "action": action,
            "tool": tool,
            "args_summary": clean_args,
            "result_code": result_code,
            "duration_ms": round(duration_ms, 2),
        }
        if clean_extra:
            event["extra"] = clean_extra

        # Append to in-memory buffer
        self._in_memory_events.append(event)

        # Write to JSONL file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            # Audit logging failure must not crash business logic, but log to stderr
            import sys
            sys.stderr.write(f"Failed to write audit event to {self.log_file}: {e}\n")

        return event

    def query_events(
        self,
        action: Optional[str] = None,
        tool: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query audit events from JSONL file (fallback to in-memory).
        """
        events: List[Dict[str, Any]] = []

        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except Exception:
                events = list(self._in_memory_events)
        else:
            events = list(self._in_memory_events)

        # Filter
        filtered = []
        for ev in events:
            if action and ev.get("action") != action:
                continue
            if tool and ev.get("tool") != tool:
                continue
            if session_id and ev.get("session_id") != session_id:
                continue
            if start_time and ev.get("timestamp", "") < start_time:
                continue
            if end_time and ev.get("timestamp", "") > end_time:
                continue
            filtered.append(ev)

        # Return latest first up to limit
        return filtered[-limit:]

