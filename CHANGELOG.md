<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - unreleased

First public release, extracted from the delivery pipeline of
[StarPulse](https://starpulse.dev) ([case study](docs/CASE_STUDY.md)).

### Added
- 10 core agents and 2 skills (`/feature-factory` with three human approval gates,
  `/build-with-tests`), rendered from templates with values from `stagegate.toml`.
- Optional infra pack: 9 agents (Terraform, Kubernetes, CI/CD, ArgoCD, monitoring), 3 skills
  and a hardened 3-stage deploy workflow: the plan is published to the run summary *before*
  the approval and apply refuses to run if it changed since; a read-only OIDC role for plans and
  a deploy role trusted only inside the production environment (no stored secrets at all);
  SHA-pinned actions; image-scan gate; GitOps wait on the exact revision. Infra agents run
  offline checks only, inside the sandbox.
- Guard hooks sharing one shell-command parser: commit guard (secrets, `:latest`, forbidden
  patterns, commits/pushes to the default branch, files added in the same command), merge gate
  (green CI only), load-test guard (local hosts only). Fail closed; block with exit 2.
- Claude Code sandbox on by default: credential stores unreadable, network allow-list.
- Stack profiles: `python`, `python-fastapi`, `react-ts`.
- One-command installer (pinned release, optional checksum), uninstaller and doctor.
- Opt-in pytest network guard template.
- 260+ offline tests with a fake `claude` and fake `gh`, a local-only live suite, and a
  success-rate eval with hidden acceptance tests.
- CI: tests on Python 3.11 and 3.14, gitleaks, trufflehog, CodeQL, OpenSSF Scorecard,
  dependency review, actionlint, zizmor, release with build provenance.

### Fixed (compared with the original StarPulse pipeline)
- The commit guard exited 1, which Claude Code treats as non-blocking, so it never blocked.
- Files `git add`-ed in the same command slipped past the commit guard.
- Builder agents told the agent to push to `main` after every file.
- The deploy pipeline used an unpinned action, long-lived cloud keys and an unverified CLI
  download; a GitOps wait could pass on the previous revision.

[0.1.0]: https://github.com/BuchbinderNatalia/stagegate-agents/releases/tag/v0.1.0
