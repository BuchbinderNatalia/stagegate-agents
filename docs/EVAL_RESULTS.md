<!-- SPDX-License-Identifier: Apache-2.0 -->
# Eval results

How often the agents get a feature right, measured with [`evals/run.py`](../evals/run.py) on five
tasks for the sample app. A run passes only if the work is on a feature branch with `main`
untouched, the existing tests still pass, the **hidden acceptance tests** (never shown to the
agents) pass, and an independent validator and reviewer each report 0 Critical findings.

## Live results

**Pending.** The first live run is scheduled before the v0.1.0 release; results (pass@1 over 3
runs per task, model, Claude Code version, date and cost) will replace this section.

## Harness check (stub mode)

Stub mode replays each task's reference solution through a fake `claude`. It proves the harness
grades correctly, not how good the agents are. It runs in CI.

| Task | Passed | Discipline | Suite | Hidden tests | Validator | Reviewer |
|---|---|---|---|---|---|---|
| csv-export | ✓ | ✓ | ✓ | ✓ | 0 Critical | 0 Critical |
| isbn-validation | ✓ | ✓ | ✓ | ✓ | 0 Critical | 0 Critical |
| remove-book | ✓ | ✓ | ✓ | ✓ | 0 Critical | 0 Critical |
| search-pagination | ✓ | ✓ | ✓ | ✓ | 0 Critical | 0 Critical |
| year-range | ✓ | ✓ | ✓ | ✓ | 0 Critical | 0 Critical |

The tests also confirm the harness fails what it should: a broken solution, work committed on
`main`, and the untouched app against every task's hidden tests.

## Reproduce

```bash
python evals/run.py --stub                       # free, offline
python evals/run.py --task csv-export --runs 1   # one live run (your Claude login, local only)
python evals/run.py --runs 3 --yes               # all tasks, 3 runs each
```
