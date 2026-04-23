# Project Context — Amazon Price Drop Monitor

## The brief (short version)

Build an application that monitors the price of ≥3 Amazon product URLs on a
configurable interval, persists every check durably, detects price drops,
sends a notification, and exposes price history via a visualization. Target
effort: 2–4 hours of AI-assisted coding. **MVP FIRST.**

Evaluated on: functionality, design clarity, failure handling, data model,
separation of concerns, AI collaboration, readability.

---

## Architecture

A scheduled fan-in / fan-out around a shared SQLite store, running as
**one process**.

```
  python -m price_monitor
         │
         ▼
  ┌──────────────────────────────┐
  │  uvicorn process             │
  │                              │
  │  ├─ FastAPI (main thread)    │  ← reviewer hits localhost:8000
  │  │                           │
  │  └─ APScheduler (threads)    │  ← ticks every N minutes
  │                              │
  │  both read/write same .db    │  ← SQLite WAL mode
  └──────────────────────────────┘
```

**Write path (every tick):** Scheduler → Scraper → Storage (always write the
check, success or failure) → Detector (only if scrape ok) → Notifier (only
if drop) → Storage (record notification).

**Read path (independent):** Storage → Dashboard. Dashboard reads the same
SQLite file; WAL mode lets reads and writes happen concurrently.

**Three tables:**
- `products` — seeded from config at startup.
- `price_checks` — every scrape attempt with a `status` column.
- `notifications` — every drop alert fired, with `delivered` + `error`.

---

## Observability — logging vs persisted state

Two channels, split **by consumer, not by severity.**

- **Tables = durable outcomes the app reads later.** Scrape attempts,
  notification events. Queryable by the dashboard and the detector.
- **Logs = transient behavior a human reads now.** Startup, config load,
  per-retry attempts, request timings, scheduler ticks, uncaught exceptions.
  Go to stdout as structured lines.

A scrape failure appears in BOTH — the DB row tells the dashboard what
happened; the log line tells the terminal observer what's happening now.

**Never create an `errors`/`events`/`logs` table** — it duplicates
`price_checks.status` for per-tick failures and can't hold outside-tick
errors (config load failure has no product_id).

---

## Core requirements — what MUST ship

1. ≥3 Amazon URLs, configurable without code change.
2. Periodic checks on a configurable interval.
3. Durable history that survives restart.
4. Drop detection with configurable threshold (percentage).
5. Notification — ConsoleNotifier (default) + ToastNotifier (desktop OS
   notification via `plyer`). Both zero-external-config.
6. Per-product history visualization on a local web page.
7. Configurable: product list, interval, threshold, notification channel.
8. Structured logging for every check and notification.
9. Individual check failures do not stop the system.
10. One meaningful test per layer.

---

## Deliverables at end of 4 hours

1. GitHub repo with 8–12 commit history on `main`.
2. `README.md` — install, configure, run, verify, test.
3. `DESIGN.md` — 1 page, ≥3 tradeoffs, what wasn't handled, 10x paragraph.
4. `AI-NOTES.md` — one specific AI miss, how it was caught, how it was fixed.

---

## Language — Python, not Java

Brief says Java preferred but NOT a language test. Python chosen because
Java's 4-hour cost is dominated by scaffolding (build tool config, HTTP
client boilerplate, JDBC wiring) that demonstrates nothing about judgment.
Architecture translates directly to Java. Name this explicitly in DESIGN.md.

---

## The three tradeoffs for DESIGN.md

1. **Scraping strategy.** Raw httpx + selectolax vs. paid scraping API
   (ScraperAPI, Zyte) vs. Playwright headless. Chose raw for time budget
   and zero external dependencies; flagged that a paid API is the real
   production answer for ToS compliance and bot-block resilience.
2. **Storage.** SQLite vs. Postgres vs. time-series DB. Chose SQLite for
   zero ops, stdlib inclusion, WAL concurrent reads. At 10x stay on SQLite.
   At 100x move to Postgres. At 1000x move history table to Timescale.
3. **Scheduler.** APScheduler in-process vs. cron + one-shot script vs.
   Celery/RQ. Chose in-process for simplicity and shared DB handle;
   flagged that scheduler and dashboard share a lifecycle, which a
   production deployment would split.

---

## Stage-by-stage build plan

Each stage produces a working, committable state. If a stage runs long,
cut scope — never spill into the next stage.

---

