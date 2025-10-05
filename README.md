# SnapRecon

SnapRecon is a Linux-first reconnaissance CLI that automates discovery, screenshot capture, and lightweight heuristic analysis for authorized assessments. It integrates Playwright/Chromium, `subfinder`, and a deterministic reporting pipeline to deliver repeatable results you can archive or feed into downstream tooling.

## Key Capabilities
- Discovery pipeline using `subfinder` or pre-built host lists
- Chromium-based screenshot capture with concurrent workers and strict timeouts
- Keyword-oriented tagging to flag administrative or high-value surfaces
- Deterministic JSON, Markdown, and HTML report generation
- Local-only processing; no external LLM or telemetry dependencies

## Requirements
- Python 3.11+
- Playwright with the Chromium runtime (`playwright install --with-deps chromium`)
- `subfinder` available on `PATH` or provided via `--subfinder-bin`
- Any modern Linux distribution (tested on Kali, Ubuntu, Arch); macOS with Playwright support should also work

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

For a global CLI, you can install with `pipx install .` instead of creating a virtual environment.

## Quick Start
1. Optional scope file (recommended for larger engagements):
   ```text
   # scope.txt
   example.com
   *.corp.example.net
   admin.partner.example.org
   ```
2. Run SnapRecon with a discovery seed or a host list. Scope filtering is additive—provide it when you want explicit allow-list behaviour.
   ```bash
   snaprecon --domain example.com                     # discovery via subfinder
   snaprecon --targets-file ./hosts.txt               # ingest an existing list
   snaprecon --domain example.com --scope-file scope.txt  # discovery + scope enforcement
   ```
3. Review the timestamped run directory under `runs/` and open `report.html`.

If you call `snaprecon` without `--domain` or `--targets-file` the CLI will exit with guidance to supply either input or inspect `--help`.

## CLI Overview
Consult `snaprecon --help` for the full command surface. Frequently used options include:
- `--domain` / `--targets-file` — choose between discovery or ingest
- `--scope-file` — optional allow-list; out-of-scope hosts are dropped when present
- `--output-dir` — parent directory for run artifacts (default: `runs`)
- `--concurrency` — concurrent browser workers (1-20)
- `--timeout` — per-target navigation timeout in milliseconds
- `--fullpage` — toggle full-page screenshots
- `--dry-run` — skip keyword analysis, capture screenshots only
- `--debug` — emit verbose logs

## Output Layout
Each run creates `runs/YYYYMMDD_HHMMSS/` containing:
- `results.json` — Pydantic-validated summary with safe configuration and per-target metadata
- `report.md` — text summary suitable for ticketing systems
- `report.html` — filterable report with thumbnails and optional port data
- `screenshots/` — PNG captures named after each host

JSON output is stable and forbids unknown fields, making it suitable for automated pipelines.

## Configuration
SnapRecon reads environment variables first and then merges an optional TOML configuration file (see `config.example.toml`). Notable settings:
- `SNAPRECON_OUTPUT_DIR`, `SNAPRECON_CONCURRENCY`, `SNAPRECON_TIMEOUT_MS`
- `SNAPRECON_USER_AGENT`, `SNAPRECON_FULLPAGE`, `SNAPRECON_HEADLESS`
- `SNAPRECON_SUBFINDER_BIN` for non-default binary paths

Persist overrides by copying `config.example.toml` to `config.toml`.

## Keyword Analysis
When analysis is enabled (the default), snapshots are tagged using heuristic keyword matching across titles, URLs, and hostnames (e.g., `admin`, `vpn`, `devops`, `api`). The process is entirely local and incurs zero external calls.

## Operational Notes
- Respect legal scope: only enumerate systems you are authorized to assess.
- Provide a scope file when you need deterministic allow-list enforcement; the CLI does not require it for single-domain discovery.
- Headless Chromium sessions do not persist cookies or credentials.
- Timeouts and concurrency limits guard against resource exhaustion during large enumerations.

## Troubleshooting
- `subfinder` missing: install via package manager or pass `--subfinder-bin` with an absolute path.
- Chromium launch failures: run `playwright install --with-deps chromium` and ensure system libraries are present.
- Repeated timeouts: increase `--timeout` or lower `--concurrency`.
- Empty screenshots: re-run with `--debug` to view Playwright logs.

Contributions are welcome. Fork the repository, branch from `main`, add tests alongside changes, and submit a pull request. 

## License
Released under the MIT License. Refer to `LICENSE` for the full text.
