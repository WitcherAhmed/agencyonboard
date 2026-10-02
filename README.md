# AgencyOnboard — AI Client Onboarding Agent

An autonomous agent that onboards a new marketing-agency client **over real Telegram**:
it asks what's missing, stores what the client says, reads uploaded documents, generates an
internal client brief, creates agency tasks, and declares onboarding complete.

This is a hackathon MVP. No database, no auth, no dashboards. JSON files + one bot process.

---

## 1. Judge quickstart — working agent in under 5 minutes

No Telegram account, no bot token, no setup beyond one API key.

```bash
git clone <your-repo-url> agency_onboard && cd agency_onboard
python -m pip install -r requirements.txt

# any OpenAI-compatible key works (OpenRouter, Nous, OpenAI, Groq, ...)
# mac/linux: export LLM_API_KEY=sk-or-...      Windows: set it in .env
copy .env.example .env        # mac/linux: cp .env.example .env

python main.py demo
```

`main.py demo` drives the **real agent** through a full Cairo Beans onboarding — same
`agent.handle_message()` the Telegram bot uses — and prints the client brief, the created
tasks and the activity log. It exits 0 when onboarding completes.

```
python main.py demo         # full run with the model (~4 min)  <- what judges watch
python main.py metrics      # impact numbers measured from the log
python rehearse.py --fast   # instant proof every tool writes real files, no model needed
```

To drive it yourself as the client, interactively:

```bash
python main.py cli
```

```
[CLIENT] We're a specialty coffee shop in New Cairo, our customers are mostly students.
/file sample/CairoBeans_BrandGuidelines.pdf
/status
/brief
/quit
```

### Configuration

| Variable | Required | Notes |
|---|---|---|
| `LLM_API_KEY` | **yes** | any OpenAI-compatible provider key |
| `LLM_BASE_URL` | no | defaults to the Nous inference gateway; set for OpenRouter etc. |
| `AGENT_MODEL` | no | defaults to `stealth/space-bunny-alpha` |
| `TELEGRAM_BOT_TOKEN` | no | only needed for the Telegram path |
| `CLIENT_CHAT_ID` | no | blank = accept the first chat that messages the bot |
| `AGENT_MANUAL_BASELINE_MINUTES` | no | manual-onboarding baseline used by `metrics` (default 90) |

Nothing in the code is model-specific; the agent only speaks the OpenAI chat-completions
tool-calling shape.

---

## 2. Full Telegram setup

```bash
cd agency_onboard
python -m pip install -r requirements.txt
copy .env.example .env          # Windows: copy, mac/linux: cp
```

Edit `.env` and paste the token from **@BotFather**:

```
TELEGRAM_BOT_TOKEN=123456:ABC-your-token-here
CLIENT_CHAT_ID=                # leave blank at first; the bot accepts whoever messages it first
```

**Model**: `AGENT_MODEL` defaults to `stealth/space-bunny-alpha`. `LLM_BASE_URL` /
`LLM_API_KEY` fall back automatically to the Hermes credentials already configured on this
machine, so there is nothing else to set. To point at a different OpenAI-compatible endpoint,
set those two vars only — nothing in the code is model-specific.

## 3. Run

```bash
python main.py bot
```

Then open Telegram, message your bot (or `/start` it), and you are in the demo.
`python main.py greet` sends the opening message first if you already know `CLIENT_CHAT_ID`.

### Demo commands in Telegram

| Command | Effect |
|---|---|
| `/status` | Progress %, collected fields, what's still missing |
| `/brief` | The generated internal client brief |
| `/tasks` | The internal agency tasks |
| `/reset` | (admin) wipe the demo state and restart |

Client uploads (PDF / DOCX / TXT / XLSX / image) are downloaded, processed, and the facts
found inside are saved automatically.

## 4. What the agent actually does

Per client message, the LLM decides, then really executes:

```
client msg ──► LLM reasoning ──► tool calls ──► data/clients/cairo_beans.json
                    ▲                                    │
                    └──────────── next question ◄────────┘
```

The 8 tools (in `tools.py`) are deterministic functions that write real files:

