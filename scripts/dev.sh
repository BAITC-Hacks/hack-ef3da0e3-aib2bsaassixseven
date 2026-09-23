#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

pids=()

cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait "${pids[@]}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

uv run --directory backend fastapi dev app/main.py --port 8000 &
pids+=("$!")

npm --prefix frontend run dev &
pids+=("$!")

echo "Tirke is starting:"
echo "  Web: http://localhost:3000"
echo "  API: http://localhost:8000/docs"
echo "Press Ctrl+C to stop both services."

wait -n "${pids[@]}"
