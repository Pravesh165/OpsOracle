"""
Dashboard data bridge — thin wrapper over OpsMind data loaders.

All dashboard pages import from here, never directly from opsmind.*
This keeps the dashboard loosely coupled to core logic.

Every function is safe to call even when data files are absent:
it returns an empty DataFrame / list / dict rather than raising.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# ---------------------------------------------------------------------------
# Resolve output directory without importing opsmind.config at module level
# (avoids pulling in google-adk at Streamlit startup)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent
_OUTPUT_DIR = _PROJECT_ROOT / "output"


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

def get_incidents() -> pd.DataFrame:
    """
    Load incident data from CSV.

    Returns an empty DataFrame when the file is absent.
    Adds a computed 'severity_score' column when priority column exists.
    """
    try:
        from opsmind.data.loader import load_incident_data
        df = load_incident_data()
        if df.empty:
            return df
        # Normalise priority → numeric severity for charts
        if "priority" in df.columns:
            _pmap = {"1": 1.0, "p1": 1.0, "critical": 1.0,
                     "2": 0.7, "p2": 0.7, "high": 0.7,
                     "3": 0.4, "p3": 0.4, "medium": 0.4,
                     "4": 0.2, "p4": 0.2, "low": 0.2}
            df["severity_score"] = (
                df["priority"].str.lower().str.strip().map(_pmap).fillna(0.3)
            )
        return df
    except Exception as exc:
        return pd.DataFrame({"_error": [str(exc)]})


def get_incident_states() -> Dict[str, int]:
    """Return count of incidents per state from the CSV 'state' column."""
    df = get_incidents()
    if df.empty or "state" not in df.columns:
        return {}
    return df["state"].value_counts().to_dict()


def get_incident_categories() -> Dict[str, int]:
    """Return count of incidents per category."""
    df = get_incidents()
    if df.empty or "category" not in df.columns:
        return {}
    return df["category"].value_counts().to_dict()


# ---------------------------------------------------------------------------
# Postmortems
# ---------------------------------------------------------------------------

def get_postmortems() -> List[Dict[str, Any]]:
    """
    List saved postmortem .md files from the output directory.

    Returns list of dicts: {filename, filepath, size, modified, incident_id, preview}.
    """
    results: List[Dict[str, Any]] = []
    try:
        output_dir = _OUTPUT_DIR
        if not output_dir.exists():
            return results
        for path in sorted(
            output_dir.glob("postmortem_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            stat = path.stat()
            text = path.read_text(encoding="utf-8", errors="replace")
            # Extract incident_id from filename: postmortem_INC0000001_20240101_120000.md
            parts = path.stem.split("_")
            incident_id = parts[1] if len(parts) >= 2 else "unknown"
            results.append({
                "filename": path.name,
                "filepath": str(path),
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "incident_id": incident_id,
                "preview": text[:200].replace("\n", " "),
                "content": text,
            })
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------

def get_mttr_data() -> pd.DataFrame:
    """
    Compute mean-time-to-resolve per category from incident CSV.

    Returns DataFrame with columns: category, mttr_hours, incident_count.
    Falls back to synthetic demo data when real data is absent.
    """
    df = get_incidents()
    if not df.empty and "resolved_at" in df.columns and "opened_at" in df.columns:
        try:
            df = df.copy()
            df["opened_dt"] = pd.to_datetime(df["opened_at"], errors="coerce")
            df["resolved_dt"] = pd.to_datetime(df["resolved_at"], errors="coerce")
            df["duration_h"] = (
                (df["resolved_dt"] - df["opened_dt"]).dt.total_seconds() / 3600
            )
            df = df[df["duration_h"] > 0]
            if not df.empty and "category" in df.columns:
                agg = (
                    df.groupby("category")["duration_h"]
                    .agg(mttr_hours="mean", incident_count="count")
                    .reset_index()
                )
                agg["mttr_hours"] = agg["mttr_hours"].round(1)
                return agg
        except Exception:
            pass

    # Demo fallback
    return pd.DataFrame({
        "category": ["network", "database", "software", "hardware", "security"],
        "mttr_hours": [4.2, 8.7, 2.1, 12.5, 6.3],
        "incident_count": [23, 15, 41, 8, 12],
    })


def get_recurring_patterns() -> pd.DataFrame:
    """
    Return top recurring incident categories/symptoms.

    Returns DataFrame with columns: pattern, count, avg_severity.
    """
    df = get_incidents()
    if not df.empty and "category" in df.columns:
        try:
            agg = df.groupby("category").agg(
                count=("category", "count"),
            ).reset_index().rename(columns={"category": "pattern"})
            if "severity_score" in df.columns:
                sev = df.groupby("category")["severity_score"].mean().reset_index()
                sev.columns = ["pattern", "avg_severity"]
                agg = agg.merge(sev, on="pattern", how="left")
            else:
                agg["avg_severity"] = 0.5
            return agg.sort_values("count", ascending=False).head(10)
        except Exception:
            pass

    return pd.DataFrame({
        "pattern": ["Connection timeout", "OOM kill", "Disk full", "DNS failure", "SSL expiry"],
        "count": [34, 21, 18, 12, 9],
        "avg_severity": [0.7, 0.8, 0.6, 0.5, 0.9],
    })


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def get_incident_timeline(incident_id: str) -> List[Dict[str, Any]]:
    """
    Build a timeline list for a given incident_id.

    Returns list of {timestamp, event, detail} dicts sorted by time.
    Falls back to a synthetic demo timeline when data is absent.
    """
    events: List[Dict[str, Any]] = []
    try:
        from opsmind.data.loader import load_incident_data, load_jira_data
        inc_df = load_incident_data()
        if not inc_df.empty and "number" in inc_df.columns:
            row = inc_df[inc_df["number"] == incident_id]
            if not row.empty:
                r = row.iloc[0]
                if r.get("opened_at"):
                    events.append({"timestamp": str(r["opened_at"]), "event": "Incident opened", "detail": str(r.get("short_description", ""))})
                if r.get("resolved_at"):
                    events.append({"timestamp": str(r["resolved_at"]), "event": "Incident resolved", "detail": str(r.get("close_notes", ""))})

        jira = load_jira_data()
        cl = jira.get("changelog", pd.DataFrame())
        if not cl.empty and "key" in cl.columns:
            related = cl[cl["key"].str.contains(incident_id, case=False, na=False)]
            for _, row in related.head(10).iterrows():
                events.append({
                    "timestamp": str(row.get("created", "")),
                    "event": f"Jira: {row.get('field', 'field')} changed",
                    "detail": f"{row.get('fromString', '')} → {row.get('toString', '')}",
                })
    except Exception:
        pass

    if not events:
        # Demo fallback
        events = [
            {"timestamp": "2024-01-15 08:00", "event": "Incident detected", "detail": "Automated alert triggered"},
            {"timestamp": "2024-01-15 08:05", "event": "Triaged", "detail": "Severity: CRITICAL, Team: network-ops"},
            {"timestamp": "2024-01-15 08:30", "event": "Acknowledged", "detail": "On-call engineer paged"},
            {"timestamp": "2024-01-15 09:15", "event": "Mitigating", "detail": "Runbook restart_service executed"},
            {"timestamp": "2024-01-15 10:00", "event": "Verification", "detail": "Health checks: 3/3 passed"},
            {"timestamp": "2024-01-15 10:05", "event": "Resolved", "detail": "Postmortem generated"},
        ]

    events.sort(key=lambda e: e["timestamp"])
    return events


# ---------------------------------------------------------------------------
# Knowledge stats
# ---------------------------------------------------------------------------

def get_knowledge_stats() -> Dict[str, Any]:
    """
    Return knowledge base statistics from the retrieval singleton.

    Safe to call even when the index has not been built yet.
    """
    try:
        from opsmind.tools.learning import get_knowledge_stats as _stats
        result = _stats()
        if result.get("status") == "success":
            return result
    except Exception:
        pass

    return {
        "status": "unavailable",
        "total_documents": 0,
        "sources": {},
        "postmortem_count": 0,
        "index_loaded": False,
        "top_weighted": [],
        "message": "Knowledge index not yet built. Run scripts/build_index.py to populate.",
    }


def get_recent_searches() -> List[str]:
    """Placeholder — returns empty list until search history is persisted."""
    return []
