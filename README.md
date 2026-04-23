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

## Running tests

```bash
source .venv/bin/activate
pytest
```
