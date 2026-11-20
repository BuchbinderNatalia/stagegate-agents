<!-- SPDX-License-Identifier: Apache-2.0 -->
# Running stagegate at scale

stagegate v0.1 is proven where it was built: one developer, one production platform, installed per
repository. This page is the design for taking it to an engineering organisation of hundreds of
developers and repositories. Each section says what exists **today** and what changes **at scale**,
so nothing here is presented as built when it isn't.

## What changes between 1 developer and 500

| Concern | One developer (today) | Organisation |
|---|---|---|
| Who can weaken a guard | the developer, by editing `.claude/settings.json` | nobody but the platform team |
| Who approves a gate | the developer, in the chat | an identified reviewer, recorded in a system of record |
| Where rules live | `stagegate.toml` in each repo | an org policy, plus per-repo settings the policy allows |
| How you know it works | 15 eval runs, a case study | eval suites on real internal repos, dashboards, audit logs |
| What it costs | one subscription | a budget per team, enforced |

## 1. Distribution: one package, many repositories

**Today:** `scripts/install.sh` renders agents, skills and hooks into each repository, pinned to a
release and verified by checksum.

**At scale:** package stagegate as a **Claude Code plugin** (agents, skills and hooks in one unit) in
an **internal plugin marketplace**, and force-enable it for every developer through managed settings.
Repositories keep only their `stagegate.toml` (test command, folders, stack profile). Upgrading
means bumping one plugin version instead of re-running an installer in hundreds of repositories, and
a bad release is rolled back the same way.

## 2. Enforcement: guards nobody can switch off

**Today:** the guards are registered in the repository's own `.claude/settings.json`, so a developer
(or an agent with write access to that file) could remove them.

**At scale:** deliver the guards and the sandbox through **managed settings**, which outrank every
user and project file and are pushed by device management or OS policy:

```json
{
  "allowManagedHooksOnly": true,
  "allowManagedPermissionRulesOnly": true,
  "sandbox": {
    "enabled": true,
    "allowUnsandboxedCommands": false,
    "network": {
      "allowManagedDomainsOnly": true,
      "allowedDomains": ["github.com", "api.github.com", "pypi.internal.example.com"]
    }
  }
}
```

- `allowManagedHooksOnly`: only the organisation's hooks run (plus force-enabled plugins), so a
  repository can't replace the merge gate with a no-op.
- `allowUnsandboxedCommands: false`: the sandbox becomes admin-required; no command opts out of it.
- `allowManagedDomainsOnly`: the network allow-list comes from the organisation only, pointing at
  internal package mirrors instead of the public internet.

The guards stay what they are today, guardrails that read commands. The sandbox and these locks are
the boundary.

## 3. Approvals tied to identity

**Today:** the three human gates (story, brief, result) are an "approved" typed in the conversation.
That's fine for one developer, and not evidence for an auditor.

**At scale:** keep the conversational gates for speed, but make the gates that matter live in
systems that record **who** approved **what**:

- **Code:** a pull request approval from someone other than the person who ran the agents
  (CODEOWNERS for sensitive paths), enforced by branch protection or an org-wide ruleset. A
  maintainer's agent session must never be able to approve its own PR.
- **Infrastructure:** the deploy workflow's apply job already waits for a GitHub **environment** with
  required reviewers, after the plan is published, and refuses a plan that changed. At scale, the
  reviewer list comes from the owning team, not the author.
- **Policy changes:** edits to agent prompts, guard code or managed settings go through the same PR
  and eval process as production code (section 6).

## 4. Observability and audit

**Today:** guard decisions aren't logged, so block rates can't be measured (the case study says so).

**At scale:**

- **Guard decision log:** every guard writes one JSON line per decision (guard, verdict, reason, repo,
  user, command hash, never the raw command or secrets), shipped to the SIEM. This is the next feature
  on the roadmap.
- **Claude Code telemetry:** enable the OpenTelemetry export for per-user and per-plugin token use,
  cost, tool activity and skill activations, into the existing observability stack.
- **Dashboards** the platform team actually uses:

| Signal | Why it matters |
|---|---|
| Guard blocks per 100 sessions, by guard and reason | rising = agents or people fighting the rules; falling to 0 = check the guard still runs |
| Gate rejections (story, brief, result) | how often humans catch the agents; a proxy for prompt quality |
| Validator/reviewer Critical findings per PR | quality trend of the builders |
| Escaped defects: incidents traced to agent-authored changes | the number leadership will ask for |
| Cost per merged PR, by team | budget control and ROI |
| Lead time and change failure rate (DORA), with vs. without stagegate | whether it's actually worth it |

## 5. Cost and data control

- **Spend limits:** route Claude Code through a gateway with per-user or per-team spend limits, and
  use the OpenTelemetry cost metrics for attribution.
- **Model per role:** keep cheap, fast models for research and story writing and stronger ones for
  building and reviewing. `stagegate.toml` already separates `models.fast` and `models.default`; the
  organisation sets defaults centrally.
- **Data residency:** where code must not leave a cloud boundary, run the model through the
  organisation's cloud provider (Amazon Bedrock, Google Cloud, Microsoft Foundry) instead of the
  public API. The sandbox's read denials keep credentials out of agent context regardless.

## 6. Quality: agents are code

Changing a prompt changes behaviour as much as changing a function, so treat it the same way:

1. **Versioned:** agents, skills and guards are released as one versioned plugin.
2. **Evaluated before rollout:** every change to an agent or guard runs the eval suite, on the
   public sample tasks *and* on 5–10 tasks taken from representative internal repositories (with a
   database, auth and an existing test suite), each judged by hidden tests.
3. **Compared with a baseline:** the same tasks run in a plain Claude Code session without stagegate.
   A change ships only if it keeps or improves pass rate, discipline and cost against the previous
   version.
4. **Staged rollout:** pilot team → 10 % of repositories → everyone, with the dashboards above as the
   gate between stages and a one-line rollback (pin the previous plugin version).

## 7. Rollout plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Pilot** | 1 platform team, 3–5 repos, guards in managed settings | guard log live; no Critical escapes; developers keep using it after week 2 |
| **1. Opt-in** | volunteer teams, internal marketplace | eval suite on internal repos beats the baseline; cost per PR within budget |
| **2. Default** | all repositories with a supported stack profile | gate rejection and block rates stable; incident review shows no agent-caused escapes |
| **3. Required** | sensitive repositories (payments, auth, infra) | identity-bound approvals and audit export accepted by security and compliance |

## 8. Open questions an organisation must answer

- Which repositories are out of scope (regulated code, customer data) until compliance signs off?
- Who owns the agents, the platform team or each product team, and who is on call for them?
- What is the policy when a guard blocks something legitimate: how fast can it be fixed, and is
  there a reviewed emergency override that is logged?
- Is the goal throughput (more features), quality (fewer escapes) or toil reduction? The dashboards
  and the eval baseline should measure that goal, not activity.

## Status

| Capability | v0.1 today | At scale |
|---|---|---|
| Install | per repo, pinned release + checksum | plugin from an internal marketplace, force-enabled |
| Guard enforcement | repo `settings.json` | managed settings, `allowManagedHooksOnly` |
| Sandbox | on by default, can be turned off per repo | admin-required, managed domain allow-list |
| Approvals | in conversation; deploy apply behind a GitHub environment | identity-bound PR and environment approvals |
| Audit | none for guard decisions | JSON decision log to the SIEM + OpenTelemetry |
| Evals | 5 sample tasks, live runs, stub mode in CI | internal-repo tasks, baseline comparison, gate for every agent change |
| Cost | per developer subscription | gateway spend limits, per-team attribution |
