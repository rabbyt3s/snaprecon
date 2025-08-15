# 🔍 SnapRecon

**Authorized reconnaissance tool with intelligent screenshot analysis via Gemini Vision**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Security: No API Keys in Results](https://img.shields.io/badge/Security-No%20API%20Keys%20Exposed-green.svg)](https://github.com/yourusername/snaprecon)

## 🚀 What is SnapRecon?

SnapRecon is a powerful, authorized reconnaissance tool that combines subdomain discovery with intelligent screenshot analysis. It automatically discovers subdomains, captures screenshots, and uses Google's Gemini Vision AI to analyze and categorize web pages.

### ✨ Key Features

- **🔍 Subdomain Discovery**: Automatic subdomain enumeration using `subfinder`
- **📸 Smart Screenshots**: Browser automation with Playwright/Chromium
- **🤖 AI Analysis**: Gemini Vision AI for intelligent page categorization
- **🌙 Dark Theme Reports**: Beautiful, responsive HTML reports with dark mode
- **🔒 Security First**: No sensitive data (API keys) stored in results
- **📊 Cost Management**: Built-in cost tracking and limits
- **⚡ Fast & Efficient**: Concurrent processing with configurable limits

## 🛠️ Installation

### Prerequisites

- **Python 3.11+**
- **subfinder** (for subdomain discovery)
- **Google API Key** (for Gemini Vision)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/yourusername/snaprecon.git
cd snaprecon

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install --with-deps chromium

# Install subfinder (Kali Linux)
sudo apt install subfinder

# Or download from: https://github.com/projectdiscovery/subfinder/releases
```

### Environment Setup

```bash
# Create .env file
cp config.example.toml config.toml

# Edit config.toml with your settings
# Required: GOOGLE_API_KEY
# Optional: SNAPRECON_MODEL, SNAPRECON_MAX_COST, etc.
```

## 🎯 Quick Start

### 1. Basic Test Run

```bash
# Test with 3 subdomains
snaprecon test --domain example.com --scope-file scope.txt --test-count 3
```

### 2. Full Reconnaissance

```bash
# Full domain reconnaissance
snaprecon run --domain example.com --scope-file scope.txt --max-cost 5.0
```

### 3. Custom Input File

```bash
# Use custom target list
snaprecon run --input-file targets.txt --scope-file scope.txt
```

## 📋 Usage Guide

### Command Structure

```bash
snaprecon [COMMAND] [OPTIONS]
```

### Available Commands

| Command | Description | Use Case |
|---------|-------------|----------|
| `run` | Full reconnaissance run | Production reconnaissance |
| `test` | Quick test run | Validation and testing |
| `estimate` | Cost estimation | Planning and budgeting |
| `validate` | Scope file validation | Pre-run verification |

### Essential Options

| Option | Description | Default |
|--------|-------------|---------|
| `--domain` | Target domain | Required for discovery |
| `--scope-file` | Allowed domains file | **Required** |
| `--test-count` | Number of test targets | 10 |
| `--max-cost` | Maximum cost in USD | 10.0 |
| `--model` | Gemini model | gemini-2.5-flash |
| `--concurrency` | Parallel operations | 5 |
| `--timeout` | Page timeout (ms) | 30000 |

### Scope File Format

Create a `scope.txt` file with allowed domains:

```txt
# Allowed domains and suffixes
example.com
*.example.org
subdomain.example.net
```

## 📊 Output & Reports

### Generated Files

Every run creates a timestamped directory with:

- **`results.json`** - Raw data and analysis results
- **`report.html`** - Interactive HTML report with dark theme
- **`report.md`** - Markdown summary report
- **`screenshots/`** - All captured screenshots

### HTML Report Features

- 🌙 **Dark Theme** - Easy on the eyes
- 📸 **Screenshot Gallery** - Click to enlarge
- 🔍 **Smart Filtering** - Filter by success/error status
- 📱 **Responsive Design** - Works on all devices
- 💰 **Cost Tracking** - Real-time cost analysis

## 🔒 Security Features

### API Key Protection

- **No API keys stored** in results files
- **SafeConfig model** excludes sensitive data
- **Environment variables** for configuration
- **Scope enforcement** prevents unauthorized targets

### Scope Validation

```bash
# Validate your scope file before running
snaprecon validate --scope-file scope.txt
```

## 💰 Cost Management

### Pricing (Gemini 2.5 Flash)

- **Vision Input**: $0.000225 per 1K tokens
- **Text Output**: $0.000075 per 1K tokens
- **Typical Cost**: ~$0.0002 per screenshot

### Cost Estimation

```bash
# Estimate costs before running
snaprecon estimate --domain example.com
```

### Cost Limits

```bash
# Set maximum cost limit
snaprecon run --domain example.com --max-cost 5.0
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Google API key | **Required** |
| `SNAPRECON_MODEL` | Gemini model | gemini-2.5-flash |
| `SNAPRECON_MAX_COST` | Maximum cost | 10.0 |
| `SNAPRECON_CONCURRENCY` | Parallel operations | 5 |
| `SNAPRECON_TIMEOUT_MS` | Page timeout | 30000 |

### Configuration File

```toml
# config.toml
[snaprecon]
google_api_key = "your-api-key-here"
gemini_model = "gemini-2.5-flash"
max_cost_usd = 10.0
concurrency = 5
timeout_ms = 30000
fullpage = false
```

## 🧪 Testing & Validation

### Test Mode

```bash
# Quick test with limited targets
snaprecon test --domain example.com --test-count 5
```

### Validation Commands

```bash
# Validate scope file
snaprecon validate --scope-file scope.txt

# Check configuration
snaprecon estimate --domain example.com
```

## 📁 Project Structure

```
snaprecon/
├── src/snaprecon/          # Core application
│   ├── cli.py             # Command-line interface
│   ├── models.py          # Data models (SafeConfig)
│   ├── browser.py         # Screenshot automation
│   ├── analysis.py        # Gemini Vision integration
│   ├── reporting.py       # Report generation
│   ├── safety.py          # Scope enforcement
│   └── cost.py            # Cost management
├── templates/              # Report templates
│   ├── report.html.j2     # HTML report (dark theme)
│   └── report.md.j2       # Markdown report
├── tests/                  # Test suite
├── docs/                   # Documentation
├── scripts/                # Helper scripts
└── config.example.toml     # Configuration template
```

## 🚨 Important Notes

### ⚠️ Legal & Ethical Use

- **Only use on authorized targets**
- **Respect robots.txt and rate limits**
- **Follow responsible disclosure practices**
- **Comply with local laws and regulations**

### 🔐 Security Best Practices

- **Keep API keys secure**
- **Use scope files to limit targets**
- **Monitor costs and usage**
- **Regular security updates**

## 🐛 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **API Key Error** | Check `GOOGLE_API_KEY` environment variable |
| **Subfinder Not Found** | Install subfinder or specify `--subfinder-bin` |
| **Screenshot Failures** | Check network connectivity and target availability |
| **Cost Exceeded** | Increase `--max-cost` or reduce target count |

### Debug Mode

```bash
# Enable verbose logging
snaprecon run --domain example.com --verbose
```

## 🤝 Contributing

### Development Setup

```bash
# Clone and setup development environment
git clone https://github.com/yourusername/snaprecon.git
cd snaprecon
pip install -e .
pip install -r requirements-dev.txt

# Run tests
pytest tests/
```

### Code Style

- **Black** for code formatting
- **Ruff** for linting
- **Type hints** for all functions
- **Docstrings** for all modules

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Google Gemini** for AI vision capabilities
- **Playwright** for browser automation
- **ProjectDiscovery** for subfinder tool
- **Open source community** for inspiration

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/snaprecon/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/snaprecon/discussions)
- **Security**: [Security Policy](SECURITY.md)

---

**⚡ Ready to start reconnaissance?** 

```bash
snaprecon test --domain yourdomain.com --scope-file scope.txt --test-count 5
```

**Happy hunting! 🎯**
