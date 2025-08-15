# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### 1. **DO NOT** create a public GitHub issue
- Security vulnerabilities should be reported privately
- Public disclosure can put users at risk

### 2. **DO** report via email
- Send details to: security@yourdomain.com
- Include "SECURITY VULNERABILITY" in the subject line
- Provide detailed description and reproduction steps

### 3. **DO** expect a response within 48 hours
- We will acknowledge receipt within 24 hours
- We will provide updates on the investigation
- We will coordinate disclosure if needed

## Security Features

### API Key Protection
- **No API keys stored** in results or reports
- **SafeConfig model** excludes sensitive data
- **Environment variables** for secure configuration

### Scope Enforcement
- **Mandatory scope files** prevent unauthorized targets
- **Domain validation** ensures compliance
- **Rate limiting** prevents abuse

### Data Privacy
- **Local processing** - no data sent to external services except Gemini
- **Configurable retention** - results can be automatically cleaned up
- **No telemetry** - no usage data collected

## Best Practices

### For Users
1. **Keep API keys secure** - never commit them to version control
2. **Use scope files** - limit targets to authorized domains only
3. **Monitor costs** - set appropriate limits to prevent unexpected charges
4. **Regular updates** - keep SnapRecon updated for security patches

### For Developers
1. **Security reviews** - all code changes require security review
2. **Dependency scanning** - regular vulnerability scans of dependencies
3. **Access control** - limited access to sensitive areas of the codebase
4. **Audit logging** - all security-relevant actions are logged

## Disclosure Policy

### Timeline
- **Initial response**: Within 48 hours
- **Investigation**: 1-2 weeks depending on complexity
- **Fix development**: 1-4 weeks depending on severity
- **Public disclosure**: Coordinated with security researchers

### Credit
- Security researchers will be credited in advisories
- CVE numbers will be requested for significant issues
- Responsible disclosure timeline will be respected

## Contact

- **Security Email**: security@yourdomain.com
- **PGP Key**: [Available on request]
- **Response Time**: 24-48 hours

---

**Thank you for helping keep SnapRecon secure! 🔒**
