"""The 8 agent tools. Deterministic: every call really changes a file on disk."""
import time
from pathlib import Path
from typing import Any, Dict

import config
import document
import store

# field key -> what it is / what to ask for
REQUIREMENTS: Dict[str, str] = {
    "business_description": "What the business is, what it sells, where it operates",
    "target_audience": "Who the customers are (demographics, age, interests, area)",
    "marketing_goals": "What success looks like for this engagement (growth, awareness, sales...)",
    "products_menu": "Products, services or menu, with prices if available",
    "social_accounts": "Existing social media accounts and their handles/links",
    "brand_voice": "How the brand should sound (tone, do's and don'ts, emoji use)",
    "brand_guidelines": "Colours, typography, visual style, logo rules",
    "logo_assets": "Logo files, photos, and other ready-to-use assets",
    "competitors": "3-5 competitors or brands they admire / want to look like",
    "content_preferences": "What content they want (formats, themes, posting cadence, banned topics)",
}

FIELD_ALIASES = {
    "business": "business_description", "description": "business_description",
    "audience": "target_audience", "customers": "target_audience",
    "goals": "marketing_goals", "goal": "marketing_goals",
    "products": "products_menu", "menu": "products_menu", "services_offered": "products_menu",
    "socials": "social_accounts", "social": "social_accounts", "social_media": "social_accounts",
    "voice": "brand_voice", "tone_of_voice": "brand_voice", "tone": "brand_voice",
    "guidelines": "brand_guidelines", "brand_guidelines_doc": "brand_guidelines",
    "logo": "logo_assets", "assets": "logo_assets", "files": "logo_assets",
    "competition": "competitors", "competitor": "competitors",
    "content": "content_preferences", "content_preference": "content_preferences",
    "location": "business_description", "city": "business_description",
}


def canonical_field(name: str) -> str:
    key = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return FIELD_ALIASES.get(key, key)


def _state() -> Dict[str, Any]:
    return store.load_state()


# ── Tool 1 ──────────────────────────────────────────────────────────────────
def get_requirements(services: str = "") -> dict:
    log = f"Agent called get_requirements() -> {len(REQUIREMENTS)} fields required"
    store.log_activity(log)
    return {
        "count": len(REQUIREMENTS),
        "requirements": [{"field": k, "what_it_is": v} for k, v in REQUIREMENTS.items()],
    }


# ── Tool 2 ──────────────────────────────────────────────────────────────────
def save_information(field: str, value: str, source: str = "client message") -> dict:
    state = _state()
    key = canonical_field(field)
    if key not in REQUIREMENTS:
        return {"ok": False,
                "error": f"Unknown field '{field}'. Valid fields: {', '.join(REQUIREMENTS)}"}
    value = (value or "").strip()
    if not value:
        return {"ok": False, "error": f"Empty value for '{key}', nothing saved."}
    prev = state["information"].get(key, {}).get("value")
    state["information"][key] = {
        "value": value,
        "source": source,
        "updated_at": store.now_full(),
    }
    store.save_state(state)
    verb = "updated" if prev and prev != value else "saved"
    store.log_activity(f"Agent {verb} {key.replace('_', ' ')}")
    return {"ok": True, "field": key, "value": value, "replaced_previous": bool(prev)}


# ── Tool 3 ──────────────────────────────────────────────────────────────────
def get_status() -> dict:
    state = _state()
    done = [f for f in REQUIREMENTS if f in state["information"]]
    missing = [f for f in REQUIREMENTS if f not in state["information"]]
    total = len(REQUIREMENTS)
    pct = round(100 * len(done) / total)
    store.log_activity(
        f"Agent checked status: {len(done)}/{total} complete ({pct}%), {len(missing)} missing"
    )
    return {
        "progress": f"{len(done)}/{total} ({pct}%)",
        "percent": pct,
        "completed": done,
        "missing": missing,
        "onboarding_complete": state["onboarding_complete"],
        "collected": {k: v["value"] for k, v in state["information"].items()},
    }


# ── Tool 4 ──────────────────────────────────────────────────────────────────
def request_missing_information(limit: int = 2, focus: str = "") -> dict:
    """Determine what is missing and hand the agent a short, specific ask."""
    status = get_status()
    if not status["missing"]:
        return {"ok": False, "missing": [], "message": "Nothing is missing."}
    picks = status["missing"][: max(1, int(limit or 1))]
    if focus:
        focus_key = canonical_field(focus)
        picks = [focus_key] + [f for f in picks if f != focus_key]
        picks = [f for f in picks if f in status["missing"]][: max(1, int(limit or 1))]
    asks = [
        {"field": f, "what_it_is": REQUIREMENTS[f], "already_known": False} for f in picks
    ]
    store.log_activity(
        f"Agent requested: {', '.join(p.replace('_', ' ') for p in picks)}"
    )
    return {"ok": True, "ask_for": asks, "still_missing": status["missing"]}


