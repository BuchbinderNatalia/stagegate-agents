<!-- SPDX-License-Identifier: Apache-2.0 -->
# Architecture

stagegate-agents is a set of files that Claude Code reads (agents, skills, settings, CLAUDE.md)
plus three small programs Claude Code runs before every shell command (the guard hooks). There is
no server and no runtime dependency: everything runs inside the user's repository with Python 3.11+.

## What gets installed

```
your-repo/
├── stagegate.toml                       one config file (yours to edit)
├── CLAUDE.md                            + a stagegate section between markers
├── .gitignore                           + secret/state patterns
├── .claude/
│   ├── settings.json                    + 3 PreToolUse hooks, sandbox settings (merged)
│   ├── agents/*.md                      10 core agents (+9 with --with-infra)
│   ├── skills/*/SKILL.md                2 core skills (+3 with --with-infra)
│   ├── stagegate/stack.md               stack profile all agents read
│   ├── hooks/stagegate/                 commit-guard.sh, merge-gate.sh, load-test-guard.sh, lib/
│   └── stagegate.manifest.json          hashes of what stagegate wrote (no-clobber, uninstall)
└── .github/workflows/stagegate-deploy.yml   only with --with-infra
```

Agents and skills are **rendered** from templates (`agents/`, `skills/`) with values from
`stagegate.toml` by `scripts/render.py`: a deliberately tiny, strict engine. Unknown keys,
unclosed blocks or leftover `{{` are errors, so a half-rendered prompt is never installed.
Hooks are copied verbatim and read `stagegate.toml` at run time, so guard settings take effect
without reinstalling.

## The delivery chain

| Step | Agent | Tools | Output |
|---|---|---|---|
| 1 | codebase-researcher | Read, Grep, Glob | relevant files, patterns, risks |
| 2 | story-writer | Read | user story + numbered acceptance criteria |
| ⛔ | **human** | | approves the story |
| 3 | spec-writer | Read, Grep, Glob | technical brief: signatures, API shapes, files |
| ⛔ | **human** | | approves the brief |
| 4 | test-strategist | Read, Grep, Glob | test plan: which layer, which owner |
| 5 | backend-builder / frontend-builder | Read, Edit, Write, Bash, Grep, Glob | code + unit tests on `feat/…` |
| 6 | test-verifier / e2e-test-writer | Read, Edit, Write, Bash, Grep, Glob | acceptance tests per AC |
| 7 | implementation-validator | Read, Grep, Glob | findings by severity, AC coverage |
| ↺ | | | Critical findings → back to the owning builder |
| ⛔ | **human** | | approves the result |
| 8 | pr-reviewer | Read, Grep, Glob, Bash (read-only git) | verdict on the PR |
| 🔒 | merge gate | | `gh pr merge` only when every check is green |

The orchestration lives in the `/feature-factory` skill. Each agent gets only the inputs it needs,
not the whole conversation. `/build-with-tests` is the same discipline without the gates, for small
changes. The infra pack mirrors this in `/infra-factory`: researcher → scope gate → builders per
layer (Terraform, Kubernetes, CI/CD, ArgoCD, monitoring) → implementation gate → validators →
final gate → reviewer.

## The guard hooks

Claude Code runs every `PreToolUse` hook registered for `Bash` before a command executes, passing
JSON on stdin. Exit **2** blocks the command and shows stderr to the agent; exit 0 allows it. Any
other exit code is a *non-blocking* error, which is why the guards never use `exit 1`.

```
Bash command ─► hooks/<guard>.sh ─► fast path: no keyword? exit 0 (no Python started)
                                 └► lib/run-guard.sh: find Python 3.11+ (else block)
                                    └► lib/<guard>.py ─► lib/shellwords.py: which commands REALLY run?
                                                     └► lib/config.py: stagegate.toml (else block)
                                                     └► allow (0) / block (2) + reason
```

`shellwords.commands()` turns a command string into the argv of each command that would run:
it splits on `;`, `&&`, `|`, newlines and backticks; drops heredoc bodies; strips wrappers
(`env`, `sudo -u x`, `timeout 30`, `xargs -I {}`, `VAR=1`); follows `bash -c`, `sh -c` and
`eval` up to three levels; and treats quoted text as data. So `git commit -m "gh pr merge"` is a
commit, not a merge, while `bash -c 'gh pr merge 3'` is a merge.

| Guard | Blocks |
|---|---|
| **commit guard** | committing secret/state files (`.env`, `*.pem`, `*.tfstate`, …), `image: …:latest`, configured forbidden patterns, commits on and pushes to the default branch. It also checks files a `git add` earlier in the same command will stage. |
| **merge gate** | `gh pr merge` (any form, incl. `--auto`) unless `gh pr checks` reports every check as pass/skipping. No checks at all also blocks. |
| **load-test guard** | k6, artillery, locust, wrk, hey, ab, … (directly, wrapped, or as a container image) aimed at a non-local host, in the command or in a referenced script. |

## The sandbox

`settings.json` turns on Claude Code's sandbox (Seatbelt on macOS, bubblewrap on Linux/WSL2) for
Bash: credential stores are unreadable (`~/.aws`, `~/.ssh`, `~/.kube`, `~/.config/gh`, …) and the
network is limited to GitHub and PyPI. `git fetch/pull/push` and `gh pr *` run outside it (they need
your credentials) but still go through permission prompts and the guards. Configure it in
`[sandbox]`. Hooks run outside the sandbox: they are Claude Code's own checks, not agent commands.

## Testing the factory itself

| Layer | Where | What |
|---|---|---|
| Unit | `tests/unit/` | parser, each guard (130+ cases), config, renderer, installer, agents, workflows, leak check |
| Integration | `tests/integration/` | a backend-builder cycle on `examples/sample-app` through the installed hooks; eval harness |
| E2E | `tests/e2e/` | PR → read-only review → merge gate blocks red/pending/missing CI → merges when green |
| Live (local, opt-in) | `tests/live/` | the same feature with the real `claude`, judged by hidden tests |
| Evals | `evals/` | 5 tasks × N runs, independent validator + reviewer sessions, pass@1 |

`tests/fixtures/fake-bin/claude` replays an agent transcript: Bash steps go through the hooks
registered in the installed `settings.json` with Claude Code's exit-code contract, and each agent's
`tools:` list is enforced. `fake-bin/gh` serves pull requests from a local bare remote.
