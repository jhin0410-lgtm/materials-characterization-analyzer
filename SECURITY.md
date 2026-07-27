# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch. Older tags or copied releases may not receive fixes.

## Reporting a vulnerability

Do not publish credentials, private instrument data, unpublished research data, customer information, or exploitable security details in a public issue.

Use GitHub's private vulnerability reporting or a private security advisory when that option is available for this repository. If no private reporting option is visible, open a minimal public issue that contains no sensitive details and asks the maintainer to establish a private communication channel.

Include, when possible:

- the affected version or commit;
- the affected command, module, or workflow;
- reproducible steps using synthetic or non-sensitive data;
- the security impact;
- whether credentials or private data may have been exposed;
- a proposed mitigation, if known.

## Credentials and data exposure

This project does not require committed credentials. Local secrets must be supplied through environment variables or untracked local configuration.

If a secret is accidentally committed, deleting it in a later commit is not sufficient. Revoke or rotate the credential immediately, then remove it from the repository and its Git history as appropriate.

Instrument exports and research datasets must be treated as potentially sensitive until ownership, publication status, anonymization, and redistribution rights are confirmed.
