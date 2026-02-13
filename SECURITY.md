# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### Private Disclosure

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, please report security issues privately:

1. **Email**: Contact the maintainer directly (see repository owner)
2. **GitHub Security Advisory**: Use GitHub's "Security" tab to report privately
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity, typically within 30 days

### What to Expect

1. **Acknowledgment**: We'll confirm receipt of your report
2. **Investigation**: We'll investigate and may request additional information
3. **Resolution**: We'll develop and test a fix
4. **Disclosure**: We'll coordinate public disclosure with you
5. **Credit**: You'll be credited in the security advisory (if desired)

## Security Best Practices

### Deployment Security

When deploying this application:

- **Always terminate TLS** at a reverse proxy (nginx, Traefik)
- **Enable Basic Auth** when exposed outside trusted networks
  ```bash
  BASIC_AUTH_ENABLED=true
  BASIC_AUTH_USERNAME=admin
  BASIC_AUTH_PASSWORD=strong_password_here
  ```
- **Keep secrets in .env** - Never commit secrets to version control
- **Use strong SECRET_KEY** for session encryption
- **Set TRUST_PROXY_COUNT** when behind a reverse proxy
- **Restrict Docker volumes** to least privilege
- **Keep dependencies updated** - Run `pip-audit` regularly

See [DEPLOYMENT_GUIDE.md](docs/operations/DEPLOYMENT_GUIDE.md) for comprehensive security guidance.

### Development Security

- **Never commit secrets** to version control
- **Use .env.example** as a template without real credentials
- **Review dependencies** before adding new packages
- **Run security scans**:
  ```bash
  # Install dev dependencies
  pip install -r requirements-dev.txt
  
  # Run security audit
  pip-audit
  
  # Run linter with security rules
  ruff check . --select S
  ```

### API Security

- **Rate limiting** is enabled on API endpoints
- **CSRF protection** on state-changing operations
- **Input validation** on all user inputs
- **SSRF protection** on URL inputs
- **File upload limits** enforced (default 500MB)

### Known Security Considerations

#### FlareSolverr

FlareSolverr is used to bypass Cloudflare protection. Consider:

- Run FlareSolverr in isolated network
- Limit access to trusted services only
- Monitor for unusual traffic patterns

#### External Services

This application integrates with external services:

- **RAGFlow**: Ensure API tokens are scoped appropriately
- **Paperless-ngx**: Use read-write tokens only for the application
- **Ollama/LLM**: Be aware of prompt injection risks in document processing

## Security Features

### Built-in Protections

- **CSP Headers**: Content Security Policy prevents XSS
- **HSTS**: HTTP Strict Transport Security (when using HTTPS)
- **Rate Limiting**: Prevents abuse of API endpoints
- **Input Validation**: Length and format validation on all inputs
- **Secure Defaults**: Authentication disabled in dev, required in production

### Audit Log

Application logs security-relevant events:

- Authentication failures
- Authorization denials
- SSRF attempts
- Malformed requests
- Rate limit violations

See [LOGGING_AND_ERROR_STANDARDS.md](docs/development/LOGGING_AND_ERROR_STANDARDS.md) for log details.

## Dependency Security

### Automated Scanning

- **GitHub Dependabot**: Monitors dependencies for known vulnerabilities
- **CI Pipeline**: Runs `pip-audit` on every commit
- **Container Scanning**: Trivy scans Docker images

### Manual Auditing

Run security audit locally:

```bash
# Install audit tool
pip install pip-audit

# Run audit
pip-audit -r requirements.txt
```

### Pinned Dependencies

All dependencies are pinned in `requirements.txt` with constraints in `constraints.txt` to ensure reproducible, auditable builds.

## Security Updates

Security patches will be:

1. Developed in private
2. Tested thoroughly
3. Released as soon as possible
4. Announced in release notes and GitHub Security Advisories
5. Backported to supported versions when critical

## Security Checklist for Deployment

- [ ] TLS certificate configured and valid
- [ ] HSTS enabled in reverse proxy
- [ ] Strong SECRET_KEY generated
- [ ] BASIC_AUTH_ENABLED=true if exposed externally
- [ ] TRUST_PROXY_COUNT configured correctly
- [ ] All API tokens/keys in .env (not hardcoded)
- [ ] File permissions restricted on config/data/logs directories
- [ ] FlareSolverr access restricted to application only
- [ ] Dependencies up to date (pip-audit passing)
- [ ] Log aggregation configured for security monitoring
- [ ] Backups configured and tested
- [ ] Incident response plan documented

## Vulnerability Disclosure Policy

### Scope

In scope:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF
- Remote code execution
- Information disclosure
- SSRF and other injection vulnerabilities

Out of scope:

- Denial of service (unless critical)
- Social engineering
- Physical attacks
- Issues in third-party dependencies (report to upstream)

### Safe Harbor

We support security research conducted:

- In good faith
- Without violating privacy or causing harm
- With responsible disclosure

We will not pursue legal action against researchers who:

- Follow our disclosure policy
- Make good faith efforts to avoid privacy violations
- Don't access data beyond what's necessary to demonstrate the vulnerability

## Contact

For security concerns:

- **Security Issues**: Use GitHub Security Advisory (preferred)
- **General Contact**: See repository maintainer information

Thank you for helping keep this project secure!
