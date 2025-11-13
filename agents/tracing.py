import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


def log_trace(run_id: Optional[str], event: Dict[str, Any]) -> None:
    """
    Append a single JSON record to logs/{run_id}.jsonl.

    If run_id is missing or empty, do nothing.
    """
    if not run_id:
        return

    os.makedirs("logs", exist_ok=True)

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "run_id": str(run_id),
    }
    record.update(event)

    path = os.path.join("logs", f"{run_id}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
