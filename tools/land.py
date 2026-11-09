#!/usr/bin/env python3
"""Land HEAD on main only if CI passes.

    tools/land.py

The default branch accepts only commits whose "build and test" check has
passed, so a plain `git push origin main` of an untested commit is refused.
This pushes HEAD to a temporary land/<commit> branch, waits for CI on it,
then pushes the same commit to main and deletes the temporary branch. HEAD
must be committed and contain origin/main (rebase first if not). Needs an
authenticated `gh`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log  # noqa: E402

MAIN = "main"
CHECK = "build and test"
FIND_RUN_S = 120  # how long GitHub may take to start the run
RUN_TIMEOUT_S = 3600


class LandError(RuntimeError):
    pass


def run(cmd: list[str], what: str, timeout: int = 120, quiet: bool = True) -> str:
    try:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=quiet, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        log.error("land", f"{what}: tool not found", error=exc, command=cmd[0])
        raise LandError(f"{cmd[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        log.error("land", f"{what}: timed out", error=exc, timeout_s=timeout)
        raise LandError(f"{what} timed out") from exc
    if result.returncode != 0:
        log.error("land", f"{what}: exited {result.returncode}", command=" ".join(cmd[:4]),
                  stderr=(result.stderr or "").strip()[-2000:])
        raise LandError(f"{what} failed")
    return result.stdout or ""


def check_head() -> str:
    if run(["git", "status", "--porcelain", "--untracked-files=no"], "check for uncommitted changes").strip():
        raise LandError("commit or stash your changes first; only committed work is tested and landed")
    commit = run(["git", "rev-parse", "HEAD"], "read HEAD").strip()
    run(["git", "fetch", "--quiet", "origin", MAIN], "fetch main")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", f"origin/{MAIN}", commit], cwd=ROOT)
    if ancestor.returncode != 0:
        raise LandError(f"HEAD does not contain origin/{MAIN}; rebase onto it first")
    return commit


def find_run(commit: str, branch: str) -> dict:
    deadline = time.monotonic() + FIND_RUN_S
    while time.monotonic() < deadline:
        out = run(["gh", "run", "list", "--commit", commit, "--branch", branch, "--workflow", "ci.yml",
                   "--json", "databaseId,url,status", "--limit", "1"], "look up the CI run")
        runs = json.loads(out or "[]")
        if runs:
            return runs[0]
        time.sleep(3)
    raise LandError(f"no CI run started for {commit[:12]} within {FIND_RUN_S}s")


def main() -> int:
    branch = None
    try:
        commit = check_head()
        branch = f"land/{commit[:12]}"
        log.info("land", "pushing to a temporary branch for CI", commit=commit[:12], branch=branch)
        run(["git", "push", "--quiet", "origin", f"{commit}:refs/heads/{branch}"], "push the temporary branch")
        ci = find_run(commit, branch)
        log.info("land", "waiting for CI", run=ci["url"])
        start = time.monotonic()
        watched = subprocess.run(["gh", "run", "watch", str(ci["databaseId"]), "--exit-status", "--interval", "15"],
                                 cwd=ROOT, timeout=RUN_TIMEOUT_S)
        duration = round(time.monotonic() - start)
        if watched.returncode != 0:
            log.error("land", "CI failed; main is unchanged", run=ci["url"], duration_s=duration)
            return 1
        log.info("land", "CI passed; landing on main", duration_s=duration)
        run(["git", "push", "--quiet", "origin", f"{commit}:refs/heads/{MAIN}"], "push to main")
        log.info("land", "landed", commit=commit[:12], branch=MAIN)
        return 0
    except LandError as exc:
        log.error("land", "not landed", error=exc)
        return 1
    except subprocess.TimeoutExpired as exc:
        log.error("land", "CI did not finish in time; main is unchanged", error=exc, timeout_s=RUN_TIMEOUT_S)
        return 1
    finally:
        if branch is not None:
            gone = subprocess.run(["git", "push", "--quiet", "origin", "--delete", branch], cwd=ROOT,
                                  capture_output=True, text=True)
            if gone.returncode != 0:
                log.warn("land", "could not delete the temporary branch", branch=branch, stderr=gone.stderr.strip())


if __name__ == "__main__":
    sys.exit(main())
