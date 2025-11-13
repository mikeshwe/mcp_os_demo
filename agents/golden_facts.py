import json
import os
from typing import Any, Dict, Optional


def _safe_slug(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return (
        str(value)
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )


def get_golden_facts_path(company_name: Optional[str], period_end: Optional[str]) -> str:
    """
    Return the file path for the golden facts snapshot for a given company and period.
    """
    base_dir = "golden_facts"
    os.makedirs(base_dir, exist_ok=True)
    company_slug = _safe_slug(company_name)
    period_slug = _safe_slug(period_end)
    filename = f"{company_slug}_{period_slug}.json"
    return os.path.join(base_dir, filename)


def save_golden_facts(
    company_name: Optional[str],
    period_end: Optional[str],
    snapshot: Dict[str, Any],
) -> str:
    """
    Persist the KPI snapshot as JSON and return the file path.
    """
    path = get_golden_facts_path(company_name, period_end)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return path


def load_golden_facts(
    company_name: Optional[str],
    period_end: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Load a previously saved KPI snapshot if it exists.
    Return None if there is no file.
    """
    path = get_golden_facts_path(company_name, period_end)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
