"""The agent loop: message in -> tool calls -> real state changes -> message out.

This module knows nothing about Telegram. It takes text (and optional files),
and returns the reply plus a trace of everything it actually did.
"""
import base64
import json
from typing import Any, Dict, List, Optional, Tuple

import config
import llm
import store
import tools

MAX_TOOL_ROUNDS = 12
HISTORY_LIMIT = 24

SYSTEM = """You are the onboarding agent for a marketing agency. You are onboarding a NEW CLIENT \
into the agency's system. You talk to the client directly on Telegram.

CLIENT: {client}
SERVICES PURCHASED: {services}

YOUR JOB, every time the client messages you:
1. Decide whether the message contains useful onboarding information.
2. Call save_information() ONCE PER FACT. If the client answered three things at once, save all three.
3. Call get_status() to see what is genuinely still missing.
4. Call request_missing_information() and ask for the next most useful thing (1-2 fields, never a form).
5. Reply in your own words: short, warm, human, 1-4 sentences. Use at most one emoji.

HARD RULES
- NEVER ask for something you have already saved. Check get_status() before every question.
- NEVER say you saved, processed, generated or created anything unless the tool call actually succeeded.
- NEVER invent facts about the client. If something is unknown, it stays unknown.
- Only record values the client actually stated or that appear in a document they sent.
- If the client sends irrelevant text, chat back briefly and steer to the next missing field.
- If the client answers a different field than you asked about, save it happily and move on.
- After process_document() returns text, you MUST call save_information() for every onboarding
  fact the document actually contains before you reply. A document turn with zero saves is a failure.
- Never reply without at least calling get_status() or request_missing_information(), so you always
  know what is still missing.
- Keep replies short. This is a Telegram chat, not an email.

WHEN NOTHING IS MISSING ANYMORE
- Call generate_client_brief(), then create_tasks(), then complete_onboarding().
- Confirm it to the client and tell them the agency team has everything.

FIELDS YOU CAN SAVE
{fields}

Start with get_requirements() and get_status() before your first question."""


def _system() -> str:
    state = store.load_state()
    fields = "\n".join(f"- {k}: {v}" for k, v in tools.REQUIREMENTS.items())
    return SYSTEM.format(
        client=state.get("business_name", config.CLIENT_NAME),
        services=", ".join(state.get("services", config.CLIENT_SERVICES)),
        fields=fields,
    )


def _state() -> Dict[str, Any]:
    return store.load_state()


def _history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return state["history"][-HISTORY_LIMIT:]


def start_onboarding() -> str:
    """Agency-side kickoff: seed state, greet the client."""
    config.ensure_dirs()
    state = store.load_state()
    if not state["history"]:
        state["history"].append(
            {"role": "assistant", "content":
             f"Welcome! I'm the onboarding assistant for {state['business_name']}. "
             f"I'll gather everything our {', '.join(state['services'])} team needs.",
             "ts": store.now_full()}
        )
    store.save_state(state)
    store.log_activity("Agency started onboarding for " + state["business_name"])

    greeting = (
        f"Hey! 👋 Welcome to {state['business_name']}'s onboarding.\n\n"
        "I'll collect everything our marketing team needs, so you don't have to fill out a giant "
        "boring questionnaire 😂\n\n"
        "We'll go a couple of questions at a time — just answer however you like. You can also "
        "drop files (brand guidelines, menu, logo) here whenever you're ready.\n\n"
        "First: tell me a little about the business."
    )
    store.log_activity("Agent sent opening greeting to client")
    return greeting


