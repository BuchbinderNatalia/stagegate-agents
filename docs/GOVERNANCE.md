<!-- SPDX-License-Identifier: Apache-2.0 -->
# Governance: safeguards, OWASP agentic risks and known gaps

stagegate-agents is a **delivery process** with guardrails: stages, human approval gates,
least-privilege agents, guard hooks, the OS sandbox and CI gates. It is not a runtime policy engine
for agents in general. This page maps what it does against the
[OWASP Top 10 for Agentic Applications (2026)](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/),
says plainly what it doesn't cover, and shows how to add a policy layer.

## Safeguards

| Safeguard | Mechanism | Enforced by |
|---|---|---|
| Human approval gates | story, brief and result need an explicit "approved" | skill instructions + you |
| Least-privilege agents | read-only roles have no Edit/Write/Bash | Claude Code tool lists; tested in CI |
| Commit guard | no secrets/state files, `:latest`, forbidden patterns, commits/pushes to `main` | PreToolUse hook, exit 2 |
| Merge gate | no `gh pr merge` unless every CI check is green | PreToolUse hook, exit 2 |
| Load-test guard | load tools only against local hosts | PreToolUse hook, exit 2 |
| Sandbox | no credential stores, network only to allowed domains | Claude Code sandbox (OS level) |
| Network guard (opt-in) | tests can't reach external hosts; swallowed calls still fail the test | `templates/tests/network_guard.py` in your test suite |
| Independent validation | validator/reviewer check code, not the builder's summary | separate agents (separate sessions in evals) |
| CI gates | tests, scan, coverage floor before deploy | GitHub Actions |
| Supply chain | SHA-pinned actions, hash-locked tools, OIDC, provenance | workflows + lock files |

## Mapping to the OWASP agentic risks

Titles from OWASP's [announcement](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/);
see OWASP for the full definitions. "Partial" means stagegate reduces the risk but doesn't remove it.

| Risk | How stagegate reduces it | Coverage |
|---|---|---|
| **ASI01 Agent Goal Hijack** | Human gates on story, brief and result; validator checks the result against the *approved* criteria; the sandbox limits what a hijacked agent can reach | Partial |
| **ASI02 Tool Misuse** | Per-agent tool lists; guards block destructive or unsafe commands (secrets, `main`, red merges, remote load tests) regardless of what the agent intends | Partial |
| **ASI03 Identity & Privilege Abuse** | Sandbox denies reading `~/.aws`, `~/.ssh`, `~/.kube`, `gh` and other credential stores; CI uses OIDC, not stored keys; infra agents never apply or touch a live cluster | Partial |
| **ASI04 Agentic Supply Chain Vulnerabilities** | Pinned release + checksum + provenance for the installer; SHA-pinned actions; hash-locked dev tools; dependency review; agents need human approval for new dependencies | Partial |
| **ASI05 Unexpected Code Execution** | Sandbox around every Bash command; network allow-list; read-only agents can't run commands at all | Partial |
| **ASI06 Memory & Context Poisoning** | Each agent gets only the inputs it needs, not the whole conversation; instructions come from versioned files you review in git | Limited |
| **ASI07 Insecure Inter-Agent Communication** | Agents communicate only through the orchestrating session and files in your repo, with human gates between stages; no agent-to-agent network channel exists | Limited (by design) |
| **ASI08 Cascading Failures** | Fail-closed guards; validation loop must reach 0 Critical; CI test gate stops the deploy pipeline before infrastructure changes | Partial |
| **ASI09 Human-Agent Trust Exploitation** | Gates ask for an explicit decision on the full artifact; validators cite `path:line`; the case study documents reviewer false positives instead of hiding them | Limited |
| **ASI10 Rogue Agents** | Guards and sandbox don't depend on the agent's cooperation; the merge gate holds even if an agent wraps the command in `bash -c` | Partial |

## Known gaps

- **Hooks are guardrails, not a security boundary.** They can't see merges done in the GitHub web
  UI or REST API, commands assembled at runtime (variables, aliases, scripts that call `gh`
  internally) or `env -S`. Use branch protection where your plan allows it.
- **One known false positive (fails safe).** Quotes nested inside a quoted command substitution,
  e.g. `git commit -m "$(msg "title" "…gh pr merge 1…")"`, can make quoted text look like a
  command, so the guard blocks it. Simple quoted mentions, single quotes and heredocs are handled.
  Put such messages in a file (`git commit -F msg.txt`) or a heredoc. Fixing this properly needs a
  full shell parser, which would add the project's first runtime dependency.
- **The sandbox covers Bash, not every tool**, and commands in `excluded_commands` run outside it
  (by default `git fetch/pull/push` and `gh pr *`, still behind permission prompts and guards).
- **pr-reviewer's "read-only git"** is an instruction: Claude Code can't restrict Bash to specific
  commands per agent. It has no Edit/Write, and the guards still block merges and unsafe commits.
- **Gates rely on a human reading.** stagegate makes the decision explicit; it can't make it careful.
- **Guard decisions aren't logged yet**, so block rates can't be measured (see the case study).

## Adding a runtime policy layer

For policy enforcement beyond delivery (prompt inspection, per-tool allow/deny/ask policies,
redaction), run Microsoft's [Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)
next to stagegate. Its Claude Code plugin adds `SessionStart`, `UserPromptSubmit` and `PreToolUse`
hooks; stagegate's guards are also `PreToolUse` hooks, so both run on every Bash command and a
block from either one stops it. Install the plugin as its README describes, keep stagegate's hooks
registered, and check with a command both should block (e.g. committing `.env`).

This combination is documented, not yet covered by stagegate's automated tests. No toolkit code is
included here, so there's no license mixing (it is MIT; stagegate is Apache-2.0).
