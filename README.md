<div align="center">

# SnapRecon

<img width="600" height="200" alt="SnapRecon banner" src="https://github.com/user-attachments/assets/735ee8d4-9aef-41d5-8c67-88609325de2e" />


SnapRecon is a **Linux-first reconnaissance CLI** that automates discovery, screenshot capture, and lightweight heuristic analysis for authorized assessments. It integrates Playwright/Chromium, `subfinder`, and a deterministic reporting pipeline to deliver repeatable results you can archive or feed into downstream tooling.

![demo](https://github.com/user-attachments/assets/1a4bf851-8b8d-42cf-8a8d-f25b0dec3411)

</div>

## Built With
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](#requirements)
[![Typer](https://img.shields.io/badge/Typer-CLI-2962FF?logo=typer&logoColor=white)](#cli-overview)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=microsoftedge&logoColor=white)](#requirements)
[![subfinder](https://img.shields.io/badge/subfinder-Discovery-000000)](#quick-start)

## Key Capabilities
- Discovery pipeline using `subfinder` or pre-built host lists
- Chromium-based screenshot capture with concurrent workers and strict timeouts
- Keyword-oriented tagging to flag administrative or high-value surfaces
- Deterministic JSON, Markdown, and HTML report generation
- Local-only processing; no external LLM or telemetry dependencies

## Requirements
- Python 3.11+
- Playwright with the Chromium runtime (`playwright install --with-deps chromium`)
- `subfinder` installed and available on your `PATH` (see installation notes below, or provide `--subfinder-bin`)
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

```bash
# Install subfinder (choose one option) and ensure it is in PATH
sudo apt install subfinder                             # Debian/Kali/Ubuntu package
# or
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
export PATH="$PATH:$HOME/go/bin" && source ~/.bashrc   # add Go bin to PATH if needed
# or
wget https://github.com/projectdiscovery/subfinder/releases/latest/download/subfinder_linux_amd64.zip
unzip subfinder_linux_amd64.zip && sudo mv subfinder /usr/local/bin/

# Verify the binary is available
which subfinder
```

For a global CLI, install with `pipx install .` to keep the environment isolated.

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
   snaprecon --domain example.com                      # discovery via subfinder
   snaprecon --targets-file ./hosts.txt                # ingest an existing list
   snaprecon --domain example.com --scope-file scope.txt  # discovery + scope enforcement
   ```
3. Review the timestamped run directory under `runs/` and open `report.html`.

If you call `snaprecon` without `--domain` or `--targets-file`, the CLI exits with guidance to supply either input or run `snaprecon --help`.

## CLI Overview
Run `snaprecon --help` for the full command surface. Frequently used options:
- `--domain` / `--targets-file` — choose discovery via subfinder or ingest a prepared list
- `--scope-file` — optional allow-list; when provided, out-of-scope hosts are dropped
- `--output-dir` — parent directory for run artifacts (default: `runs`)
- `--concurrency` — concurrent browser workers (1-20)
- `--timeout` — per-target navigation timeout in milliseconds
- `--fullpage` — toggle full-page screenshots
- `--dry-run` — skip keyword analysis and capture screenshots only
- `--debug` — emit verbose logs with Playwright details
- `--scan-profile` — choose `fast`, `balanced`, or `full` presets (controls analysis + tech fingerprinting)
- `--wappalyzer` / `--wappalyzer-scan` — enable Wappalyzer detection and select `fast`, `balanced`, or `full`

### Scan Profiles

SnapRecon bundles three opinionated presets to balance speed and fidelity:

| Profile   | Description | Analysis | Wappalyzer |
|-----------|-------------|----------|------------|
| `fast`    | Screenshot-only; quickest feedback loop | Disabled (`--dry-run`) | Off |
| `balanced`| Default mix of speed and insight | Enabled | Off |
| `full`    | Maximum context via local analysis + tech fingerprinting | Enabled | On (`--wappalyzer-scan full`) |

You can still override individual flags (`--wappalyzer`, `--dry-run`, etc.) after selecting a profile.

### Wappalyzer Integration

SnapRecon optionally augments metadata with technology fingerprints via the [`wappalyzer`](https://pypi.org/project/wappalyzer/) package.

1. Install runtime dependencies (Wappalyzer relies on Firefox/geckodriver):
   ```bash
   sudo apt install firefox-esr
   wget -O geckodriver.tar.gz "https://github.com/mozilla/geckodriver/releases/latest/download/geckodriver-linux64.tar.gz"
   tar xf geckodriver.tar.gz
   sudo mv geckodriver /usr/local/bin/
   ```
2. Install the Python dependency (already in project requirements):
   ```bash
   pip install wappalyzer
   ```
3. Run SnapRecon with Wappalyzer enabled:
   ```bash
snaprecon --targets-file hosts.txt --scan-profile full
# (scan profile full automatically enables Wappalyzer with a full scan)
# or manually
snaprecon --targets-file hosts.txt --wappalyzer --wappalyzer-scan balanced
   ```

Detected technologies surface in both JSON (`results.targets[].metadata.technologies`) and rendered reports.

<img width="1452" height="550" alt="image" src="https://github.com/user-attachments/assets/1a405ec2-1b11-4add-a314-08ae0521a6fb" />

## Output Layout
Each run creates `runs/YYYYMMDD_HHMMSS/` containing:
- `results.json` — Pydantic-validated summary with safe configuration and per-target metadata
- `report.md` — text summary aligned with ticketing workflows
- `report.html` — interactive report with thumbnails and optional port data
- `screenshots/` — PNG captures named after each host

JSON output is stable and forbids unknown fields, making it safe for downstream automation.

## Configuration
SnapRecon reads environment variables first and then merges an optional TOML configuration file (see `config.example.toml`). Notable settings:
- `SNAPRECON_OUTPUT_DIR`, `SNAPRECON_CONCURRENCY`, `SNAPRECON_TIMEOUT_MS`
- `SNAPRECON_USER_AGENT`, `SNAPRECON_FULLPAGE`, `SNAPRECON_HEADLESS`
- `SNAPRECON_SUBFINDER_BIN` for non-default binary paths

Persist overrides by copying `config.example.toml` to `config.toml`.

## Keyword Analysis
When analysis is enabled (the default), SnapRecon tags snapshots using heuristic keyword matching across titles, URLs, and hostnames (e.g., `admin`, `vpn`, `devops`, `api`). All processing is local; no external LLM calls are performed.

## Operational Notes
- Respect legal scope: only target systems you are authorized to assess.
- Provide a scope file when you need deterministic allow-list enforcement; it is not mandatory for basic discovery.
- Headless Chromium sessions do not persist cookies or credentials.
- Timeouts and concurrency limits guard against resource exhaustion during large enumerations.

## Troubleshooting
- `subfinder` missing: install via package manager or pass `--subfinder-bin` with an absolute path.
- Chromium launch failures: run `playwright install --with-deps chromium` and ensure system libraries are present.
- Repeated timeouts: increase `--timeout` or lower `--concurrency`.
- Empty screenshots: re-run with `--debug` to view Playwright logs.

## Contributing
Contributions are welcome. Fork the repository, branch from `main`, add tests alongside changes, and submit a pull request. 

## License
Released under the MIT License. Refer to `LICENSE` for the full text.


