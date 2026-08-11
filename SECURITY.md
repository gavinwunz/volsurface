# Security Policy

## Supported versions

Only the latest released version of VolFoundry receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

Pre-release (`<0.1.0`) versions are development snapshots and are not
supported for security fixes.

## Reporting a vulnerability

If you discover a security vulnerability in VolFoundry, please report it
privately. Do not open a public issue.

### What to include

- A clear description of the vulnerability.
- Steps to reproduce, including a minimal example if possible.
- The VolFoundry version, Python version, and operating system.
- Whether the issue depends on optional dependencies or a specific
  build configuration.

### How to report

Email the maintainer directly at the address listed on the PyPI package
page (or on the GitHub profile). You should receive an acknowledgment
within a reasonable timeframe.

Once confirmed, we aim to release a fix within a reasonable period and
will credit the reporter (unless you prefer to remain anonymous).

## Scope

VolFoundry is a quantitative research and educational library. Security
concerns primarily relate to:

- Deserialization of untrusted inputs via snapshot/persistence
  functionality.
- HTTP interactions with the public Deribit API via the optional live
  data adapter.
- Dependency chain vulnerabilities.

## Responsible disclosure

Please allow reasonable time for a fix to be released before disclosing
details publicly. We follow coordinated vulnerability disclosure best
practices and will work with reporters to establish a timeline.