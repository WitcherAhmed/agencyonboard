"""Local harness: runs the SAME agent over plain stdin/stdout, no Telegram.

This is not a fake Telegram interface — it is the identical agent.handle_message()
loop, used to rehearse the demo and to debug without a bot token. Useful for
verifying tool calls really mutate data/.
"""
import sys
from pathlib import Path

import agent
import config
import store
import tools


def banner(title: str) -> None:
    print("\n" + "=" * 66)
    print(f"  {title}")
    print("=" * 66)


def main() -> None:
    config.ensure_dirs()
    banner("AgencyOnboard — local agent harness (no Telegram)")
    print(f"  client   : {config.CLIENT_NAME}")
    print(f"  model    : {config.LLM_MODEL}")
    print(f"  endpoint : {config.LLM_BASE_URL}  key={config.redact_key(config.LLM_API_KEY)}")
    print(f"  state    : {config.client_file(config.CLIENT_ID)}")

    print("\n  commands: /status  /brief  /tasks  /reset  /file <path>  /quit")
    if "--start" in sys.argv:
        print("\n[AGENT -> CLIENT]\n" + agent.start_onboarding())

    while True:
        try:
            line = input("\n[CLIENT] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        low = line.lower()
        if low in ("/quit", "/exit"):
            break
        if low == "/reset":
            store.save_state(store.blank_state(config.CLIENT_ID))
            store.save_tasks([])
            print("[AGENT] state reset\n" + agent.start_onboarding())
            continue
        if low == "/status":
            print(tools.status_text())
            continue
        if low == "/brief":
            print(tools.brief_text())
            continue
        if low == "/tasks":
            for t in store.load_tasks():
                print(f"  {t['id']}  {t['title']}  [{t['status']}]")
            continue
        attachment = None
        if low.startswith("/file"):
            parts = line.split(maxsplit=1)
            path = Path(parts[1].strip().strip('"')) if len(parts) > 1 else None
            if not path or not path.exists():
                print("[AGENT] file not found:", path)
                continue
            attachment = {"path": str(path), "name": path.name}
            text = "(no text, just the file)"
        else:
            text = line

        reply, trace = agent.handle_message(text, attachment=attachment)
        print(f"\n[AGENT -> CLIENT]\n{reply}")
        if trace:
            print(f"\n[TOOLS CALLED] {' -> '.join(trace)}")
        _maybe_close()

    banner("Activity log")
    if config.ACTIVITY_FILE.exists():
        print(config.ACTIVITY_FILE.read_text(encoding="utf-8"))


def _maybe_close() -> None:
    state = store.load_state()
    if state["onboarding_complete"]:
        print("\n[AGENT] ✅ Onboarding complete. Brief: " + str(state.get("brief_path")))


if __name__ == "__main__":
    main()
