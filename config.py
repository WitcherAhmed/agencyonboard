"""Tiny env-var config + .env loader. No framework, no pydantic."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CLIENTS_DIR = DATA_DIR / "clients"
SAMPLE_DIR = ROOT / "sample"
DOWNLOADS_DIR = DATA_DIR / "downloads"

TASKS_FILE = DATA_DIR / "tasks.json"
ACTIVITY_FILE = DATA_DIR / "activity.log"
BRIEFS_DIR = DATA_DIR / "briefs"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(ROOT / ".env")


def _hermes_agent_key() -> str:
    """Reuse the already-configured Hermes inference credential if present."""
    home = os.environ.get("HERMES_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "hermes"
    )
    auth = Path(home) / "auth.json"
    if not auth.exists():
        return ""
    try:
        data = json.loads(auth.read_text(encoding="utf-8"))
        return data["providers"]["nous"]["agent_key"]
    except Exception:
        return ""


def _hermes_base_url() -> str:
    home = os.environ.get("HERMES_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "hermes"
    )
    cfg = Path(home) / "config.yaml"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("base_url:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    return "https://inference-api.nousresearch.com/v1"


# ── Model (all overridable from .env) ───────────────────────────────────────
LLM_MODEL = os.environ.get("AGENT_MODEL", "stealth/space-bunny-alpha")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").strip() or _hermes_base_url()
LLM_API_KEY = (
    os.environ.get("LLM_API_KEY")
    or os.environ.get("OPENROUTER_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or _hermes_agent_key()
)

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CLIENT_CHAT_ID = os.environ.get("CLIENT_CHAT_ID", "").strip()

# ── Demo client ─────────────────────────────────────────────────────────────
CLIENT_ID = os.environ.get("CLIENT_ID", "cairo_beans")
CLIENT_NAME = os.environ.get("CLIENT_NAME", "Cairo Beans")
CLIENT_SERVICES = [
    s.strip()
    for s in os.environ.get("CLIENT_SERVICES", "Social Media Management,Content Creation").split(",")
    if s.strip()
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, CLIENTS_DIR, DOWNLOADS_DIR, BRIEFS_DIR, SAMPLE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def client_file(client_id: str) -> Path:
    return CLIENTS_DIR / f"{client_id}.json"


def redact_key(key: str) -> str:
    return f"{key[:6]}...{key[-4:]}" if len(key) > 12 else ("set" if key else "missing")