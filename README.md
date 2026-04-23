# price-tracker

Amazon Price Drop Monitor — watches a list of Amazon product URLs and notifies you when prices drop past a configured threshold. Logs are written to `logs/price_monitor.log` and a live dashboard is served at `http://localhost:8000`.

## Requirements

- Python 3.11 or later
- Git

### Installing Python

If you don't have Python 3.11+ installed, follow the steps for your OS:

**macOS**
```bash
brew install python@3.12
```
> If you don't have Homebrew: `curl -fsSL https://brew.sh | bash`

**Ubuntu / Debian Linux**
```bash
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv python3-pip
```

**Windows**

Download and run the installer from [python.org/downloads](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**.

---

Verify your install before continuing:

```bash
python3 --version   # macOS / Linux
python --version    # Windows
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/BugsRugs/price-tracker.git
cd price-tracker
```

### 2. Create and activate a virtual environment

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

> If the above fails, bootstrap pip manually:
> ```bash
> python3 -m venv .venv --without-pip && source .venv/bin/activate && curl -sS https://bootstrap.pypa.io/get-pip.py | python3
> ```

**Windows**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs all runtime dependencies (`httpx`, `selectolax`, `apscheduler`, `fastapi`, `uvicorn`, `pydantic`, `pyyaml`, `plyer`, etc.) and dev dependencies (`pytest`).

### 4. Create your config file (one-time)

**macOS / Linux**
```bash
cp config.example.yaml config.yaml
```

**Windows**
```powershell
copy config.example.yaml config.yaml
```

Open `config.yaml` and fill in the Amazon product URLs you want to track. The file is gitignored so your personal URLs and settings will never be committed. Key fields:

| Field | Description | Default |
|---|---|---|
| `products` | List of `url` + `name` pairs to monitor | *(required)* |
| `check_interval_minutes` | How often to check prices | `60` |
| `drop_threshold_pct` | Minimum % drop to trigger a notification | `5.0` |
| `notification_channels` | `console`, `desktop`, or both | `["console"]` |
| `db_path` | Path to the SQLite database file | `price_monitor.db` |

### 5. Run the monitor

Run this from the **repo root** (the directory containing `config.yaml`):

**macOS / Linux**
```bash
source .venv/bin/activate
python -m price_monitor
```

**Windows**
```powershell
.venv\Scripts\activate
python -m price_monitor
```

The scheduler starts, prices are checked on the configured interval, and the dashboard is available at `http://localhost:8000`. Logs are written to `logs/price_monitor.log`.

## Triggering a test price drop

Real price drops can take hours or days to occur. To verify the full notification pipeline immediately, seed a fake high price directly into the database for one of your products. On the next scheduled tick, the scraper will fetch the real (lower) price, detect the drop, and fire all configured notifications.

**1. Lower your threshold so any price difference triggers an alert** (optional but recommended for testing):

In `config.yaml`, set:
```yaml
drop_threshold_pct: 0.01
check_interval_minutes: 1
```

**2. Seed a fake high price for product 1** (adjust `product_id` and `checked_at` as needed — set `checked_at` to a minute or two in the past so it is treated as the most recent prior price):

```bash
sqlite3 price_monitor.db "INSERT INTO price_checks (product_id, checked_at, status, price, currency, attempts) VALUES (1, '2026-04-23T16:06:00+00:00', 'ok', 9999.99, 'USD', 1);"
```

**3.** Wait for the next tick (up to `check_interval_minutes`). When a successful scrape is logged you will see:

- A bold green **PRICE DROP ALERT** banner in the terminal
- A persistent desktop notification with a sound (if `notification_channels` includes `desktop`)
- A new entry in the **Notifications** table on the dashboard at `http://localhost:8000`
- A visible drop on the price history chart

**4. Reset after testing** — restore `drop_threshold_pct` and `check_interval_minutes` to your preferred values in `config.yaml`.

## Privacy

**Personal data.** The application collects, stores, and processes no personal data. Inputs are product URLs and prices; outputs are local notifications and a local web dashboard. No user accounts, no analytics, no third-party data sharing. The SQLite database contains only product metadata (URL, name) and price history.

## Running tests

```bash
source .venv/bin/activate
pytest
```
