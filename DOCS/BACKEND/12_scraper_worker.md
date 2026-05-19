# `backend/app/services/scraper.py` + `worker.py` — Amazon Scraping System

## System Overview

The scraping system has three layers:

```
HTTP Request → scraping.py endpoint
                    │
                    ▼
              scraping_queue.py   ← In-memory queue (thread-safe)
                    │
                    ▼
              worker.py           ← Separate OS process (polls DB)
                    │
                    ▼
              scraper.py          ← Playwright headless Chrome
                    │
                    ▼
              models/scraping.py  ← ProductData saved to PostgreSQL
```

---

## `services/scraper.py` — Playwright Browser Automation

```python
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def scrape_amazon_asin(asin: str) -> dict:
    url = f"https://www.amazon.in/dp/{asin}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)   # headless = no visible window
        try:
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
            page = context.new_page()
            page.set_default_timeout(30_000)   # 30 seconds

            resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
```

### What Is Playwright?

Playwright is a **browser automation library** that controls a real Chromium browser.
Unlike `requests` (which fetches raw HTML), Playwright executes JavaScript, handles
cookies, and renders dynamic content — just like a real user's browser.

**Why Playwright for Amazon?**

Amazon renders prices and ratings via JavaScript after page load. Simple HTTP clients
(`requests`, `httpx`) get the initial HTML skeleton but miss dynamic content.
Amazon also implements sophisticated bot detection that Playwright bypasses by running
a real browser engine.

### Browser Context — Why Create a New Context?

```python
context = browser.new_context(
    user_agent=_USER_AGENT,    # Identifies as Chrome browser
    viewport={"width": 1280, "height": 900},  # Real screen size
    locale="en-IN",            # Indian locale
    extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
)
```

A **browser context** is like an incognito window — isolated cookies, storage, cache.
Each ASIN gets a fresh context with no cookies from previous scrapes.
This prevents Amazon from correlating sessions and triggering bot detection.

### CAPTCHA Detection

```python
if page.query_selector("form[action='/errors/validateCaptcha']") or \
   "captcha" in page.url.lower() or \
   "robot" in (page.title() or "").lower():
    raise RuntimeError(f"Amazon returned CAPTCHA for ASIN {asin}")
```

Three detection strategies:
1. **DOM check** — look for the CAPTCHA form element
2. **URL check** — Amazon redirects CAPTCHA to a URL containing "captcha"
3. **Title check** — CAPTCHA page has "Robot Check" in the title

The task is marked as `failed` with the error message. The user sees this in the UI.

### Flexible Price Extraction

```python
for sel in [
    ".a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    ".apexPriceToPay .a-offscreen",
    "#corePrice_feature_div .a-offscreen",
]:
    val = _text(page, sel)
    if val:
        result["price"] = val
        break
```

Amazon uses different HTML structures for different product types (electronics, books,
clothing). Trying multiple selectors in priority order handles all variants.

`".a-offscreen"` — Amazon hides the price text in a span with class `a-offscreen`
(visually hidden but machine-readable). The main displayed price is often an image for
anti-scraping — the `.a-offscreen` span contains the plain text version.

### `wait_until="domcontentloaded"`

```python
resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
```

Options for `wait_until`:
- `"domcontentloaded"` — fires when HTML is parsed (before JS runs)
- `"networkidle"` — waits until no network requests for 500ms (fully loaded)
- `"load"` — waits for the `load` event (images, CSS also loaded)

`"domcontentloaded"` is the fastest. Then we wait specifically for `#productTitle`:
```python
page.wait_for_selector("#productTitle", timeout=10_000)
```

This targeted wait is more reliable than `"networkidle"` because it waits for exactly
the element we need, not all network traffic.

---

## `worker.py` — Standalone OS Process

### Why a Separate Process?

```python
# In main.py lifespan:
cmd = f'exec "{sys.executable}" "{_WORKER_SCRIPT}"'
worker = subprocess.Popen(cmd, shell=True, start_new_session=True)
```

Playwright (headless Chrome) is:
1. **Memory-hungry** — Chrome uses 200-500MB per browser instance
2. **CPU-intensive** — JavaScript rendering
3. **Blocking** — `sync_playwright()` blocks the calling thread for 5-30 seconds

Running inside the FastAPI process would:
- Block the event loop (asyncio)
- Or saturate the thread pool (sync)

A separate OS process has **its own memory space, Python interpreter, and GIL**.
Playwright runs freely without affecting the API server.

### Singleton Pattern via PID File

```python
def _acquire_singleton() -> bool:
    """Return False if another worker process is already alive."""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)   # signal 0 = check if process exists (no actual signal sent)
            logger.warning("Worker already running (PID=%d). Exiting.", old_pid)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # stale PID file — previous worker died without cleanup

    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))
    return True
```

**`os.kill(pid, 0)` — Signal 0:**

Signal 0 doesn't send an actual signal. It just checks if the process `pid` exists.
If the process exists → returns normally. If not → raises `ProcessLookupError`.
This is the standard UNIX idiom for checking process existence.

**`atexit.register`:**

Registers a cleanup function to run when the Python process exits normally.
`PID_FILE.unlink(missing_ok=True)` deletes the PID file so the next startup
doesn't see a stale PID.

### Poll Loop — DB-Backed Queue

```python
def _poll_loop() -> None:
    while not _stop.is_set():
        db = SessionLocal()
        pending = (
            db.query(ScrapingTask)
            .filter(ScrapingTask.status == "pending")
            .order_by(ScrapingTask.id)   # FIFO order
            .all()
        )
        db.close()

        for task in pending:
            with _lock:
                if task.id in _in_progress:
                    continue              # Already processing
                if len(_in_progress) >= MAX_CONCURRENT:
                    break                # Concurrency limit reached
                _in_progress.add(task.id)
            _executor.submit(_run_with_semaphore, task.id)

        _stop.wait(POLL_INTERVAL)   # Sleep 2 seconds (event-aware)
```

