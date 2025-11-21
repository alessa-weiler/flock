# Security Policy

## Supported Versions

We take the security of Flock seriously. This section outlines which versions of Flock are currently being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

### Preferred Method: Private Security Advisory

1. Go to the [Security Advisories page](https://github.com/[YOUR-USERNAME]/flock/security/advisories)
2. Click "Report a vulnerability"
3. Fill out the form with details about the vulnerability
4. Submit the report

### Alternative Method: Email

Send an email to: alessa@pont.world

Include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

## What to Expect

After submitting a vulnerability report:

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours.

2. **Investigation**: We will investigate the issue and work to understand its scope and impact. This typically takes 1-5 business days.

3. **Communication**: We will keep you informed of our progress. If we need additional information, we will reach out.

4. **Resolution Timeline**:
   - **Critical vulnerabilities**: Patched within 7 days
   - **High severity**: Patched within 14 days
   - **Medium severity**: Patched within 30 days
   - **Low severity**: Patched in next regular release

5. **Disclosure**: We follow a coordinated disclosure process:
   - We will work with you to understand the issue and fix it
   - We will credit you in our security advisory (unless you prefer to remain anonymous)
   - We will publish a security advisory once a patch is released
   - We ask that you do not publicly disclose the vulnerability until we have released a patch

## Security Best Practices for Users

### Required Security Measures

1. **Environment Variables**
   - Never commit `.env` files to version control
   - Use strong, randomly generated secrets (see `.env.example`)
   - Rotate secrets regularly (every 90 days recommended)

2. **Database**
   - Use strong database passwords
   - Enable SSL/TLS for database connections in production
   - Regularly backup your database
   - Restrict database access to application servers only

3. **API Keys**
   - Restrict API key permissions to minimum required
   - Use separate API keys for development and production
   - Monitor API usage for anomalies
   - Rotate API keys if compromise is suspected

4. **Production Deployment**
   - Always use HTTPS in production
   - Enable HSTS (HTTP Strict Transport Security)
   - Set secure cookie flags (`SESSION_COOKIE_SECURE=True`)
   - Use a Web Application Firewall (WAF)
   - Keep all dependencies up to date

5. **Access Control**
   - Use role-based access control (RBAC)
   - Implement principle of least privilege
   - Regularly audit user permissions
   - Enable multi-factor authentication (MFA) for admin accounts

### Recommended Security Measures

1. **Monitoring**
   - Set up error tracking (e.g., Sentry)
   - Monitor for suspicious activity
   - Configure security alerts
   - Regular security audits

2. **Data Protection**
   - Encrypt sensitive data at rest
   - Use TLS 1.2+ for data in transit
   - Implement proper data retention policies
   - Regular security backups

3. **Rate Limiting**
   - Implement rate limiting on API endpoints
   - Use distributed rate limiting (Redis) in production
   - Monitor for abuse patterns

4. **Input Validation**
   - Validate all user inputs
   - Sanitize data before database operations
   - Use parameterized queries (already implemented)
   - Implement CSRF protection (Flask-WTF)

## Known Security Features

Flock implements several security features:

### ✅ Authentication & Authorization
- Session-based authentication with secure cookies
- Password hashing using Werkzeug (PBKDF2)
- Login required decorators for protected routes
- HTTPS enforcement in production

### ✅ Data Encryption
- Fernet symmetric encryption for sensitive data
- SHA-256 hashing for matching algorithms
- Secure random token generation
- GDPR compliance features

### ✅ API Security
- Stripe webhook signature verification
- Rate limiting on embedding service
- Circuit breaker pattern for external APIs
- Parameterized SQL queries (SQL injection prevention)

### ✅ Infrastructure Security
- Environment variable isolation
- No hardcoded secrets or credentials
- Comprehensive `.gitignore`
- Fail-fast on missing environment variables

## Security Audit History

| Date       | Type          | Auditor        | Findings | Status   |
|------------|---------------|----------------|----------|----------|
| 2024-11-12 | Full Audit    | Internal       | 9 issues | Resolved |

### Recent Security Improvements

**Version 1.0.0 (2024-11-12)**
- Fixed hardcoded secret keys
- Removed weak encryption defaults
- Eliminated API key logging
- Fixed undefined function references
- Implemented fail-fast configuration
- Comprehensive `.env.example` template

## Security Dependencies

We regularly monitor and update our dependencies for security vulnerabilities:

- **Dependabot**: Automated dependency updates (recommended to enable)
- **Snyk**: Continuous security monitoring (recommended)
- **GitHub Security Advisories**: We monitor for known vulnerabilities

### Updating Dependencies

To check for security vulnerabilities:

```bash
# Check for outdated packages
pip list --outdated

# Check for known vulnerabilities (requires pip-audit)
pip install pip-audit
pip-audit

# Update all dependencies
pip install -U -r requirements.txt
```

## Compliance

Flock is designed to help organizations comply with:

- **GDPR** (General Data Protection Regulation)
  - User data export (Article 15)
  - Right to be forgotten (Article 17)
  - Data encryption and anonymization
  - Processing logs and audit trails

- **SOC 2** considerations
  - Access controls
  - Encryption at rest and in transit
  - Audit logging
  - Data backup and recovery

## Bug Bounty Program

We currently do not have a formal bug bounty program, but we deeply appreciate security researchers who responsibly disclose vulnerabilities. We will:

- Publicly acknowledge your contribution (with your permission)
- Provide swag/merchandise for significant findings
- Consider implementing a formal bug bounty program in the future


## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/2.3.x/security/)

## License

This security policy is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

---

**Last Updated**: November 12, 2024
**Version**: 1.0.0
