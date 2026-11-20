<!-- SPDX-License-Identifier: Apache-2.0 -->
# Extending stagegate-agents

## Configure before you extend

Most changes need only [`stagegate.toml`](../templates/stagegate.toml): test and lint commands,
folders, branch prefix, models, sandbox domains, guard patterns, infra values. After editing
`[stack]`, `[models]` or `[sandbox]`, re-run `scripts/install.sh`; guards read the file live.

```toml
[stack]
run_prefix = "docker compose run --rm app"   # run tests inside your container

[guards]
forbidden_hosts = ["shop.example.com"]        # never load-test production
forbidden_patterns = ['from legacy_sdk import']  # a banned import, blocked at commit time

[models]
default = "opus"                              # or a full model ID to pin one
```

## Block network calls in your tests

Copy [`templates/tests/network_guard.py`](../templates/tests/network_guard.py) next to your tests
and add `pytest_plugins = ["network_guard"]` to `conftest.py`. Any test that tries to reach a
non-local host then fails, even if the code under test catches the error. Allow extra hosts with
`NETWORK_GUARD_ALLOW=testserver,minio`.

## Add a stack (e.g. Java)

The agents are stack-neutral; stack knowledge lives in `stacks/<profile>.md`, installed as
`.claude/stagegate/stack.md`.

1. Create `stacks/java.md` with the four sections every profile has: **Structure**, **Patterns**,
   **Tests**, **Review checklist** (the validator and reviewer use the checklist). Copy
   [`stacks/python.md`](../stacks/python.md) as a starting point.
2. In the project's `stagegate.toml`:
   ```toml
   [stack]
   language = "java"
   profile = "java"
   backend_dir = "src/main/java"
   tests_dir = "src/test/java"
   test_command = "./mvnw -q test"
   lint_command = "./mvnw -q spotless:check"
   ```
3. Add the build tool's hosts to `[sandbox] allowed_domains` (e.g. `repo.maven.apache.org`).
4. Run `scripts/install.sh`. The tooling itself still needs Python 3.11+ on the machine; the app
   doesn't.

## Add an agent

1. Create `agents/core/<name>.md.tmpl` (or `agents/infra/`): YAML frontmatter with `name`,
   `description` (when to use it: Claude reads this to decide), `model: {{ models.default }}` and
   the **smallest** `tools:` list that works, then the SPDX comment, then the prompt.
2. Use template values instead of hardcoding: `{{ project.name }}`, `{{ cmd.test }}`,
   `{{ project.default_branch }}`, `{{#if stack.frontend_dir}}…{{/if}}`, partials such as
   `{{> infra-rules }}`.
3. If it should install only sometimes, add it to `AGENT_REQUIRES` in `scripts/render.py`.
4. Wire it into a skill (`skills/core/feature-factory/SKILL.md.tmpl`) and add it to the agent
   lists in `tests/unit/test_agents.py`; the tests check frontmatter, tool privileges and that the
   chain only names agents that exist.

## Add a guard

1. Write the logic in `hooks/lib/<guard>.py`: read the payload with `hookio.read_payload()`, find
   real commands with `shellwords.commands()`, load settings with `config.load()`, and end with
   `hookio.allow()` or `hookio.block(name, reasons)`. **Never exit 1**: Claude Code treats it as
   non-blocking.
2. Add a wrapper `hooks/<guard>.sh` with a fast path (a `case` on a keyword) and `run_guard`.
3. Add its name to `HOOKS` in `scripts/render.py` and `HOOK_FILES` in `scripts/install.py`.
4. Write tests in `tests/unit/hooks/`: allowed mentions (quotes, heredocs, commit messages) *and*
   blocked forms (wrappers, `bash -c`, `eval`, newlines). Most guard bugs live in that list.

## Other clouds and delivery tools

The infra pack's reference implementation is AWS + EKS + ArgoCD. To adapt it:

- **Agents** describe practices (remote state, pinned images, least privilege, dry runs), not AWS
  APIs; set `infra.cloud`, `cluster` and `registry`, and edit the few AWS examples in
  `agents/infra/*.md.tmpl` if you need to.
- **Workflow template** (`templates/workflows/deploy-3stage.yml.tmpl`): swap
  `aws-actions/configure-aws-credentials` for your cloud's OIDC login (e.g.
  `google-github-actions/auth`, `azure/login`) and `aws eks update-kubeconfig` for its equivalent.
  Keep SHA pinning. The workflow-lint CI job lints the rendered result.
- **No ArgoCD:** `gitops = "none"` installs 6 infra agents and a kubectl-based deploy stage.

## Running real agents in CI (not done here)

This repo never stores a Claude credential in CI: live tests and evals run locally with your login.
If you want nightly live runs in your fork: use a GitHub **environment** with required reviewers,
store `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or a spend-capped `ANTHROPIC_API_KEY`
there, trigger only on `schedule`/`workflow_dispatch` (never on PRs from forks), and keep the sandbox
on with `fail_if_unavailable = true`.
