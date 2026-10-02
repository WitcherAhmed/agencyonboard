"""Entry point.

  python main.py bot       -> run the Telegram bot (real Telegram, long polling)
  python main.py cli       -> local agent harness (same agent, no Telegram)
  python main.py demo      -> scripted end-to-end demo run (real agent, no Telegram)
  python main.py metrics   -> impact numbers measured from the activity log
  python main.py greet     -> send the opening greeting to CLIENT_CHAT_ID now
  python main.py status    -> print onboarding status
  python main.py brief     -> print the client brief
  python main.py log       -> print the activity log
  python main.py reset     -> wipe the demo client state and tasks
"""
import sys
import time

import config
import store
import tools


def send(text: str) -> None:
    import urllib.request
    import urllib.parse
    url = (f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
           f"/sendMessage?chat_id={config.CLIENT_CHAT_ID}&parse_mode=Markdown"
           f"&disable_web_page_preview=true")
    data = urllib.parse.urlencode({"text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as r:
            print("   [telegram] sent:", r.read().decode()[:120])
    except Exception as exc:
        detail = getattr(exc, "read", lambda: b"")().decode("utf-8", "replace")[:300]
        raise SystemExit(f"Telegram send failed: {exc} {detail}")


def main() -> None:
    config.ensure_dirs()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cli"

    if cmd == "bot":
        if not config.TELEGRAM_BOT_TOKEN:
            raise SystemExit("TELEGRAM_BOT_TOKEN missing. Copy .env.example to .env and paste your bot token.")
        import telegram_bot
        telegram_bot.run()
    elif cmd == "cli":
        import cli
        cli.main()
    elif cmd == "greet":
        if not (config.TELEGRAM_BOT_TOKEN and config.CLIENT_CHAT_ID):
            raise SystemExit("Need TELEGRAM_BOT_TOKEN and CLIENT_CHAT_ID in .env")
        import agent
        send(agent.start_onboarding())
    elif cmd == "status":
        print(tools.status_text())
    elif cmd == "brief":
        print(tools.brief_text())
    elif cmd == "metrics":
        import metrics
        metrics.main()
    elif cmd == "demo":
        # One-command, no-Telegram proof for judges: drives the real agent
        # through a full Cairo Beans onboarding and prints the results.
        import rehearse
        raise SystemExit(rehearse.run())
    elif cmd == "log":
        print(config.ACTIVITY_FILE.read_text(encoding="utf-8") if config.ACTIVITY_FILE.exists() else "no log yet")
    elif cmd == "reset":
        store.save_state(store.blank_state(config.CLIENT_ID))
        store.save_tasks([])
        if config.ACTIVITY_FILE.exists():
            config.ACTIVITY_FILE.write_text("", encoding="utf-8")
        print("state reset")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()