### Stage 1 — Scaffold + Storage (target 60 min)

**Goal:** empty-to-working persistence layer with tests green. Nothing
runs end-to-end yet.

**Order of operations:**
1. Create repo, `cd` in.
2. Drop `.cursorrules` and `PROJECT_CONTEXT.md` at root.
3. `python -m venv .venv && source .venv/bin/activate`
4. Create `pyproject.toml` with locked stack. Create `.gitignore`.
5. Create `src/price_monitor/__init__.py`, `models.py`, `config.py`,
   `storage.py`.
6. Create `config.example.yaml` with 3 Amazon URLs.
7. Create `tests/conftest.py` and `tests/test_storage.py`.
8. `pip install -e .`

**`.gitignore` must cover:** `.venv/`, `__pycache__/`, `*.pyc`, `*.db`,
`*.db-wal`, `*.db-shm`, `.env`, `config.yaml`, `.cursor/plans/`.

**Storage API:**
- `__init__(db_path)` — runs schema if not exists, enables WAL + FK
- `upsert_product(url, name) -> int`
- `list_products() -> list[Product]`
- `save_check(product_id, result: ScrapeResult) -> int`
- `get_last_ok_price(product_id, exclude_check_id=None) -> float | None`
- `get_history(product_id, days=30) -> list[dict]`
- `save_notification(event, delivered: bool, error=None) -> int`
- `recent_notifications(limit=10) -> list[dict]`

**Tests (4):**
1. Upsert product, read back.
2. Save OK check + save failed check; `get_last_ok_price` ignores failure.
3. `get_last_ok_price` with `exclude_check_id` returns prior row.
4. Save notification with `delivered=False`, read back.

**Sanity check:**
```bash
pytest tests/test_storage.py -v
```
Expected: 4 pass. Also verify with one-liner in REPL:
```python
from price_monitor.storage import Storage
s = Storage("/tmp/smoke.db")
# insert a product and a check, query last ok price
```

**Transition gate — all must be true to move on:**
- [ ] `pytest` passes (4 tests)
- [ ] One commit on `main`: "storage layer with tests"
- [ ] `config.example.yaml` exists with 3 real Amazon URLs
- [ ] Schema has `products`, `price_checks`, `notifications` tables
- [ ] `git status` shows nothing unexpected — no `.db`, no `config.yaml`

**Likely failure:** Tests pass individually, fail together → shared DB
file. Fix with `tmp_path` fixture. 2 min.

---

### Stage 2 — Scraper + Detector + Notifier (target 75 min)

**Goal:** three pipeline modules operating on a single URL, unit-tested.
Still no end-to-end run.

**Order of operations:**
1. Write `scraper.py` — `fetch_price(url)` with classification, then
   `fetch_with_retry`.
2. Save `tests/fixtures/product.html` (real Amazon response — View Source,
   save). Save `tests/fixtures/bot_check.html` if you can provoke it by
   scraping without a User-Agent.
3. Write `detector.py` — pure functions, no I/O.
4. Write `notifier.py` — `ConsoleNotifier` + `ToastNotifier`.
5. Write the three test files.

**Scraper classification — one of:**
`OK`, `NETWORK_ERROR`, `HTTP_ERROR`, `BOT_DETECTED`, `PARSE_ERROR`,
`PRICE_INVALID`. Never raises — returns `ScrapeResult` with error status.

**Selectors, in priority order:**
```python
AMAZON_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    ".a-price .a-offscreen",
]
BOT_SIGNATURES = [
    "robot check", "/errors/validatecaptcha",
    "enter the characters you see",
    "api-services-support@amazon",
]
```

**Retry policy:** `fetch_with_retry(url, max_attempts=3)`. Retries
NETWORK_ERROR and HTTP_ERROR only, with jittered exponential backoff
(`2**attempt + random(0..1)`). Other failure categories return immediately.

**Notifier Protocol:**
```python
class Notifier(Protocol):
    def send(self, event: PriceDropEvent) -> None: ...
```
Implementations: `ConsoleNotifier` (logs + prints banner, always works),
`ToastNotifier` (calls `plyer.notification.notify`, cross-platform,
wraps in try/except). Factory: `build_notifier(channel: str) -> Notifier`.

**Tests:**
- `test_scraper.py` — 3 fixture-based tests (normal / bot / unparseable)
- `test_detector.py` — 5+ (threshold boundary inclusive, below threshold,
  price went up, prev=0, equal prices)
