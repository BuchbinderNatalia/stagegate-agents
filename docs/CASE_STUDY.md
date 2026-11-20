<!-- SPDX-License-Identifier: Apache-2.0 -->
# Case study: StarPulse

stagegate-agents was not designed on a whiteboard. It was extracted from the delivery pipeline
of **[StarPulse](https://starpulse.dev)**, a production web app that tracks GitHub repositories'
star velocity and predicts breakouts: FastAPI and MongoDB behind a React frontend, on AWS EKS
with Terraform, Helm, Vault, Keycloak, ArgoCD and a Prometheus/Grafana/Loki stack. One developer
ran it end to end with the agents in this repo.

Everything below comes from StarPulse's git history, pull requests and GitHub Actions runs
(snapshot 19 November 2026). The repository is private, so PRs are cited by number only, and
only aggregates are published: no code, account IDs or internal hostnames.

## At a glance

| | |
|---|---|
| Period | 14 Apr – 19 Nov 2026 (about 7 months) |
| Commits on `main` | 645, of which **388 co-authored by Claude** |
| Merged pull requests | **56**, every one carrying the Claude Code attribution |
| PRs by type | 25 fix · 14 feat · 12 docs · 5 chore (by branch prefix) |
| Backend tests | **2 → 123** test functions |
| Coverage floor (CI-enforced ratchet) | **55% → 65% → 74% → 82%** |
| Test workflow runs (PRs and deploy stage 0) | 75 of 75 green |
| Production deploys since the full gate set (14 Nov) | **18 of 21 succeeded (86%)** |

## The reviewer agents caught real problems

Fourteen PR descriptions record what the validator and reviewer agents found before merge.
Counting only what those descriptions state explicitly:

- **At least 5 Critical findings, all fixed before merge.**
  - #4: `infra-validator` found a hardcoded secret that the pipeline would have **echoed
    unmasked into the GitHub Actions logs**.
  - #15: `pr-reviewer` returned *REQUEST CHANGES* with two Critical findings in the Vault
    automation; both were fixed in a follow-up commit, and an Important one stopped a
    `vault kv put` from silently wiping unrelated secrets.
  - #33: `pr-reviewer` found runbooks that still applied the raw manifests directly.
  - #52: `implementation-validator` found the new MCP endpoint answered with a redirect instead
    of serving requests.
- **At least 12 Important findings** fixed across #15, #28, #39, #41 and #45, plus more in #31,
  #32 and #33 whose descriptions don't give a count.
- **Several rounds when needed.** #18 (moving the frontend to EKS) went through three
  `infra-validator` rounds and two independent `pr-reviewer` rounds; the second reviewer pass
  found two problems the first had missed.

The reviewers were not always right, and the PRs say so. In #33 a reviewer claimed a merge
conflict that `git merge-tree` showed did not exist. In #41 a reviewer doubted a model ID because
its training data predated it. Both claims were checked and rejected with evidence, which is the
point of keeping a human at the gates.

## Gates that hold by themselves

- **Tests gate the deploy.** The test workflow is stage 0 of the production pipeline: a red test
  stops Terraform, Helm and the rollout before anything touches AWS. A network guard fails any
  test that tries to reach an outside host, so no test can spend LLM tokens or hit GitHub's rate
  limit.
- **Coverage only goes up.** The floor in CI rose from 55% to 82% as tests were added and is
  never lowered.
- **The image scan blocks vulnerable builds.** The first frontend image hit the scan gate with
  **43 CRITICAL/HIGH CVEs**, and the fix (#22) was a different base image, not a weaker gate. An
  earlier scan caught a **CRITICAL JWT auth-bypass CVE** in the backend's token library (#7).
- **The merge gate blocks red PRs.** On a free private repo GitHub can't require status checks,
  so a Claude Code hook refuses `gh pr merge` until every check is green.

## Deploys

From 14 November, when the test gate, merge gate, coverage floor and network guard were all in
place, **18 of 21 production deploys succeeded (86%)**. Earlier pipeline history covers
infrastructure bring-up (creating and rebuilding the cluster, platform services and networking)
and isn't comparable.

## What porting it taught us

Extracting the factory into this repo was itself a review, and it found bugs in the original
that are now fixed in both places:

- The commit guard exited with code 1, which Claude Code treats as a **non-blocking** error,
  so it never actually blocked a commit. It also missed files added in the same command
  (`git add -f .env && git commit`).
- Two builder agents told the agent to `git push origin main` after every file, contradicting
  their own branch rule.
- Nothing mechanically stopped a commit on, or a push to, the default branch. stagegate now
  blocks both by default.
- The deploy pipeline used a branch-pinned action (`@master`), long-lived cloud keys and an
  unverified CLI download; the template here uses SHA-pinned actions, OIDC and no CLI at all.

## Not measured

The guards didn't log their blocks, so these numbers don't exist and aren't estimated:
how often the merge gate stopped a red merge, how often the load-test guard stopped a remote load
test, and how often the network guard caught a test reaching the internet. Logging guard
decisions is on the roadmap.

## How the numbers were produced

All read-only, from a clone of the private repository:

```bash
git rev-list --count origin/main                              # commits
git log origin/main --format=%B | grep -c "Co-Authored-By: Claude"
gh pr list --state merged --limit 500 --json number,title,body,headRefName
gh run list --workflow deploy.yml --limit 1000 --json conclusion,createdAt
git log -p -- backend/.coveragerc                             # coverage floor history
git grep -E "def test_" -- backend/tests                      # test functions
```