def _encode_image(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    except Exception:
        return None


def handle_message(text: str, attachment: Optional[dict] = None) -> Tuple[str, List[str]]:
    """Process one client turn.

    text: what the client wrote
    attachment: {"path": ..., "name": ...} for an uploaded file, else None

    Returns (reply_to_client, trace_of_tool_actions).
    """
    config.ensure_dirs()
    state = _state()
    trace: List[str] = []
    store.log_activity("Agent received client message" + (f" + file {attachment['name']}" if attachment else ""))

    user_msg: Dict[str, Any] = {"role": "user", "content": text or "(no text)"}
    if attachment:
        user_msg["content"] += (
            f"\n\n[client uploaded a file. filename: {attachment['name']}"
            f"\nlocal path — call process_document(file_path=\"{attachment['path']}\","
            f" original_name=\"{attachment['name']}\") with this exact path]"
        )
    state["history"].append({**user_msg, "ts": store.now_full()})
    state["pending_attachment"] = attachment
    store.save_state(state)

    pending_images: List[str] = []
    messages: List[Dict[str, Any]] = [{"role": "system", "content": _system()}]
    for turn in _history(_state()):
        messages.append({"role": turn["role"], "content": turn["content"]})
    if attachment and attachment["path"].lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        b64 = _encode_image(attachment["path"])
        if b64:
            pending_images.append(attachment["path"])
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": messages[-1]["content"] +
                     "\n\nI also uploaded this file, look at it now:"},
                    llm.image_part(b64),
                ],
            }

    reply = ""
    for round_no in range(MAX_TOOL_ROUNDS):
        try:
            resp = llm.chat(messages, tools=tools.TOOL_SCHEMAS)
        except RuntimeError as exc:
            store.log_activity(f"Agent LLM error: {exc}")
            return ("Sorry, my brain hiccuped for a second 🤖 — could you say that again?", trace)

        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        content = (msg.get("content") or "").strip()

        if not calls:
            reply = content or "Got it, thanks! I'll keep that."
            break

        messages.append({"role": "assistant", "content": content or None,
                         **({"tool_calls": calls} if calls else {})})
        for call in calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            store.log_activity(f"Agent called tool: {fn['name']}")
            result = tools.call_tool(fn["name"], args)
            trace.append(fn["name"])

            if fn["name"] == "process_document":
                img = result.get("image_path")
                if img:
                    b64 = _encode_image(img)
                    if b64:
                        pending_images.append(img)
                        messages.append({
                            "role": "user",
                            "content": [{"type": "text",
                                         "text": f"I extracted nothing as text from {result['filename']}. "
                                                 "Look at the image now and extract what's on it."},
                                        llm.image_part(b64)],
                        })

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": fn["name"],
                "content": json.dumps(result, ensure_ascii=False)[:12000],
            })
    else:
        reply = "That's a lot — give me one minute and I'll come back to you. 🙂"

    state = _state()
    state["history"].append({"role": "assistant", "content": reply, "ts": store.now_full()})
    state["history"] = state["history"][-(HISTORY_LIMIT * 2):]
    store.save_state(state)

    # Final sweep: if everything is in, let the agent close out the onboarding.
    if not state["onboarding_complete"]:
        status = tools.get_status()
        if not status["missing"] and state.get("brief_path") and state.get("tasks_created"):
            closing = _close_out(messages)
            if closing:
                reply = reply + "\n\n" + closing
    store.log_activity("Agent replied to client")
    return reply, trace


def _close_out(messages: List[Dict[str, Any]]) -> str:
    """Last mile: brief -> tasks -> complete_onboarding, guarded so it can't loop."""
    closing = ""
    for _ in range(3):
        try:
            resp = llm.chat(
                messages + ([{"role": "user", "content":
                              "Everything is collected. Call generate_client_brief(), then "
                              "create_tasks(), then complete_onboarding(), then confirm it to me."}]
                            if not closing else
                            [{"role": "user", "content": "Tools done. Now write the final confirmation message."}]),
                tools=tools.TOOL_SCHEMAS,
            )
        except RuntimeError:
            return ""
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            closing = (msg.get("content") or "").strip()
            break
        messages.append({"role": "assistant", "content": msg.get("content") or None,
                         "tool_calls": calls})
        for call in calls:
            tools.call_tool(call["function"]["name"],
                            json.loads(call["function"].get("arguments") or "{}"))
    state = _state()
    state["history"].append({"role": "assistant", "content": closing, "ts": store.now_full()})
    store.save_state(state)
    return closing