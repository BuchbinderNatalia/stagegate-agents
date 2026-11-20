<!-- SPDX-License-Identifier: Apache-2.0 -->
# Contributing

Thanks for helping! Issues and pull requests are welcome. For anything large, open an issue first
so we can agree on the approach.

## Set up

```bash
git clone https://github.com/BuchbinderNatalia/stagegate-agents.git && cd stagegate-agents
python3 -m venv .venv && . .venv/bin/activate          # Python 3.11+
pip install --require-hashes -r requirements-dev.lock  # exact, hash-checked dev tools
pre-commit install                                     # gitleaks, ruff, shellcheck, SPDX, leak check
```

## Before you open a PR

```bash
pytest                       # 260+ offline tests (unit, integration, E2E); ~10 min on a laptop
ruff check . && ruff format --check .
pre-commit run --all-files
python evals/run.py --stub   # the eval harness, offline and free
```

Live tests and evals use your own Claude Code login and run **locally only**:
`STAGEGATE_LIVE=1 pytest tests/live` and `python evals/run.py --task csv-export`.

## Guidelines

- **Guards:** every change needs tests for both what must be blocked (wrappers, `bash -c`, `eval`,
  newlines) and what must stay allowed (quotes, heredocs, commit messages). Block with exit 2,
  never 1.
- **Agents:** keep the smallest tool list; read-only roles stay read-only (a test enforces it).
  Keep templates stack-neutral; stack rules go in `stacks/`.
- **No project-specific values:** no account IDs, real domains or emails. Use placeholders such as
  `<AWS_ACCOUNT_ID>` and `example.com`. The leak check and gitleaks run on every commit.
- **Dependencies:** none at runtime. For a dev tool, add it to `requirements-dev.in` *and* the
  `dev` group in `pyproject.toml`, then run `scripts/lock-dev.sh`. Packages that download binaries
  at build time are not accepted (they bypass the hash lock).
- **Actions:** pin to a full commit SHA with the version in a comment.
- **Files:** start source files with `SPDX-License-Identifier: Apache-2.0`.
- **Commits:** conventional style (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`). AI-assisted
  commits are welcome; keep the co-author trailer.

## License

By contributing you agree that your contribution is licensed under [Apache-2.0](LICENSE).
