# Security Policy

## Supported Versions

Deeper Notebook is an actively developed project. Security fixes are applied to the
**latest released version** only; there are no long-term support branches.

| Version | Supported          |
| ------- | ------------------ |
| Latest release (`1.x`, current minor) | :white_check_mark: |
| Older releases | :x: |

If you are running an older version, please upgrade to the latest release before
reporting an issue — the problem may already be fixed.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Instead, report them privately through GitHub's built-in **private vulnerability
reporting**:

1. Go to the [Security tab](https://github.com/Antman1526/Deeper-Notebook/security) of
   the repository.
2. Click **"Report a vulnerability"**.
3. Fill out the form with as much detail as you can.

This keeps the report private between you and the maintainers until a fix is
available.

When reporting, please include where relevant:

- A description of the vulnerability and its impact.
- Steps to reproduce (a proof of concept, affected endpoint/component, or sample
  configuration).
- The Deeper Notebook version and how you are running it (native app, Docker Compose,
  single-container, from source).
- Any suggested remediation, if you have one.

## What to Expect

- **Acknowledgement:** we aim to acknowledge a report within **5 business days**.
- **Assessment:** we will investigate, confirm the issue, and determine the
  affected versions.
- **Fix & disclosure:** once a fix is ready we will release it and, with your
  consent, credit you in the release notes. We follow a coordinated-disclosure
  approach and ask that you keep the report private until a fix is published.

## Scope

Deeper Notebook is **self-hosted**: you run the API, frontend, and SurrealDB
yourself, and you control the AI provider credentials. Please keep in mind:

- The built-in password middleware (`DEEPER_NOTEBOOK_PASSWORD`; legacy
  `OPEN_NOTEBOOK_PASSWORD`) is a basic access
  control, not a full authentication system. See
  [docs/5-CONFIGURATION/security.md](docs/5-CONFIGURATION/security.md) for
  hardening guidance (encryption key, reverse proxy, CORS, default credentials).
- Misconfiguration of your own deployment (e.g. exposing SurrealDB with default
  credentials, or running without `DEEPER_NOTEBOOK_ENCRYPTION_KEY`; legacy
  `OPEN_NOTEBOOK_ENCRYPTION_KEY`) is a
  deployment concern covered by that hardening guide rather than a vulnerability
  in the project — though we welcome reports where the defaults or docs actively
  steer users toward an insecure setup.

Thank you for helping keep Deeper Notebook and its users safe.
