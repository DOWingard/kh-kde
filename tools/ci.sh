#!/usr/bin/env bash
# Every check this project has, run in a clean Arch Linux system:
#   build both variants -> unit and integration tests -> offscreen renders ->
#   the decoration under a headless KWin -> the AUR package built by makepkg.
#
# CI runs this as root in an archlinux:base-devel container. The root part
# installs the packages the PKGBUILD declares plus what the checks need, so a
# dependency missing from the PKGBUILD fails here as it would for an AUR user.
# The rest runs unprivileged, as makepkg requires. tools/ci-local.sh runs the
# same thing in Docker on your own machine.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDER=builder
# Needed by the checks, not by the package itself.
CHECK_DEPS=(git python-pyqt6 kvantum spectacle ttf-dejavu)

json_escape() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  printf '%s' "${s//$'\n'/\\n}"
}

log() {  # level message [key=value ...]: one JSON record on stderr
  local level=$1 message=$2 fields="" kv
  shift 2
  for kv in "$@"; do
    fields+=$(printf ',"%s":"%s"' "${kv%%=*}" "$(json_escape "${kv#*=}")")
  done
  printf '{"timestamp":"%s","level":"%s","context":"ci","message":"%s"%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" "$level" "$(json_escape "$message")" "$fields" >&2
}

on_error() {
  local code=$? line=$1 command=$2
  log error "check failed" line="$line" command="$command" exit_code="$code" user="$(id -un)"
  exit "$code"
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

step() {  # name command...: run one check, logging when it starts and how long it took
  local name=$1 start=$SECONDS
  shift
  [[ -n ${GITHUB_ACTIONS:-} ]] && echo "::group::$name"
  log info "check started" check="$name"
  "$@"
  [[ -n ${GITHUB_ACTIONS:-} ]] && echo "::endgroup::"
  log info "check passed" check="$name" duration_s="$((SECONDS - start))"
}

install_deps() {
  local deps
  mapfile -t deps < <(bash -c 'source "$1" && printf "%s\n" "${depends[@]}" "${makedepends[@]}"' _ \
    "$ROOT/packaging/aur/PKGBUILD.in")
  if ((${#deps[@]} == 0)); then
    log error "no dependencies read from the PKGBUILD template"
    return 1
  fi
  log info "dependencies read from the PKGBUILD" packages="${deps[*]}" check_packages="${CHECK_DEPS[*]}"
  # Arch supports only full upgrades; installing onto a stale image would mix versions.
  pacman -Syu --noconfirm --needed --noprogressbar "${deps[@]}" "${CHECK_DEPS[@]}"
}

as_root() {
  step "install dependencies" install_deps
  if ! id -u "$BUILDER" &>/dev/null; then
    useradd --create-home "$BUILDER"
    log info "unprivileged user created" user="$BUILDER"
  fi
  chown -R "$BUILDER:" "$ROOT"
  exec runuser -u "$BUILDER" -- bash "$ROOT/tools/ci.sh" --unprivileged
}

release_args() {
  local url=${KH_REPO_URL:-}
  if [[ -z $url && -n ${GITHUB_REPOSITORY:-} ]]; then
    url="${GITHUB_SERVER_URL:-https://github.com}/$GITHUB_REPOSITORY"
  fi
  RELEASE_ARGS=(--test-build)
  [[ -n $url ]] && RELEASE_ARGS+=(--url "$url")
  if [[ ${GITHUB_REF_TYPE:-} == tag ]]; then
    local version
    version=$(python3 -c 'import khtheme; print(khtheme.VERSION)')
    if [[ $GITHUB_REF_NAME != "v$version" ]]; then
      log error "the tag does not match khtheme.VERSION" tag="$GITHUB_REF_NAME" version="$version"
      return 1
    fi
  else
    # Commits after a release still package; only tag builds must match the tag.
    RELEASE_ARGS+=(--no-tag-check)
  fi
}

as_builder() {
  cd "$ROOT"
  git config --global --add safe.directory '*'
  git config --global user.name >/dev/null || git config --global user.name "CI"
  git config --global user.email >/dev/null || git config --global user.email "ci@localhost"
  # A container has no login session; Qt and KWin need a private runtime folder.
  XDG_RUNTIME_DIR=$(mktemp -d)
  export XDG_RUNTIME_DIR
  chmod 700 "$XDG_RUNTIME_DIR"
  release_args

  step "byte-compile the Python" python3 -m compileall -q build.py install.py khtheme tools tests
  step "build both variants" ./build.py --clean
  step "unit and integration tests" python3 -m unittest discover -s tests -v
  step "offscreen renders" ./tools/preview.py
  step "decoration under a headless KWin" ./tools/nestedkwin.py
  step "AUR package" ./tools/release.py "${RELEASE_ARGS[@]}"
  log info "all checks passed" commit="$(git rev-parse --short HEAD)"
}

log info "ci started" root="$ROOT" user="$(id -un)"
if [[ ${1:-} == --unprivileged ]]; then
  as_builder
elif ((EUID == 0)); then
  as_root
else
  log error "run as root in a disposable container (CI or tools/ci-local.sh); it installs packages"
  exit 2
fi
