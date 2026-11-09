#!/usr/bin/env python3
"""Make a release: the source bundle, and the AUR package files that build it.

    tools/release.py                    needs a clean tree and a GitHub 'origin' remote
    tools/release.py --url https://github.com/OWNER/REPO
    tools/release.py --test-build       also build the package locally with makepkg

Writes into dist/release/:

    kingdom-hearts-plasma-VERSION.tar.gz         the source bundle (git archive of HEAD)
    kingdom-hearts-plasma-VERSION.tar.gz.sha256
    aur/PKGBUILD, aur/.SRCINFO, aur/kingdom-hearts-plasma.install

then prints how a release is published: by CI, from the version's tag.
Nothing is uploaded or pushed here. The version is khtheme.VERSION; the
PKGBUILD downloads the bundle from the GitHub release tagged vVERSION.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import VERSION, log  # noqa: E402

NAME = "kingdom-hearts-plasma"
OUT = ROOT / "dist" / "release"
AUR_TEMPLATE = ROOT / "packaging" / "aur"
GITHUB = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


class ReleaseError(RuntimeError):
    pass


def run(cmd: list[str], what: str, cwd: Path = ROOT, timeout: int = 120) -> str:
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        log.error("release", f"{what}: tool not found", error=exc, command=cmd[0])
        raise ReleaseError(f"{what}: {cmd[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        log.error("release", f"{what}: timed out", error=exc, command=cmd[0], timeout_s=timeout)
        raise ReleaseError(f"{what}: timed out after {timeout}s") from exc
    duration = round((time.monotonic() - start) * 1000, 1)
    if result.returncode != 0:
        log.error("release", f"{what}: exited {result.returncode}", command=" ".join(cmd[:3]), duration_ms=duration,
                  stderr=result.stderr.strip()[-3000:], stdout=result.stdout.strip()[-2000:])
        raise ReleaseError(f"{what} failed")
    log.debug("release", f"{what}: ok", duration_ms=duration)
    return result.stdout


def project_url(override: str | None) -> str:
    """The GitHub page the package's url and source point at."""
    remote = override
    if remote is None:
        try:
            remote = run(["git", "remote", "get-url", "origin"], "read the origin remote").strip()
        except ReleaseError as exc:
            raise ReleaseError("no 'origin' remote; add the GitHub repository or pass --url") from exc
    match = GITHUB.search(remote)
    if not match:
        log.error("release", "the project is not on GitHub; the PKGBUILD downloads from GitHub releases", remote=remote)
        raise ReleaseError(f"not a GitHub repository: {remote}")
    return f"https://github.com/{match['owner']}/{match['repo']}"


def maintainer() -> str:
    name = run(["git", "config", "user.name"], "read git user.name").strip()
    email = run(["git", "config", "user.email"], "read git user.email").strip()
    if not name or not email:
        raise ReleaseError("set git user.name and user.email; the PKGBUILD names its maintainer")
    return f"{name} <{email}>"


def check_tree(tag_check: bool = True) -> str:
    """HEAD's commit, refusing uncommitted changes: the bundle is HEAD, and
    unbundled edits would make it differ from what was tested. Unless told
    otherwise, also refuses a version whose tag already names another commit."""
    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"], "check for uncommitted changes").strip()
    if dirty:
        log.error("release", "uncommitted changes; commit them first", changes=dirty.splitlines()[:20])
        raise ReleaseError("the working tree has uncommitted changes")
    commit = run(["git", "rev-parse", "HEAD"], "read HEAD").strip()
    if not tag_check:
        return commit
    tag = f"v{VERSION}"
    tagged = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    if tagged and tagged != commit:
        log.error("release", "the version's tag points at another commit; raise khtheme.VERSION", tag=tag,
                  tagged=tagged, head=commit)
        raise ReleaseError(f"{tag} already names {tagged[:12]}, not HEAD")
    return commit


