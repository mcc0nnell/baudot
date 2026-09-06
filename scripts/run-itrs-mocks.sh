#!/usr/bin/env bash
set -euo pipefail

PORT="${ITRS_MOCK_PORT:-8799}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mvn -q -DskipTests compile

java -cp target/classes org.mcc0nnell.baudot.itrs.ItrsMockServer "$PORT" &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in {1..20}; do
  if curl --fail --silent "http://127.0.0.1:${PORT}/health" >/dev/null; then
    break
  fi
  sleep 0.1
done

curl --fail --silent "http://127.0.0.1:${PORT}/health" >/dev/null
java -cp target/classes org.mcc0nnell.baudot.itrs.ItrsMockProbe "http://127.0.0.1:${PORT}"