# ── Tool 5 ──────────────────────────────────────────────────────────────────
def process_document(file_path: str, original_name: str = "", client_message: str = "") -> dict:
    """Extract text from an uploaded file and give the agent the raw material."""
    path = Path(file_path) if file_path else Path("")
    name = original_name or path.name
    if not path.exists():
        # Fall back to the file the client just uploaded, whatever the model typed.
        pending = _state().get("pending_attachment")
        if pending and Path(pending["path"]).exists():
            path, name = Path(pending["path"]), pending.get("name", pending["path"])
    if not path.exists():
        # The model may send just a filename; look it up where uploads live.
        for folder in (config.DOWNLOADS_DIR, config.SAMPLE_DIR, config.DATA_DIR, config.ROOT):
            candidate = folder / path.name
            if candidate.exists():
                path = candidate
                break
    if not path.exists():
        store.log_activity(f"Agent failed to process {name}: file not found")
        return {"ok": False, "error": f"File not found: {file_path}"}

    result = document.extract(path)
    store.log_activity(f"Agent received document: {name} ({result['note']})")

    state = _state()
    entry = {
        "filename": name,
        "path": str(path),
        "kind": result["kind"],
        "chars": result["chars"],
        "note": result["note"],
        "client_message": client_message,
        "processed_at": store.now_full(),
        "extracted_text": result["text"],
    }
    state["documents"].append(entry)
    state["pending_attachment"] = None
    store.save_state(state)
    store.log_activity(f"Agent processed document {name} -> {result['kind']}, {result['chars']} chars")

    return {
        "ok": result["kind"] != "empty",
        "filename": name,
        "kind": result["kind"],
        "extracted_text": result["text"],
        "chars": result["chars"],
        "note": result["note"],
        "image_path": str(path) if result["kind"] == "image" else None,
        "instruction": (
            "Read the extracted text and call save_information() once per relevant field. "
            "Only record facts actually present in the document. If the text is empty or "
            "irrelevant, say so plainly and move on."
            if result["kind"] == "text"
            else "You must now LOOK at the image yourself (it is attached to your next turn), "
                 "describe what is on it, then call save_information() for any onboarding "
                 "facts it actually contains. Never invent what you cannot see."
            if result["kind"] == "image"
            else "Extraction produced nothing usable. Tell the client you couldn't read it and "
                 "ask them to resend as PDF/DOCX/TXT."
        ),
    }


# ── Tool 6 ──────────────────────────────────────────────────────────────────
def generate_client_brief() -> dict:
    state = _state()
    info = state["information"]
    missing = [f for f in REQUIREMENTS if f not in info]
    labels = {f: f.replace("_", " ").title() for f in REQUIREMENTS}
    lines = [
        f"# {state['business_name']} — Client Brief",
        "",
        f"_Generated {store.now_full()} by AgencyOnboard agent_",
        "",
    ]
    for f in REQUIREMENTS:
        lines.append(f"## {labels[f]}")
        lines.append(info[f]["value"] if f in info else "_Not provided_")
        lines.append("")
    lines += [
        "## Services Purchased",
        ", ".join(state["services"]),
        "",
        "## Documents Received",
    ]
    lines += [f"- {d['filename']} ({d['chars']} chars extracted)" for d in state["documents"]] or ["- None"]
    lines += ["", "## Important Notes"]
    notes = []
    if missing:
        notes.append(f"Still missing before activation: {', '.join(labels[f] for f in missing)}.")
    if not state["documents"]:
        notes.append("No brand documents were uploaded.")
    if state["onboarding_complete"]:
        notes.append(f"Onboarding completed at {state['completed_at']}.")
    lines += notes or ["- Nothing outstanding, client is fully onboarded."]
    lines.append("")

    path = config.BRIEFS_DIR / f"{state['client_id']}_brief.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    state["brief_path"] = str(path)
    store.save_state(state)
    store.log_activity(f"Agent generated client brief -> {path.name}")
    return {"ok": True, "brief_path": str(path), "brief": "\n".join(lines), "missing": missing}


# ── Tool 7 ──────────────────────────────────────────────────────────────────
TASK_TEMPLATES = [
    "Review {client} brand guidelines and extract do's/don'ts for the content team",
    "Prepare initial content strategy for {client}",
    "Create the first social media calendar for {client}",
    "Review {client} competitors and summarise positioning opportunities",
    "Set up {client} social accounts and grant the agency access",
    "Draft 5 launch content pieces for {client}",
]