- `test_notifier.py` — 2 (ConsoleNotifier writes expected log, factory
  returns correct class)

**Sanity checks:**
```bash
pytest -v
```
Expected: ~12 tests pass total.

```bash
python -c "from price_monitor.scraper import fetch_with_retry; print(fetch_with_retry('https://www.amazon.com/dp/B08N5WRWNW'))"
```
Expected: `ScrapeResult(status=OK, price=<float>, ...)` or
`status=BOT_DETECTED`. Either is acceptable. `PARSE_ERROR` means your
selectors are wrong — fix before moving on.

**Transition gate:**
- [ ] All tests pass
- [ ] Real URL smoke test returns OK or BOT_DETECTED (no uncaught exception)
- [ ] ConsoleNotifier prints banner when called directly
- [ ] 4–5 commits on `main`

**Likely failure:** First real GET returns 200 with bot-check body because
default httpx User-Agent is `python-httpx/x.x`. Set realistic `Mozilla/...`
header. Save bot-check body as a fixture while you have it.

---

### Stage 3 — Scheduler + Dashboard + End-to-End (target 75 min)

**Goal:** `python -m price_monitor` starts everything; dashboard at
`localhost:8000` renders; drop notifications fire.

**Order of operations:**
1. Write `scheduler.py` — `check_product` tick function, `run_all_checks`
   iterator, `build_scheduler` factory with `max_instances=1` and
   `misfire_grace_time=60`.
2. Write `dashboard.py` — FastAPI app. `GET /` renders Jinja template;
   `GET /api/history/{product_id}?days=30` returns JSON.
3. Write `templates/index.html` — Chart.js from jsdelivr CDN, one canvas
   per product, "Recent drops" panel from `recent_notifications`.
4. Write `main.py` — load config, open Storage (runs schema), upsert
   products, build notifier, create FastAPI app with scheduler in lifespan,
   `uvicorn.run`.
5. Write `src/price_monitor/__main__.py` so `python -m price_monitor` works.

**The critical wire-up pattern** — scheduler must be in FastAPI's lifespan
to ensure scheduler and web server share one process lifecycle:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    log.info("scheduler_started", extra={"interval_min": cfg.interval})
    yield
    scheduler.shutdown(wait=False)
    log.info("scheduler_stopped")
```

**Every tick wraps exceptions at the outer level:**
```python
def run_all_checks(storage, config, notifier):
    for product in storage.list_products():
        try:
            check_product(product, storage, notifier, config.threshold_pct)
        except Exception:
            log.exception("tick_failed_unexpectedly", extra={"product_id": product.id})
```
A scheduler whose jobs can die is worse than useless.

**Sanity checks — this is where end-to-end is validated:**

Forcing a drop to fire fast (instead of waiting an hour) — seed a fake
high prior price so the next real scrape registers as a drop:

```bash
# with app NOT running:
sqlite3 price_monitor.db "INSERT INTO price_checks (product_id, checked_at, status, price, currency, attempts) VALUES (1, '2026-01-01T00:00:00+00:00', 'ok', 9999.99, 'USD', 1);"

# set short interval and low threshold in config.yaml:
#   check_interval_minutes: 1
#   drop_threshold_pct: 0.01

python -m price_monitor
# wait 1 minute, watch logs
```

Expected to see:
1. `scheduler_started` at boot
2. `tick_started` within 1 minute
3. `check_completed` with `status=ok` (or bot_detected — still fine)
4. `drop_detected` + `PRICE_DROP` log + banner printed to stdout
5. `tick_complete` with counts
6. Dashboard at `http://localhost:8000` shows chart with data points
7. `curl localhost:8000/api/history/1` returns JSON
8. `Ctrl+C` → `scheduler_stopped` logs → clean exit

**Scope cut triggers — cut in this order if running long:**
- If minute 40 and scheduler isn't firing → replace APScheduler with
  `threading.Timer` or `while True: run_all_checks(); time.sleep(interval)`.
  Name in DESIGN.md.
- If minute 50 and Chart.js won't render → replace with matplotlib PNG
  per product, render with `<img>` tag.
- If minute 55 and anything else broken → commit what works, move to Hour 4.

**Transition gate:**
- [ ] `python -m price_monitor` starts without errors
- [ ] Dashboard renders at `localhost:8000`
- [ ] At least one tick fired and wrote to DB
- [ ] At least one drop notification triggered and logged
- [ ] `Ctrl+C` stops cleanly
- [ ] 7–9 commits on `main`

