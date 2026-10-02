"""End-to-end rehearsal: drives the real agent exactly as Telegram would.

  python rehearse.py           -> full happy-path demo (real LLM, real tools, real files)
  python rehearse.py fast      -> deterministic tool-only smoke test, no LLM

This is the pre-flight check before a live demo: if it passes here, the same
calls will fire from Telegram.
"""
import sys
import time
from pathlib import Path

import agent
import config
import store
import tools

SAMPLE_PDF = config.SAMPLE_DIR / "CairoBeans_BrandGuidelines.pdf"

SCRIPT = [
    ("We're a specialty coffee shop in New Cairo, New Administrative Capital. We roast in small batches and teach people what they're tasting.", None),
    ("Most of our customers are university students (18-25) and young professionals who work nearby. They care about where the beans come from.", None),
    ("Our goal this quarter is to grow Instagram to 5k followers and get people to walk in. Second place is our cold brew in summer.", None),
    ("Here's our brand guidelines, hope that helps!", SAMPLE_PDF),
    ("Sure — our menu is on the guidelines doc mostly. The signatures are the Caramel Latte and the Single Origin V60. We also do cold brew in summer.", None),
    ("Our handles are @cairobeans on Instagram and TikTok, and we're on Facebook as Cairo Beans Roastery. You won't have posting access yet, the owner has it.", None),
    ("Competitors? We're up against Roots and Beans in New Cairo, and honestly I love what Sofra does on social.", None),
    ("I want short-form video, reels mostly, 3-4 a week. Behind the scenes at the roaster would be great. Absolutely no discount spam please, and never call us 'the best coffee in Cairo'.", None),
    ("Also we uploaded our logo files, use logo_dark.svg on light backgrounds.", None),
]


def banner(t):
    print("\n" + "=" * 70 + f"\n  {t}\n" + "=" * 70, flush=True)


def run() -> int:
    store.save_state(store.blank_state(config.CLIENT_ID))
    store.save_tasks([])
    config.ACTIVITY_FILE.write_text("", encoding="utf-8")

    banner("AGENCY SIDE: onboarding started")
    print("[AGENT -> CLIENT]\n" + agent.start_onboarding(), flush=True)

    for i, (text, attach) in enumerate(SCRIPT, 1):
        banner(f"CLIENT TURN {i}/{len(SCRIPT)}" + (f"  (uploads {attach.name})" if attach else ""))
        print(f"[CLIENT] {text}\n", flush=True)
        t0 = time.time()
        reply, trace = agent.handle_message(text, attachment=(
            {"path": str(attach), "name": attach.name} if attach else None))
        print(f"[AGENT -> CLIENT] ({time.time() - t0:.1f}s)\n{reply}\n", flush=True)
        print(f"[TOOLS] {' -> '.join(trace)}\n", flush=True)
        state = store.load_state()
        if state["onboarding_complete"]:
            print("*** onboarding_complete = True", flush=True)

    banner("FINAL STATUS")
    print(tools.status_text())
    banner("CLIENT BRIEF")
    print(tools.brief_text())
    banner("INTERNAL TASKS")
    for t in store.load_tasks():
        print(f"  {t['id']}  [{t['status']}]  {t['title']}")
    banner("ACTIVITY LOG")
    print(config.ACTIVITY_FILE.read_text(encoding="utf-8"))
    return 0 if store.load_state()["onboarding_complete"] else 2


def fast() -> int:
    """No LLM: proves each tool really mutates data/."""
    store.save_state(store.blank_state(config.CLIENT_ID))
    store.save_tasks([])
    ok = True
    print("requirements:", tools.get_requirements()["count"])
    tools.save_information("audience", "University students", source="test")
    tools.save_information("targets", "Nope", source="test")
    s = tools.get_status()
    print("status after 2 saves:", s["progress"], "| completed:", s["completed"])
    print("ask for:", tools.request_missing_information(limit=2)["ask_for"])
    res = tools.process_document(str(SAMPLE_PDF))
    print("doc:", res["kind"], res["chars"], "chars")
    for f in ("brand_guidelines", "brand_voice", "products_menu"):
        tools.save_information(f, "from document", source="document")
    tools.save_information("business_description", "coffee shop")
    tools.save_information("marketing_goals", "grow instagram")
    tools.save_information("social_accounts", "@cairobeans")
    tools.save_information("logo_assets", "logo_dark.svg")
    tools.save_information("competitors", "Roots and Beans")
    tools.save_information("content_preferences", "reels")
    print("blocked completion:", tools.complete_onboarding()["ok"])
    print("brief:", tools.generate_client_brief()["ok"])
    print("tasks:", len(tools.create_tasks()["created"]))
    print("complete:", tools.complete_onboarding()["ok"])
    ok = store.load_state()["onboarding_complete"]
    print("state file:", config.client_file(config.CLIENT_ID).exists(),
          "| tasks file:", config.TASKS_FILE.exists())
    store.save_state(store.blank_state(config.CLIENT_ID))
    store.save_tasks([])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(fast() if "--fast" in sys.argv else run())