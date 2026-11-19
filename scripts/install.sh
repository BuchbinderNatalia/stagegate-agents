#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install stagegate-agents into a git repository.
#
# From a clone:   scripts/install.sh [TARGET] [--with-infra] [--force] [--dry-run]
# One command:    curl -fsSL https://raw.githubusercontent.com/BuchbinderNatalia/stagegate-agents/v0.1.0/scripts/install.sh \
#                   | bash -s -- [TARGET] [--with-infra]
#
# Piped mode downloads the PINNED release tarball (STAGEGATE_VERSION, never
# "latest") into a temp dir. Set STAGEGATE_SHA256 to the checksum published next to
# it on the release page (stagegate-agents-<version>.tar.gz.sha256) to verify it
# before anything runs; `gh attestation verify` also proves where it was built.
# Python 3.11+ required.
set -euo pipefail

STAGEGATE_VERSION="${STAGEGATE_VERSION:-v0.1.0}"
# The release asset built by .github/workflows/release.yml, not GitHub's auto-generated
# tag archive: those aren't guaranteed byte-stable, so a published checksum could break.
STAGEGATE_TARBALL_URL="${STAGEGATE_TARBALL_URL:-https://github.com/BuchbinderNatalia/stagegate-agents/releases/download/${STAGEGATE_VERSION}/stagegate-agents-${STAGEGATE_VERSION}.tar.gz}"

src=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  [ -f "$here/install.py" ] && [ -d "$here/../agents" ] && src=$(cd "$here/.." && pwd)
fi

if [ -z "$src" ]; then
  command -v curl >/dev/null 2>&1 || { echo "stagegate: curl is required" >&2; exit 1; }
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  echo "stagegate: downloading ${STAGEGATE_VERSION}"
  curl -fsSL --proto '=https,file' --tlsv1.2 -o "$tmp/stagegate.tar.gz" "$STAGEGATE_TARBALL_URL"
  if [ -n "${STAGEGATE_SHA256:-}" ]; then
    if command -v sha256sum >/dev/null 2>&1; then
      actual=$(sha256sum "$tmp/stagegate.tar.gz" | cut -d' ' -f1)
    else
      actual=$(shasum -a 256 "$tmp/stagegate.tar.gz" | cut -d' ' -f1)
    fi
    if [ "$actual" != "$STAGEGATE_SHA256" ]; then
      echo "stagegate: checksum mismatch (expected $STAGEGATE_SHA256, got $actual); aborting" >&2
      exit 1
    fi
    echo "stagegate: checksum verified"
  fi
  mkdir "$tmp/src"
  tar -xzf "$tmp/stagegate.tar.gz" -C "$tmp/src" --strip-components=1
  src="$tmp/src"
fi

# shellcheck source=lib/python.sh
. "$src/scripts/lib/python.sh"
py=$(stagegate_find_python)
"$py" -E -s "$src/scripts/install.py" "$@"
