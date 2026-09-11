#!/usr/bin/env python3
"""Fetch the pristine gem5 sources the RISC-V MinorCPU model is built from.

The version is read from the gem5 image's own recipe, so this fetches exactly
what the image builds and nothing newer. The tree is mirrored rather than
flattened, unlike get_CVA6_files.py, because that is what lets
MinorCPU_CVA6.patch apply to the copy as it is.

  python3 scripts/get_gem5_files.py                # fetch into gem5_files/
  python3 scripts/get_gem5_files.py -o pristine    # a different destination
  python3 scripts/get_gem5_files.py --dry-run      # list what would be fetched
  python3 scripts/get_gem5_files.py --check-patch  # then dry-run the patch
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile


def repo_root():
    """The repository this script sits in, found by walking up to the nearest
    .git. The script lives in scripts/, so counting parents would be one more
    thing to fix the next time the tree moves."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = here
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return here
        path = parent


REPO_ROOT = repo_root()

DEFAULT_DEST = "gem5_files"
GEM5_REPO = "https://github.com/gem5/gem5.git"

# The recipe the version is read from, and the patch whose files are fetched.
DOCKERFILE = os.path.join("dockerfiles", "gem5", "Dockerfile")
PATCH = os.path.join("gem5_config_CVA6", "gem5", "configs",
                     "MinorCPU_CVA6.patch")

# The MinorCPU model and the branch predictors every configuration sets up,
# taken whole because the configurations reach into most of both.
WHOLE_DIRS = ("src/cpu/minor", "src/cpu/pred")

# What makes a MinorCPU a RiscvMinorCPU.
EXTRA_FILES = ("src/arch/riscv/RiscvCPU.py",)

# Written into the destination, naming what it holds. Its presence is also
# what marks a folder as one this script may replace.
VERSION_FILE = "GEM5_VERSION"

# The container whose build the fetched commit is compared with, if running.
CONTAINER = "gem5"


def gem5_tag():
    """The tag the gem5 image clones, or None when the recipe does not say."""
    path = os.path.join(REPO_ROOT, DOCKERFILE)
    if not os.path.isfile(path):
        return None
    found = re.search(r"^ARG GEM5_TAG=(\S+)", open(path).read(), re.M)
    return found.group(1) if found else None


def patched_files():
    """Every file the patch modifies that already exists in gem5. The files it
    creates are left out, since pristine gem5 has no copy of them."""
    path = os.path.join(REPO_ROOT, PATCH)
    if not os.path.isfile(path):
        return []
    return sorted({line[len("--- a/"):].strip()
                   for line in open(path, encoding="utf-8")
                   if line.startswith("--- a/")})


def manifest():
    """The paths to fetch, a whole directory once rather than its files."""
    paths = list(WHOLE_DIRS) + list(EXTRA_FILES)
    for rel in patched_files():
        if not any(rel.startswith(d + "/") for d in WHOLE_DIRS):
            paths.append(rel)
    return sorted(set(paths))


def git(args, **kwargs):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          **kwargs)


def fetch(tag, paths, work):
    """(commit, error). A partial clone with no blobs, then a checkout of only
    these paths, so the whole of gem5 is never downloaded."""
    done = git(["clone", "--quiet", "--depth", "1", "--filter=blob:none",
                "--no-checkout", "--branch", tag, GEM5_REPO, work])
    if done.returncode != 0:
        return None, f"clone failed: {done.stderr.strip()[:200]}"
    done = git(["-C", work, "checkout", "HEAD", "--"] + paths)
    if done.returncode != 0:
        return None, f"checkout failed: {done.stderr.strip()[:200]}"
    commit = git(["-C", work, "rev-parse", "HEAD"]).stdout.strip()
    return commit, None


