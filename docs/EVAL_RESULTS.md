<!-- SPDX-License-Identifier: Apache-2.0 -->
# Eval results

How often the agents get a feature right, measured with [`evals/run.py`](../evals/run.py) on five
tasks for the sample app. Each run is a fresh copy of the app with stagegate installed and no git
remote, and makes three separate Claude Code sessions: `backend-builder` implements the brief,
then `implementation-validator` and `pr-reviewer` judge it independently. A run passes only if:

- **discipline:** the work is on a feature branch with at least one commit, a clean tree and
  `main` untouched
- **suite:** the app's existing tests still pass
- **hidden tests:** acceptance tests the agents never see pass
- **validator** and **reviewer** each report 0 Critical findings

## Live results (20 November 2026)

**pass@1: 15 / 15 runs (100%).** The reviewer gave a clean *APPROVE* on 12 / 15.

| Task | Passed | Reviewer approved | Avg time | Avg cost |
|---|---|---|---|---|
| csv-export | 3/3 | 3/3 | 156 s | $0.16 |
| isbn-validation | 3/3 | **0/3** (see below) | 185 s | $0.21 |
| remove-book | 3/3 | 3/3 | 162 s | $0.18 |
| search-pagination | 3/3 | 3/3 | 180 s | $0.17 |
| year-range | 3/3 | 3/3 | 144 s | $0.14 |
| **Total** | **15/15** | **12/15** | **166 s** | **$2.60** |

Every run passed discipline, suite and hidden tests, with 0 Critical findings from both judges.
Setup: Claude Code 2.1.329, agents on the `sonnet` alias (Claude Sonnet 5.5), macOS, sandbox
forced on (`fail_if_unavailable = true`). On average a run took 18 turns across its three
sessions. Cost is the API-equivalent `total_cost_usd` Claude Code reports; on a subscription it
counts against plan usage rather than being billed. The code under test was commit `f78eb71`
(stagegate PR #2).

### What the reviewer caught: a bug in the task, not the code

On all three isbn-validation runs the builder implemented the brief exactly, the hidden tests
passed, and the reviewer still returned **REQUEST CHANGES** with the same Important finding. The
brief asked to accept ISBNs written with hyphens or spaces **and** to "keep the ISBN exactly as
given". That means `9780441013593` and `978-0-441-01359-3`, the same book, are stored under
different keys and both get added, silently bypassing `DuplicateBookError`. The reference
solution has the same flaw. The reviewer found a design defect in the human-written spec
consistently, which is the reviewer's job. It counts as a pass under the 0-Critical rule, and is
reported here rather than hidden behind it.

**Corrected (task v2):** the brief now says the catalogue identifies books by the normalized ISBN,
so the same ISBN in another format is a duplicate and `get()` finds a book by any format. Two new
hidden tests cover exactly this. The v1 reference solution fails them, so the grading itself now
catches what the reviewer caught. The v1 results above stay as they were measured; v2 results
will be added below when they've been run.

### The run before these: a stagegate bug

The first live run (csv-export, before PR #2) failed the discipline check although the builder did
everything right. The cause was stagegate's own guard hooks, which wrote an untracked
`__pycache__/` into the repository. The builder also reported that `ruff check .` failed on the
installed hook files. Both were fixed in PR #2 (guards run with `python -B`, and the hook code now
passes a strict lint) with regression tests. That run is not counted above; the next run, on the
fixed code, passed.

## Harness check (stub mode)

Stub mode replays each task's reference solution through a fake `claude`. It proves the harness
grades correctly, not how good the agents are, and it runs in CI. All five tasks pass, and the
tests also confirm the harness fails what it should: a broken solution, work committed on `main`,
and the untouched app against every task's hidden tests.

## Reproduce

```bash
python evals/run.py --stub                       # free, offline
python evals/run.py --task csv-export --runs 1   # one live run (your Claude login, local only)
python evals/run.py --runs 3 --yes               # all tasks, 3 runs each
```
