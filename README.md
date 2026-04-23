# price-tracker

Amazon Price Drop Monitor — watches a list of Amazon product URLs and notifies you when prices drop past a configured threshold.

## Getting started

### 1. Clone the repository

```bash
git clone <repo-url>
cd price-tracker
```

### 2. Create and activate a virtual environment, then install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> **Note (Debian/Ubuntu):** If `python3 -m venv` fails with an `ensurepip` error, install the system package first:
> ```bash
> sudo apt-get update && sudo apt-get install python3.12-venv
> ```
> Then re-run the `venv` commands above.

### 3. Set up `config.yaml` (one-time)

```bash
cp config.example.yaml config.yaml
```

Open `config.yaml` and add the Amazon product URLs you want to track along with any other settings (check interval, drop threshold, notification channel, etc.). See `config.example.yaml` for reference.

### 4. Run the monitor

```bash
cd /home/bronson-wong/price-tracker
source .venv/bin/activate
python -m price_monitor
```

The monitor will check prices on the interval defined in `config.yaml` and print a notification to the console whenever a price drops by at least the configured threshold.