**`_stop.wait(POLL_INTERVAL)` vs `time.sleep(POLL_INTERVAL)`:**

`threading.Event.wait()` blocks for up to `POLL_INTERVAL` seconds, but wakes
immediately if `_stop.set()` is called (during shutdown). `time.sleep()` always sleeps
the full duration — shutdown would take up to 2 seconds longer.

### Concurrency Control

```python
_semaphore = threading.Semaphore(MAX_CONCURRENT)   # MAX_CONCURRENT = 2
_executor  = ThreadPoolExecutor(max_workers=MAX_CONCURRENT + 1)
_in_progress: set = set()
_lock = threading.Lock()

def _run_with_semaphore(task_id: int) -> None:
    with _semaphore:   # Blocks until a "slot" is available
        _process_task(task_id)
```

**Three-layer concurrency control:**
1. `_in_progress` set + `_lock` — prevents the poll loop from submitting the same task twice
2. `ThreadPoolExecutor(max_workers=3)` — limits threads in the pool
3. `threading.Semaphore(2)` — limits concurrent Playwright browsers

Why 3 threads for 2 concurrent scrapes? One thread can be waiting on the semaphore
while two others are actively scraping. Without the extra thread, the pool might
deadlock waiting for a thread to become available.

### Crash Recovery

```python
def _recover() -> None:
    db = SessionLocal()
    stuck = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
    for t in stuck:
        t.status = "pending"   # Reset to pending
        t.started_at = None
        job = db.query(ScrapingJob).filter(ScrapingJob.id == t.job_id).first()
        if job:
            job.running = max(0, job.running - 1)
            job.pending += 1
    if stuck:
        db.commit()
```

If the worker process crashes mid-scrape, tasks stay in `"running"` state forever.
On startup, `_recover()` resets them to `"pending"`. FIFO ordering in the poll loop
means these recovered tasks get picked up in the next poll cycle.

`max(0, job.running - 1)` — guard against counter drift going negative.

---

## `services/scraping_queue.py` — In-Memory Queue (Alternative Path)

This file provides an alternative to the external `worker.py` process — a daemon
thread running inside the FastAPI process:

```python
_task_queue: queue.Queue = queue.Queue()   # Thread-safe FIFO queue

def enqueue(task_id: int) -> None:
    _task_queue.put(task_id)   # Non-blocking, thread-safe

def _worker_loop() -> None:
    while True:
        task_id = _task_queue.get()   # Blocks until an item arrives
        _executor.submit(_process_with_semaphore, task_id)
```

**`queue.Queue`** is Python's thread-safe FIFO queue. `put()` is non-blocking (adds to queue).
`get()` blocks until an item is available (no CPU spinning / busy waiting).

**vs `worker.py` approach:**

| | In-process queue (`scraping_queue.py`) | External process (`worker.py`) |
|---|---|---|
| Restart safety | Tasks lost if app crashes | Tasks survive (in DB) |
| Memory isolation | Shares app memory | Fully isolated |
| Deployment | Simpler | More complex |
| Best for | Development | Production |

---

## Database Table Relationships

```
scraping_jobs                 scraping_tasks              product_data
─────────────                 ──────────────              ────────────
id (PK)                       id (PK)                     id (PK)
user_id → users.id            job_id → scraping_jobs.id   task_id → scraping_tasks.id (unique)
total                         asin                        asin
pending                       status: pending/running/    title
running                              completed/failed     price
completed                     error                       rating
failed                        queued_at                   ...
created_at                    started_at                  scraped_at
                              completed_at
```

**Job counters (pending/running/completed/failed):** Denormalised counts kept in sync
with task status. This avoids expensive `COUNT(*)` queries on the tasks table for the
live status display. The endpoint validates these against actual task rows:

```python
# In endpoint — recount from tasks (guards against counter drift)
pending = sum(1 for t in tasks if t.status == "pending")
```

---

## Interview Questions

**Q: What is headless Chrome and why is it used for scraping?**

Headless Chrome is a Chrome browser that runs without a visible window. It executes
JavaScript, handles cookies, and renders pages exactly like a real browser — making
it nearly impossible for anti-scraping systems to distinguish from real users.
`requests` is detectable (no JS execution, distinctive TLS fingerprint, no viewport).

**Q: What is a Semaphore and how is it different from a Lock?**

A **Lock** allows only 1 holder at a time. A **Semaphore** allows N holders concurrently.
`threading.Semaphore(2)` means at most 2 threads can hold it simultaneously.
When both slots are taken, `with _semaphore:` blocks until one is released.
Use Semaphore for concurrency limiting; use Lock for mutual exclusion.

**Q: What is `start_new_session=True` in `subprocess.Popen`?**

Creates a new process group for the child process. On Unix, pressing Ctrl+C sends SIGINT
to the entire process group. Without `start_new_session=True`, Ctrl+C would kill both
the FastAPI server and the worker. With it, only the FastAPI server receives Ctrl+C;
the worker continues running. We terminate the worker explicitly in the `finally` block.

**Q: Why does the poll loop use `_stop.wait(2)` instead of `time.sleep(2)`?**

`threading.Event.wait(timeout)` is interruptible — when `_stop.set()` is called
(e.g., by a SIGTERM signal handler), `wait()` returns immediately even if the timeout
hasn't elapsed. `time.sleep()` always waits the full duration. This means graceful
shutdown completes in <1ms instead of waiting up to 2 seconds.
