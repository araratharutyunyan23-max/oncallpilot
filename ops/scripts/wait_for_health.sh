#!/usr/bin/env bash
# Poll a health endpoint until it returns 200 (or time out). Used by CI / smoke tests.
# Usage: wait_for_health.sh <url> [timeout_seconds]
set -euo pipefail
URL="${1:?usage: wait_for_health.sh <url> [timeout_seconds]}"
TIMEOUT="${2:-30}"
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -fsS "$URL" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "timed out waiting for $URL" >&2
    exit 1
  fi
  sleep 1
done
echo "healthy: $URL"
