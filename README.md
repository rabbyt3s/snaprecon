# SnapRecon

A Python-based reconnaissance tool for authorized security testing that discovers subdomains, captures screenshots, and analyzes web applications using local keyword analysis.

## Overview

SnapRecon automates the reconnaissance phase of security assessments by:
- Discovering subdomains using `subfinder`
- Taking screenshots of web applications via Playwright/Chromium
- Analyzing page content using local keyword heuristics
- Generating comprehensive HTML and Markdown reports

## Features

- **Subdomain Discovery**: Automatic subdomain enumeration via `subfinder`
- **Screenshot Capture**: Headless browser automation with configurable timeouts
- **Local Analysis**: Keyword-based tagging without external API calls
- **Scope Validation**: Strict domain allowlist enforcement
- **Multiple Outputs**: JSON, HTML, and Markdown report generation
- **Concurrent Processing**: Configurable concurrency for performance

## Requirements

- Python 3.8+
- `subfinder` binary (Kali Linux or manual installation)
- Playwright with Chromium browser

## Installation

```bash
# Clone repository
git clone https://github.com/rabbyt3s/snaprecon.git
cd snaprecon

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install --with-deps chromium
```

## Configuration

### Environment Variables

```bash
export GOOGLE_API_KEY="your_api_key_here"
export SNAPRECON_MODEL="gemini-2.5-flash"
export SNAPRECON_MAX_COST="10.0"
export SNAPRECON_OUTPUT_DIR="runs"
export SNAPRECON_CONCURRENCY="5"
```

### Configuration File (config.toml)

```toml
[gemini]
model = "gemini-2.5-flash"
max_cost_usd = 10.0

[browser]
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
timeout_ms = 30000
fullpage = false

[discovery]
subfinder_bin = "subfinder"
concurrency = 5

[output]
output_dir = "runs"
verbose = false
```

## Usage

### Basic Commands

```bash
# Full reconnaissance with scope file
snaprecon run --domain example.com --scope-file scope.txt

# Quick reconnaissance (no scope file, auto-filtering)
snaprecon quick --domain example.com --concurrency 10

# Test run with limited targets
snaprecon test --domain example.com --scope-file scope.txt --test-count 5

# Cost estimation
snaprecon estimate --domain example.com

# Scope file validation
snaprecon validate --scope-file scope.txt
```

### Advanced Options

```bash
# Full page screenshots
snaprecon run --domain example.com --scope-file scope.txt --fullpage

# Custom timeout and concurrency
snaprecon run --domain example.com --scope-file scope.txt --timeout 60000 --concurrency 10

# Proxy support
snaprecon run --domain example.com --scope-file scope.txt --proxy "http://proxy:8080"

# Dry run (skip analysis)
snaprecon run --domain example.com --scope-file scope.txt --dry-run

# Verbose logging
snaprecon run --domain example.com --scope-file scope.txt --verbose
```

## Scope File Format

Create a scope file with allowed domains and suffixes:

```text
# Allowed domains
example.com
test.example.com

# Allowed suffixes (matches any subdomain)
.example.org
.test.com

# Comments are ignored
```

## Output Structure

```
runs/
├── 20241201_143022/          # Timestamped run directory
│   ├── results.json          # Structured results data
│   ├── report.html           # Interactive HTML report
│   ├── report.md             # Markdown report
│   └── screenshots/          # PNG screenshots
```

## Architecture

### Core Components

- **CLI Interface**: Typer-based command-line interface
- **Discovery**: Subdomain enumeration and target resolution
- **Browser Automation**: Playwright-based screenshot capture
- **Analysis**: Local keyword-based content analysis
- **Reporting**: Jinja2 template-based report generation
- **Safety**: Scope validation and denylist support

### Data Models

- **Target**: Individual host with metadata and analysis results
- **RunResult**: Complete reconnaissance run data
- **SafeConfig**: Non-sensitive configuration for storage
- **Error**: Structured error handling and reporting

## Local Analysis

The tool uses local keyword analysis to categorize web pages:

- **Authentication**: login, auth, sso, keycloak
- **Administration**: admin, backoffice, wp-admin
- **Infrastructure**: vpn, monitoring, devops, kubernetes
- **Services**: jenkins, gitlab, jira, confluence
- **Databases**: phpmyadmin, pgadmin, mongodb
- **Security**: vault, guard, shield

Analysis is performed locally without external API calls, ensuring privacy and zero cost.

## Safety Features

- **Scope Enforcement**: Mandatory domain allowlist validation
- **Denylist Support**: Optional domain blocking
- **Rate Limiting**: Configurable concurrency and timeouts
- **Error Handling**: Comprehensive error reporting and logging
- **Dry Run Mode**: Test configuration without analysis

## Performance

- **Concurrent Processing**: Configurable concurrency (1-20)
- **Timeout Protection**: Per-target and overall timeouts
- **Resource Management**: Efficient browser instance handling
- **Memory Optimization**: Streaming screenshot processing

## Troubleshooting

### Common Issues

1. **Subfinder not found**: Install `subfinder` or specify path with `--subfinder-bin`
2. **Browser launch failures**: Ensure Playwright is installed with `playwright install --with-deps chromium`
3. **Permission errors**: Check file permissions for output directories
4. **Timeout issues**: Adjust `--timeout` and `--concurrency` values

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
snaprecon run --domain example.com --scope-file scope.txt --verbose
```

## Development

### Project Structure

```
src/snaprecon/
├── cli.py           # Command-line interface
├── config.py        # Configuration management
├── models.py        # Data models and validation
├── discover.py      # Subdomain discovery
├── browser.py       # Browser automation
├── analysis.py      # Local keyword analysis
├── reporting.py     # Report generation
├── cost.py          # Cost management (legacy)
├── safety.py        # Scope validation
└── utils.py         # Utility functions
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src/snaprecon

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Author

**rabbyt3s** - Security researcher and tool developer

## Disclaimer

This tool is designed for authorized security testing only. Always ensure you have proper authorization before scanning any systems. The authors are not responsible for misuse of this software.