def container_commit():
    """The commit the gem5 container was built from, or None when there is no
    running container to ask."""
    if not shutil.which("docker"):
        return None
    done = subprocess.run(["docker", "exec", CONTAINER, "git", "-C", "/gem5",
                           "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def check_patch(dest):
    """Dry-run the patch on the fetched copy. True when every hunk applies."""
    if not shutil.which("patch"):
        print("[WARN] No patch on PATH, so the patch was not checked")
        return True
    done = subprocess.run(["patch", "-p1", "--dry-run", "-d", dest, "-i",
                           os.path.join(REPO_ROOT, PATCH)],
                          capture_output=True, text=True)
    trouble = [line for line in done.stdout.splitlines()
               if re.search(r"FAILED|fuzz|offset|Reversed", line)]
    if done.returncode == 0 and not trouble:
        print("[INFO] MinorCPU_CVA6.patch applies cleanly to this copy")
        return True
    print("[ERROR] MinorCPU_CVA6.patch does not apply cleanly:")
    for line in (trouble or done.stdout.splitlines())[:12]:
        print(f"         {line}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch the pristine gem5 sources of the RISC-V MinorCPU "
                    "at the version the gem5 image builds.")
    parser.add_argument("-o", "--dest", default=DEFAULT_DEST, metavar="DIR",
                        help=f"Destination directory (default "
                             f"{DEFAULT_DEST}/)")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="List what would be fetched and stop")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Name every file as it is copied")
    parser.add_argument("--tag", default=None, metavar="TAG",
                        help="Fetch this tag instead of the one the image "
                             "builds, which is then no longer the same "
                             "version")
    parser.add_argument("--check-patch", action="store_true",
                        help="After fetching, dry-run MinorCPU_CVA6.patch on "
                             "the copy")
    args = parser.parse_args()

    tag = args.tag or gem5_tag()
    if tag is None:
        print(f"[ERROR] No ARG GEM5_TAG in {DOCKERFILE}, so there is no "
              f"version to match. Pass --tag.")
        return 2
    if args.tag and args.tag != gem5_tag():
        print(f"[WARN] {args.tag} is not {gem5_tag()}, the version the gem5 "
              f"image builds")
    paths = manifest()
    dest = os.path.abspath(args.dest)
    print(f"[INFO] gem5 {tag}, from {GEM5_REPO}")
    print(f"[INFO] Destination: {dest}")
    print(f"[INFO] {len(paths)} path(s): {', '.join(WHOLE_DIRS)} whole, "
          f"{len(paths) - len(WHOLE_DIRS)} file(s) the model and the patch "
          f"touch")
    if args.dry_run:
        for rel in paths:
            print(f"       {rel}")
        print("[INFO] Dry run, nothing fetched")
        return 0

    # Replaced whole, so a file from an older version cannot linger, but only
    # when this script made it. Any other folder there is someone's work.
    if os.path.isdir(dest) and os.listdir(dest):
        if not os.path.isfile(os.path.join(dest, VERSION_FILE)):
            print(f"[ERROR] {dest} exists and was not made by this script, "
                  f"so it is left alone. Pick another -o.")
            return 1
        shutil.rmtree(dest)

    work = tempfile.mkdtemp(prefix="gem5_files_")
    try:
        print("[INFO] Fetching, which takes about a minute")
        commit, error = fetch(tag, paths, os.path.join(work, "gem5"))
        if error:
            print(f"[ERROR] {error}")
            return 1
        copied = 0
        for rel in paths:
            source = os.path.join(work, "gem5", rel)
            target = os.path.join(dest, rel)
            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
                count = sum(len(files) for _, _, files in os.walk(source))
            elif os.path.isfile(source):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
                count = 1
            else:
                print(f"[WARN] {rel} is not in gem5 {tag}")
                continue
            copied += count
            if args.verbose:
                print(f"       {rel} ({count})")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    today = datetime.date.today().isoformat()
    with open(os.path.join(dest, VERSION_FILE), "w") as handle:
        handle.write(f"gem5 {tag}\ncommit {commit}\nfrom {GEM5_REPO}\n"
                     f"fetched {today} by scripts/get_gem5_files.py\n")
    print(f"[INFO] Copied {copied} file(s), gem5 {tag} at {commit[:12]}")

    built = container_commit()
    if built is None:
        print(f"[INFO] No running '{CONTAINER}' container to compare with")
    elif built == commit:
        print(f"[INFO] Same commit the '{CONTAINER}' container was built from")
    else:
        print(f"[WARN] The '{CONTAINER}' container was built from "
              f"{built[:12]}, not {commit[:12]}")

    if args.check_patch and not check_patch(dest):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