def make_bundle(commit: str) -> tuple[Path, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    bundle = OUT / f"{NAME}-{VERSION}.tar.gz"
    run(["git", "archive", "--format=tar.gz", f"--prefix={NAME}-{VERSION}/", "-o", str(bundle), commit],
        "write the source bundle")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (OUT / f"{bundle.name}.sha256").write_text(f"{digest}  {bundle.name}\n", encoding="utf-8")
    log.info("release", "source bundle written", bundle=str(bundle), sha256=digest,
             size_mb=round(bundle.stat().st_size / 1e6, 1), commit=commit[:12])
    return bundle, digest


def render_aur(url: str, digest: str, pkgrel: int) -> Path:
    aur = OUT / "aur"
    if aur.exists():
        shutil.rmtree(aur)
    aur.mkdir(parents=True)
    values = {"@MAINTAINER@": maintainer(), "@PKGVER@": VERSION, "@PKGREL@": str(pkgrel), "@URL@": url,
              "@SHA256@": digest}
    text = (AUR_TEMPLATE / "PKGBUILD.in").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(key, value)
    left = sorted(set(re.findall(r"@[A-Z0-9_]+@", text)))
    if left:
        log.error("release", "PKGBUILD template has unfilled placeholders", placeholders=left)
        raise ReleaseError(f"unfilled placeholders: {left}")
    (aur / "PKGBUILD").write_text(text, encoding="utf-8")
    shutil.copy2(AUR_TEMPLATE / f"{NAME}.install", aur / f"{NAME}.install")
    srcinfo = run(["makepkg", "--printsrcinfo"], "generate .SRCINFO", cwd=aur)
    (aur / ".SRCINFO").write_text(srcinfo, encoding="utf-8")
    log.info("release", "AUR package files written", folder=str(aur), pkgver=VERSION, pkgrel=pkgrel)
    return aur


def test_build(aur: Path, bundle: Path) -> None:
    """Build the package the way an AUR helper would, from the local bundle
    (makepkg uses a source file it finds next to the PKGBUILD instead of
    downloading it). Nothing is installed."""
    work = OUT / "test-build"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(aur, work)
    shutil.copy2(bundle, work / bundle.name)
    log.info("release", "test build started; this compiles and renders everything", folder=str(work))
    start = time.monotonic()
    run(["makepkg", "--force", "--cleanbuild", "--noconfirm", "--noprogressbar"], "build the package",
        cwd=work, timeout=3600)
    packages = sorted(p.name for p in work.glob(f"{NAME}-*.pkg.tar.*") if not p.name.endswith(".sig"))
    if not packages:
        log.error("release", "makepkg finished but wrote no package", folder=str(work))
        raise ReleaseError("no package was built")
    log.info("release", "test build finished", packages=packages, duration_s=round(time.monotonic() - start))


def next_steps(commit: str) -> str:
    tag = f"v{VERSION}"
    clone = f"../aur-{NAME}"
    return f"""# CI publishes from the tag, with a bundle and AUR files it builds and tests itself.
# 1. Land the release commit (CI must pass first), then tag it:
./tools/land.py
git tag -a {tag} -m "{NAME} {VERSION}" {commit[:12]}
git push origin {tag}

# 2. CI tests the tag, publishes the GitHub release (bundle, checksum and
#    aur-files.tar.gz) and, when the AUR_SSH_PRIVATE_KEY secret is set, pushes
#    the AUR package. Without that secret, push the release's AUR files by hand
#    (first time: git clone ssh://aur@aur.archlinux.org/{NAME}.git {clone}):
gh release download {tag} -p aur-files.tar.gz -O - | tar -xz -C {clone}
git -C {clone} add PKGBUILD .SRCINFO {NAME}.install
git -C {clone} commit -m "Update to {VERSION}"
git -C {clone} push
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="GitHub repository URL, when 'origin' is not set or not the one to publish to")
    parser.add_argument("--pkgrel", type=int, default=1, help="package release; raise it for packaging-only fixes")
    parser.add_argument("--test-build", action="store_true", help="also build the package locally with makepkg")
    parser.add_argument("--no-tag-check", action="store_true",
                        help="package HEAD even when the version's tag names an earlier commit (CI on later commits)")
    args = parser.parse_args()

    log.info("release", "release started", version=VERSION)
    try:
        url = project_url(args.url)
        commit = check_tree(tag_check=not args.no_tag_check)
        bundle, digest = make_bundle(commit)
        aur = render_aur(url, digest, args.pkgrel)
        if args.test_build:
            test_build(aur, bundle)
    except ReleaseError as exc:
        log.error("release", "release aborted", error=exc, version=VERSION)
        return 1
    except Exception as exc:
        log.error("release", "unexpected failure", error=exc, version=VERSION)
        return 1
    print(next_steps(commit))
    log.info("release", "release files ready", version=VERSION, url=url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
