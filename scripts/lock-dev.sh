#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Regenerate requirements-dev.lock (exact versions + sha256 hashes) from
# requirements-dev.in. CI installs it with --require-hashes, so a tampered or
# substituted package fails to install. Dependabot also updates this lock.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m piptools compile --quiet --generate-hashes --allow-unsafe \
  --strip-extras --no-emit-index-url \
  --output-file requirements-dev.lock requirements-dev.in
echo "requirements-dev.lock updated"