def create_tasks() -> dict:
    state = _state()
    tasks = store.load_tasks()
    existing = {t["title"] for t in tasks if t.get("client_id") == state["client_id"]}
    created = []
    for template in TASK_TEMPLATES:
        title = template.format(client=state["business_name"])
        if title in existing:
            continue
        task = {
            "id": f"task_{len(tasks) + 1:03d}",
            "client_id": state["client_id"],
            "title": title,
            "status": "todo",
            "owner": "account-manager",
            "created_at": store.now_full(),
        }
        tasks.append(task)
        created.append(task)
    store.save_tasks(tasks)
    state["tasks_created"] = True
    store.save_state(state)
    store.log_activity(f"Agent created {len(created)} internal tasks")
    return {"ok": True, "created": created, "total_tasks": len(tasks), "tasks_file": str(config.TASKS_FILE)}


# ── Tool 8 ──────────────────────────────────────────────────────────────────
def complete_onboarding() -> dict:
    state = _state()
    missing = [f for f in REQUIREMENTS if f not in state["information"]]
    if missing:
        store.log_activity(f"Agent blocked: onboarding incomplete, missing {len(missing)}")
        return {"ok": False,
                "error": "Cannot complete onboarding, still missing: " + ", ".join(missing)}
    if not state.get("brief_path"):
        return {"ok": False, "error": "Generate the client brief before completing onboarding."}
    if not state.get("tasks_created"):
        return {"ok": False, "error": "Create the internal tasks before completing onboarding."}
    state["onboarding_complete"] = True
    state["completed_at"] = store.now_full()
    store.save_state(state)
    store.log_activity("Onboarding completed for " + state["business_name"])
    return {"ok": True, "completed_at": state["completed_at"], "brief_path": state["brief_path"]}


# ── Plain-text helpers for /status and /brief ───────────────────────────────
def status_text() -> str:
    status = get_status()
    state = _state()
    head = f"**{state['business_name']} — Onboarding**"
    body = [head, "", f"Progress: {status['percent']}% {'✅' if status['onboarding_complete'] else ''}",
            f"Completed: {status['progress']}", ""]
    if status["completed"]:
        body.append("✅ Got it:")
        body += [f"  ✓ {f.replace('_', ' ').title()}" for f in status["completed"]]
        body.append("")
    if status["missing"]:
        body.append("Still needed:")
        body += [f"  • {f.replace('_', ' ').title()}" for f in status["missing"]]
    else:
        body.append("Nothing outstanding 🎉")
    return "\n".join(body)


def brief_text() -> str:
    state = _state()
    if state.get("brief_path") and Path(state["brief_path"]).exists():
        return Path(state["brief_path"]).read_text(encoding="utf-8")
    res = generate_client_brief()
    return res["brief"]


# ── JSON schemas handed to the LLM ──────────────────────────────────────────
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_requirements",
        "description": "List the onboarding fields this client must provide.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "save_information",
        "description": "Persist one onboarding field. Call once per fact. Only save real info.",
        "parameters": {"type": "object", "properties": {
            "field": {"type": "string", "enum": list(REQUIREMENTS)},
            "value": {"type": "string", "description": "Verbatim-ish summary of what the client actually said"},
            "source": {"type": "string", "description": "client message | document"},
        }, "required": ["field", "value"]}}},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Completed fields, missing fields and completion percentage.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "request_missing_information",
        "description": "Pick the next thing to ask the client for and return a short ask.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "How many fields to ask about now (1-3, default 2)"},
            "focus": {"type": "string", "description": "Optional field key to ask about first"},
        }}}},
    {"type": "function", "function": {
        "name": "process_document",
        "description": "Process a document the client uploaded (PDF/DOCX/TXT/image). Returns extracted text.",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string"},
            "original_name": {"type": "string"},
            "client_message": {"type": "string", "description": "Caption the client sent with the file"},
        }}}},
    {"type": "function", "function": {
        "name": "generate_client_brief",
        "description": "Render the internal client brief markdown from everything collected.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "create_tasks",
        "description": "Create the internal agency task list for this client.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "complete_onboarding",
        "description": "Mark onboarding complete. Only succeeds when all fields are collected, the brief exists and tasks exist.",
        "parameters": {"type": "object", "properties": {}}}},
]

DISPATCH = {
    "get_requirements": get_requirements,
    "save_information": save_information,
    "get_status": get_status,
    "request_missing_information": request_missing_information,
    "process_document": process_document,
    "generate_client_brief": generate_client_brief,
    "create_tasks": create_tasks,
    "complete_onboarding": complete_onboarding,
}


def call_tool(name: str, args: dict) -> dict:
    fn = DISPATCH.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as exc:
        return {"ok": False, "error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:
        store.log_activity(f"Agent tool {name} error: {type(exc).__name__}: {exc}")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}