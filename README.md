# SnapRecon

*Built and maintained by rabbyt3s for authorized recon workflows.*

SnapRecon is a Python CLI that performs authorized reconnaissance end to end: it discovers targets, screenshots them with Playwright/Chromium, applies lightweight local heuristics, and ships a report you can hand to stakeholders. The tool is designed to run on Kali or any Linux box where you already vet your scope.

## Why SnapRecon
- One command from discovery to report: subfinder integration, screenshots, local tagging
- Reports you can share: JSON for automation, Markdown/HTML for humans
- Friendly UX: progress spinners, Rich-powered summaries, actionable errors
- Safety first: scoped runs, deterministic denylisting, no credential or cookie capture

## Requirements
- Python 3.11 or newer (virtual environments recommended)
- Playwright with the Chromium browser runtime (`playwright install --with-deps chromium`)
- `subfinder` on your PATH (installed via `apt`, `brew`, or the upstream release)
- A scope file defining what you are authorized to scan (see below)

## Installation
```bash
# Clone and install SnapRecon in editable mode
git clone https://github.com/rabbyt3s/snaprecon.git
cd snaprecon
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

# Install Playwright browsers
playwright install --with-deps chromium
```

You can optionally install with `pipx install .` if you prefer isolated CLIs.

## Quick Start
1. **Create a scope file** describing allowed domains/hosts:
   ```text
   # scope.txt
   example.com
   *.example.net
   admin.partner.example.org
   ```
2. **Run SnapRecon** with either a discovery seed (`--domain`) or a prepared host list (`--targets-file`). A scope file is required.
   ```bash
   snaprecon --domain example.com --scope-file scope.txt
   ```
3. **Open the report** from the timestamped run directory under `runs/`.

If you see `Missing input: provide --domain or --targets-file. Run 'snaprecon --help' for usage details.`, pass one of the required inputs or run the help command for full CLI usage.

## CLI Usage
Run `snaprecon --help` for the latest options. Core flags include:
- `--domain / --targets-file` – choose between discovery (subfinder) or ingesting a prepared list
- `--scope-file` – mandatory allow-list of domains/hosts; targets outside scope are dropped
- `--output-dir` – parent directory for timestamped runs (default `runs`)
- `--concurrency` – browser worker count (1-20)
- `--timeout` – per-target navigation timeout in milliseconds
- `--fullpage` – capture full-page screenshots
- `--dry-run` – skip local analysis while still capturing screenshots
- `--debug` – enable verbose logging to the terminal

Example: ingest a curated list, run in headed mode for debugging, and keep costs low by skipping analysis.
```bash
snaprecon --targets-file scope_hosts.txt --scope-file scope.txt --headed --dry-run
```

## Output
Each run creates `runs/YYYYMMDD_HHMMSS/` containing:
- `results.json` – Pydantic-validated run data (safe config, per-target metadata, analysis)
- `report.md` – quick summary for chat tools or issue trackers
- `report.html` – rich, filterable report with thumbnails and open-port highlights
- `screenshots/` – full-resolution PNGs named after the host

JSON serialization is stable and extra fields are rejected, so downstream tooling can rely on the schema.

## Configuration
SnapRecon reads values from environment variables first, then an optional TOML file (see `config.example.toml`). Useful knobs:
- `SNAPRECON_OUTPUT_DIR`, `SNAPRECON_CONCURRENCY`, `SNAPRECON_TIMEOUT_MS`
- `SNAPRECON_USER_AGENT`, `SNAPRECON_FULLPAGE`, `SNAPRECON_HEADLESS`
- `SNAPRECON_SUBFINDER_BIN` to point to a custom binary path

To persist settings, copy `config.example.toml` to `config.toml` and tweak as needed.

## Local Keyword Analysis
When not running in `--dry-run`, SnapRecon tags each page using heuristics driven by titles, URLs, and hostnames. Tags such as `admin`, `vpn`, `devops`, or `api` help you triage interesting surfaces quickly—without sending data to external LLMs.

## Safety & Ethics
- Always provide a valid scope file; SnapRecon refuses to proceed when the file is missing or empty.
- Targets outside your scope or in a denylist are skipped with explicit logging.
- Playwright sessions never persist cookies, local storage, or credentials to disk.
- Respect rate limits and legal boundaries—only run SnapRecon where you have written permission.

## Troubleshooting
- **`subfinder` not found** – install the binary or point `--subfinder-bin` to its location.
- **Chromium fails to launch** – rerun `playwright install --with-deps chromium` and ensure you have required system libraries.
- **Timeouts** – raise `--timeout` or lower `--concurrency` for high-latency targets.
- **Missing screenshots** – inspect `runs/<timestamp>/screenshots/` and rerun with `--debug` for verbose logs.

## Development
```bash
# Run linting and tests
ruff check src
pytest -q

# Format code
ruff format src
```

Contributions are welcome: fork, branch, add tests, and open a PR. See `SECURITY.md` for the vulnerability disclosure policy.

## License
SnapRecon is released under the MIT License. See `LICENSE` for details.
