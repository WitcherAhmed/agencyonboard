"""JSON-file persistence: client state, tasks, activity log. Deterministic, no DB."""
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import config

_LOCK = threading.Lock()


def now() -> str:
    return datetime.now().strftime("%H:%M")


def now_full() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_activity(action: str) -> None:
    """Append one line to the human-readable activity log."""
    config.ensure_dirs()
    line = f"{now()} {action}"
    with _LOCK:
        with open(config.ACTIVITY_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    print(f"   [activity] {line}", flush=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".corrupt")
        path.rename(backup)
        print(f"   [warn] corrupt json moved to {backup.name}")
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic write so a crash mid-demo never loses state."""
    config.ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def blank_state(client_id: str) -> Dict[str, Any]:
    return {
        "client_id": client_id,
        "business_name": config.CLIENT_NAME,
        "services": list(config.CLIENT_SERVICES),
        "created_at": now_full(),
        "information": {},        # field -> {value, source, updated_at}
        "documents": [],          # processed uploads
        "history": [],            # conversation turns for the LLM
        "onboarding_complete": False,
        "completed_at": None,
        "brief_path": None,
        "tasks_created": False,
        "pending_attachment": None,  # file the client just uploaded, for process_document()
    }


def load_state(client_id: str = None) -> Dict[str, Any]:
    client_id = client_id or config.CLIENT_ID
    return read_json(config.client_file(client_id), blank_state(client_id))


def save_state(state: Dict[str, Any]) -> None:
    write_json(config.client_file(state["client_id"]), state)


def load_tasks() -> list:
    return read_json(config.TASKS_FILE, [])


def save_tasks(tasks: list) -> None:
    write_json(config.TASKS_FILE, tasks)