---

### Stage 4 — Docs + Fresh-Clone + Polish (target 30 min)

**Goal:** a reviewer clones, runs, and verifies with zero friction.

**Order of operations (~7 min each):**

**1. `README.md`** — sections:
- Overview (2 paragraphs)
- Requirements (Python 3.11+)
- Install: `pip install -e .`
- Configure: `cp config.example.yaml config.yaml`
- Run: `python -m price_monitor` → dashboard at `localhost:8000`
- Verify: seed high price into DB, set short interval, watch notification
- Test: `pytest`
- Note: "No database setup required — `price_monitor.db` creates on first run"

**2. `DESIGN.md`** — 1 page:
- One-paragraph system overview
- Three tradeoffs (language, scraping, storage)
- "What I didn't handle and why" — bot detection at scale, idempotency on
  crash between notify-and-persist, concurrent process safety
- "At 10x scale" paragraph

**3. `AI-NOTES.md`** — go back through your Cursor session, find the ONE
specific moment. Candidates to check:
- Agent suggested `requests` → you swapped for `httpx`
- Agent used obsolete selector like `#priceblock_ourprice`
- Agent wrote `datetime.now()` without tz
- Agent used naive UA and first scrape hit bot-check
- Agent forgot `exclude_check_id` in `get_last_ok_price`, comparing a
  price to itself
- Agent started `BackgroundScheduler` in a script that exits

6–10 sentences. Specific beats polished.

**4. Fresh-clone dry run** — single highest-value step in Hour 4:
```bash
cd /tmp && rm -rf clone-test
git clone <your-repo> clone-test && cd clone-test
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
pytest
python -m price_monitor
# open localhost:8000, verify
```
Every error hit becomes a README line.

**5. `.gitignore` audit:** `git status` on the clone should be empty.
`find . -name "*.db"` finds nothing tracked. No secrets anywhere.

**6. Final commit:** "docs: README, DESIGN, AI-NOTES"

**7. Push to GitHub**, verify public or Levi has access, send the link.

**End-state transition gate:**
- [ ] Fresh clone runs with documented commands
- [ ] 9–12 commits on `main`
- [ ] No secrets, no DB files, no `.venv`, no `config.yaml` in repo
- [ ] `README`, `DESIGN`, `AI-NOTES` all present and readable
- [ ] Tests pass on the clone

---

## One-command startup (for README and your own use)

```bash
# one-time setup
git clone <repo>
cd price-monitor
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml

# run (scheduler + dashboard both in this terminal)
python -m price_monitor
# → open http://localhost:8000
# → Ctrl+C to stop

# run tests (separate terminal, same venv)
pytest
```

No Docker, no separate worker, no Redis, no supervisord. One process,
one command, one `Ctrl+C`. **The simplicity is a feature** — it's what
lets you say in the panel: "I picked in-process scheduling because a
reviewer verifies end-to-end in 30 seconds; the tradeoff is that
scheduler and dashboard share a lifecycle, which I'd split in production."

---

## Commit plan (target 8–12 on `main`)

1. `scaffold: pyproject, gitignore, models, config schema`
2. `storage: SQLite layer with WAL + tests`
3. `scraper: httpx fetch with fallback selectors and classification`
4. `scraper: retry-with-backoff for transient failures`
5. `detector: pure drop-detection functions + tests`
6. `notifier: Console and Toast implementations`
7. `scheduler: APScheduler tick orchestration`
8. `dashboard: FastAPI + Chart.js per-product history`
9. `main: wire scheduler into FastAPI lifespan`
10. `docs: README, DESIGN, AI-NOTES`

---

## Panel prep — what to defend

- **The three tradeoffs** in DESIGN.md.
- **"One place your solution could break that you knew about and left
  alone":** Amazon bot detection at scale — solved structurally (classify
  + never false-alert) but not solved at source. Real fix costs money.
- **"One place you learned something unexpected":** how many distinct
  failure modes a single HTTP GET can produce (5+ classes, each needing
  different handling), OR how much of "production-quality Python" is
  packaging discipline vs. code.
- **AI-NOTES entry in detail.**

---

## Meta-rule for all 4 hours

At the end of each hour, you have a committable, working state. If
something is broken at :55, commit what works and cut the remaining
scope. **Never start Hour N+1 with unfinished Hour N code** — failure
modes compound.
