# price-tracker

Amazon Price Drop Monitor — watches a list of Amazon product URLs and notifies you when prices drop past a configured threshold. Logs are written to `logs/price_monitor.log` and a live dashboard is served at `http://localhost:8000`.

## Requirements

- Python 3.11 or later
- Git

Verify your Python version before starting:

```bash
python3 --version
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/BugsRugs/price-tracker.git
cd price-tracker
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **Debian/Ubuntu only:** If the above fails with an `ensurepip is not available` error, install the system package first, then re-run the two commands above:
> ```bash
> sudo apt-get update && sudo apt-get install python3.12-venv
> ```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs all runtime dependencies (`httpx`, `selectolax`, `apscheduler`, `fastapi`, `uvicorn`, `pydantic`, `pyyaml`, `plyer`, etc.) and dev dependencies (`pytest`).

### 4. Create your config file (one-time)

```bash
cp config.example.yaml config.yaml
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

```bash
source .venv/bin/activate
python -m price_monitor
```

The scheduler starts, prices are checked on the configured interval, and the dashboard is available at `http://localhost:8000`. Logs are written to `logs/price_monitor.log`.

## Running tests

```bash
source .venv/bin/activate
pytest
```
