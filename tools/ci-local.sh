#!/usr/bin/env bash
# Run tools/ci.sh exactly as CI does, in a fresh archlinux:base-devel Docker
# container, on the committed HEAD (uncommitted changes are not tested).
# The repository is mounted read-only and cloned inside the container.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE=archlinux:base-devel

log() {
  printf '{"timestamp":"%s","level":"%s","context":"ci-local","message":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" "$1" "$2" >&2
}
trap 'log error "local CI run failed (exit $?)"' ERR

if ! command -v docker >/dev/null; then
  log error "docker is not installed"
  exit 2
fi
url=$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)
log info "running CI on $(git -C "$ROOT" rev-parse --short HEAD) in $IMAGE"
start=$SECONDS
docker run --rm -e KH_REPO_URL="${KH_REPO_URL:-$url}" -v "$ROOT:/src:ro" "$IMAGE" bash -c '
  set -euo pipefail
  pacman -Syu --noconfirm --needed --noprogressbar git python >/dev/null
  git config --global --add safe.directory /src
  git clone --quiet /src /work
  exec /work/tools/ci.sh'
log info "local CI run passed in $((SECONDS - start))s"
