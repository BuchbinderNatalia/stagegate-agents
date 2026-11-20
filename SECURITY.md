<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security policy

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through GitHub:
**Security → Report a vulnerability** on this repository
([private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).

Include what's affected (guard, installer, workflow template, agent), how to reproduce it, and the
impact. You'll get an acknowledgement within 7 days and a fix or a plan within 30 days. Credit is
given in the advisory unless you prefer otherwise.

**In scope:** a way to get a command past a guard that the docs say is blocked; the installer
writing outside the target repository or overwriting user files; secrets exposure through
templates or workflows; supply-chain issues in releases.

**Known limits, not vulnerabilities:** the gaps listed in
[GOVERNANCE.md](docs/GOVERNANCE.md#known-gaps) (merges via the web UI, commands assembled at
runtime, Bash not being restrictable per agent).

## Supported versions

The latest release receives fixes. Pin installs to a release tag and verify them (checksum or
`gh attestation verify`), as the README shows.

## If a secret leaks (runbook)

For maintainers of this repository, and a good default for repositories using stagegate:

1. **Revoke or rotate the credential first**, at the provider (cloud console, GitHub settings,
   API dashboard). Removing it from git doesn't un-leak it; assume it's already copied.
2. **Check for use**: provider audit logs for the exposure window.
3. **Remove it from history** if the repository may become public or is shared:
   `git filter-repo --replace-text <file>`, force-push, and ask collaborators to re-clone.
   GitHub caches may keep old commits; contact GitHub Support for sensitive data removal.
4. **Find out how it got in** and add a guard: a `blocked_files` pattern, a
   `forbidden_patterns` regex, or a gitleaks rule.
5. **Record it**: what leaked, for how long, what was rotated, what changed.

## How this repository protects itself

gitleaks on every push (full history) and pre-commit; weekly trufflehog verification; a leak check
with a private denylist; CodeQL; OpenSSF Scorecard; dependency review; actionlint and zizmor;
SHA-pinned actions; hash-locked dev dependencies; signed build provenance on releases.