| Tool | Real effect |
|---|---|
| `get_requirements()` | returns the 10 required onboarding fields for the purchased services |
| `save_information(field, value)` | persists one field into `data/clients/cairo_beans.json` (with source + timestamp) |
| `get_status()` | completed / missing / percentage, computed from the file |
| `request_missing_information(limit, focus)` | picks the next fields to chase and returns a short ask |
| `process_document(path)` | extracts text (pypdf / docx2txt / openpyxl / plain text) and hands the raw text to the agent; images are attached to the LLM's next turn for visual reading |
| `generate_client_brief()` | writes `data/briefs/cairo_beans_brief.md` |
| `create_tasks()` | appends 6 tasks to `data/tasks.json` (idempotent) |
| `complete_onboarding()` | only succeeds if all 10 fields are collected **and** the brief and tasks exist |

Two rules are enforced in code, not just in the prompt:
* `complete_onboarding()` returns `ok: False` with the missing list if anything is outstanding.
* `save_information()` rejects unknown fields and empty values, and records what changed.

## 5. Files

```
agency_onboard/
├── main.py            entry point: bot | cli | greet | status | brief | log | reset
├── telegram_bot.py    Telegram layer ONLY (no agent logic): text, files, photos, commands
├── agent.py           the agent loop: LLM + tool execution + close-out
├── tools.py           the 8 tools + JSON schemas
├── llm.py             OpenAI-compatible chat client with retries
├── store.py           atomic JSON persistence + activity log
├── document.py        PDF/DOCX/TXT/XLSX/image text extraction
├── cli.py             local harness — same agent, no Telegram (debug/rehearse)
├── rehearse.py        scripted end-to-end rehearsal; `--fast` for a no-LLM tool smoke test
├── sample/
│   ├── make_sample_pdf.py             builds the demo brand-guidelines PDF
│   └── CairoBeans_BrandGuidelines.pdf the file the client uploads in the demo
└── data/
    ├── clients/cairo_beans.json   onboarding state + conversation history
    ├── tasks.json                 internal agency tasks
    ├── activity.log               the visible action log
    ├── downloads/                 uploaded files
    └── briefs/cairo_beans_brief.md
```

## 6. Rehearse before you demo

```bash
python rehearse.py --fast   # seconds, no LLM: proves every tool mutates data/
python rehearse.py          # full run with the real model, prints brief + tasks + log
python main.py cli          # freeform chat with the agent locally
```

Both harnesses call the exact same `agent.handle_message()` the Telegram bot calls, so a green
rehearsal means the live demo will behave the same way.

## 7. Demo script (2–3 min)

1. `python main.py bot`, message the bot on Telegram.
2. Client: *"We're a specialty coffee shop in New Cairo, most of our customers are university
   students and young professionals."* → agent saves business description **and** target audience,
   never asks for them again.
3. Client: *"Here's our brand guidelines"* + uploads `CairoBeans_BrandGuidelines.pdf`
   → agent extracts 2,200+ chars, saves brand guidelines / voice / colours / menu.
4. `/status` → shows real completion %, real missing list.
5. Client answers the missing fields across 2–3 messages.
6. Agent: generates brief → creates 6 tasks → completes onboarding → tells the client.
7. Show `python main.py brief`, `/tasks`, and `data/activity.log`.

## 9. Measured impact

`python main.py metrics` reads `data/activity.log` and the client state file and prints the
numbers judges ask for. Measured on a real Telegram run:

| Measure | Value |
|---|---|
| Information fields collected | 10/10 |
| Wall-clock, first message to brief + tasks | 30 min |
| Same onboarding done manually (baseline) | 90 min |
| **Time returned to the agency** | **60 min (67%)** |
| Client messages needed | 7 |
| Agent tool calls executed | 38 |
| Documents parsed / characters extracted | 2 / 4,434 |
| Client brief / internal tasks generated | yes / 6 |

The 90-minute baseline is an assumption held in `AGENT_MANUAL_BASELINE_MINUTES`; replace it
with your agency's measured figure. `data/impact_report.md` is regenerated on every call.

## 8. Error handling

Irrelevant messages, unparseable documents, empty extractions, answers to the wrong question,
multi-field answers and LLM failures all degrade gracefully: the agent explains, asks for the
next missing field, and never claims an action it did not perform.