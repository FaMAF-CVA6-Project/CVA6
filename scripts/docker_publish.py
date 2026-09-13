#!/usr/bin/env python3
"""Rebuild the project's images and publish them to Docker Hub.

Which image a change affects is not decided here. The build decides it: a
cached rebuild reuses every layer above the edit, so an untouched image comes
out with the same ID and is not pushed. There is no list of paths to keep in
step with .dockerignore, which is the point.

    python3 scripts/docker_publish.py              # rebuild both, push changed
    python3 scripts/docker_publish.py gem5         # one side
    python3 scripts/docker_publish.py --check      # say what would be pushed
    python3 scripts/docker_publish.py -n           # print the commands
    python3 scripts/docker_publish.py --tag latest # override the tag policy

The tag follows the branch: master publishes latest, anything else publishes
testing. Both also get sha-<short>, so a moving tag stays traceable to a
commit. make_containers.py --build is for the first, cold build, which takes
hours. This is for every rebuild after it.
"""
import argparse
import importlib.util
import os
import subprocess
import sys


def repo_root():
    """The repository this script sits in, found by walking up to the nearest
    .git. The script lives in scripts/, so counting parents would be one more
    thing to fix the next time the tree moves."""
    path = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.dirname(os.path.abspath(__file__))
        path = parent


REPO = repo_root()

# The branch that publishes the tag readers pull. Everything else is testing.
RELEASE_BRANCH = "master"
RELEASE_TAG = "latest"
TESTING_TAG = "testing"


def load_module(rel, name):
    """Import a sibling script for its tables, without running it."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(REPO, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The image recipes, the local tags and the published names all live there
# already, so this reads them rather than keeping a second copy.
MAKER = load_module("scripts/make_containers.py", "make_containers")
SIDES = MAKER.SIDES


def docker(args, **kwargs):
    return subprocess.run(["docker"] + args, **kwargs)


def git_out(args):
    """A git value, or None when git cannot answer."""
    done = subprocess.run(["git", "-C", REPO] + args,
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def image_id(tag):
    """The image a tag points at, or None when there is no such tag here."""
    done = docker(["image", "inspect", "-f", "{{.Id}}", tag],
                  capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def registry_name(side):
    """The Docker Hub repository, taken from the published name so the
    registry is named in one place only."""
    return SIDES[side]["published"].rsplit(":", 1)[0]


def logged_in():
    """The Docker Hub user, or None. A push fails late without one, after the
    build has already spent its time."""
    done = docker(["system", "info", "--format", "{{.Username}}"],
                  capture_output=True, text=True)
    user = done.stdout.strip() if done.returncode == 0 else ""
    return user or None


def tag_policy(override):
    """(moving tag, reason). The branch decides unless --tag says otherwise."""
    if override:
        return override, "asked for with --tag"
    branch = git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch == RELEASE_BRANCH:
        return RELEASE_TAG, f"on {RELEASE_BRANCH}"
    return TESTING_TAG, f"on {branch or 'an unknown branch'}"


def tags_for(side, moving):
    """Every tag this publish writes. The sha tag is what makes a moving tag
    traceable to a commit after it has moved on."""
    repository = registry_name(side)
    names = [f"{repository}:{moving}"]
    sha = git_out(["rev-parse", "--short", "HEAD"])
    if sha:
        names.append(f"{repository}:sha-{sha}")
    return names


def cache_args(side):
    """The build arguments that make a rebuild incremental.

    BUILDKIT_INLINE_CACHE writes cache metadata into the image being pushed,
    which is what lets a later pull seed a build. --cache-from offers the
    published image as that seed when it is here."""
    args = ["--build-arg", "BUILDKIT_INLINE_CACHE=1"]
    published = SIDES[side]["published"]
    if image_id(published) is not None:
        args += ["--cache-from", published]
    if image_id(SIDES[side]["local_tag"]) is not None:
        args += ["--cache-from", SIDES[side]["local_tag"]]
    return args


def rebuild(side, jobs, dry_run):
    """Rebuild one image. Returns (exit code, changed), where changed says
    whether the build produced a different image than the one already here."""
    local = SIDES[side]["local_tag"]
    before = image_id(local)
    code = MAKER.build_image(side, jobs, dry_run, False, cache_args(side))
    if code != 0:
        return code, False
    if dry_run:
        return 0, True
    return 0, before != image_id(local)


def normalised(reference):
    """A reference with its tag spelled out, so manuel313/famaf_cva6 and
    manuel313/famaf_cva6:latest compare equal. A colon in the last path element
    is the tag, anything earlier is a registry port."""
    return (reference if ":" in reference.rsplit("/", 1)[-1]
            else reference + ":latest")


def needs_push(side, moving, changed):
    """Whether the moving tag has to move. A rebuild that changed nothing
    still publishes when the tag does not already point at this image."""
    if changed:
        return True
    local = SIDES[side]["local_tag"]
    target = f"{registry_name(side)}:{moving}"
    # Unifying the namespaces makes these one reference, and the test below
    # would then compare a tag with itself and skip for ever. A local tag
    # says nothing about the registry anyway, so push.
    if normalised(local) == normalised(target):
        return True
    here = image_id(local)
    return here is None or here != image_id(target)


def confirm(question):
    """Publishing is outward-facing, so it is never done unasked."""
    if not sys.stdin.isatty():
        print("[INFO] Not a terminal, so nothing is pushed. Pass -y.")
        return False
    try:
        return input(f"  {question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def publish(side, names, dry_run):
    """Tag the built image under every published name and push each."""
    local = SIDES[side]["local_tag"]
    for name in names:
        print(f"  $ docker tag {local} {name}")
        if not dry_run and docker(["tag", local, name]).returncode != 0:
            print(f"[ERROR] Could not tag {name}")
            return 1
        print(f"  $ docker push {name}")
        if not dry_run and docker(["push", name]).returncode != 0:
            print(f"[ERROR] Could not push {name}")
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Rebuild the project's images and publish them.",
        epilog="The build decides what changed: a cached rebuild reuses\n"
               "every layer above the edit, so an untouched image keeps its\n"
               "ID and is not pushed.\n"
               "\n"
               f"{RELEASE_BRANCH} publishes {RELEASE_TAG}, every other "
               f"branch publishes\n{TESTING_TAG}. Both also get sha-<short>.")
    parser.add_argument("side", nargs="?", choices=sorted(SIDES) + ["both"],
                        default="both",
                        help="which side to publish. Defaults to both")
    parser.add_argument("--tag", metavar="NAME",
                        help="publish under this moving tag instead of the "
                             "one the branch implies")
    parser.add_argument("--jobs", type=int, default=None, metavar="N",
                        help="override the computed build job count")
    parser.add_argument("--force", action="store_true",
                        help="publish even when the rebuild changed nothing, "
                             "and from a branch that is not "
                             f"{RELEASE_BRANCH}")
    parser.add_argument("--check", action="store_true",
                        help="say what would be rebuilt and pushed, and stop")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="do not ask before pushing")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="print the commands without running them")
    args = parser.parse_args()

    moving, why = tag_policy(args.tag)
    sides = sorted(SIDES) if args.side == "both" else [args.side]

    # Only --tag can ask for the release tag off the release branch, since
    # the policy would have chosen testing. It is the tag readers pull, so
    # asking for it there has to be deliberate.
    branch = git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    if moving == RELEASE_TAG and branch != RELEASE_BRANCH and not args.force:
        print(f"[ERROR] {RELEASE_TAG} is the tag readers pull, and this is "
              f"{branch}, not {RELEASE_BRANCH}. Add --force to mean it.")
        return 2

    print(f"[INFO] Publishing to {moving} ({why})")
    dirty = git_out(["status", "--porcelain"])
    if dirty:
        print(f"[WARN] {len(dirty.splitlines())} uncommitted change(s). The "
              f"image will carry them and sha-<short> will not name them.")

    if args.check:
        for side in sides:
            print(f"[INFO] {side}: would rebuild "
                  f"{SIDES[side]['local_tag']}, then push "
                  + ", ".join(tags_for(side, moving)))
        return 0

    resources = MAKER.docker_resources()
    if resources is None:
        print("[ERROR] Could not query the Docker daemon. Is it running, and "
              "is this user in the docker group?")
        return 2
    mem_gb, cpus, _ = resources

    # With neither the local build nor the published image here there is
    # nothing to build on, so this would be the cold build, not a rebuild.
    for side in sides:
        local = SIDES[side]["local_tag"]
        published = SIDES[side]["published"]
        if MAKER.image_present(local):
            continue
        if not MAKER.image_present(published):
            print(f"[ERROR] Neither {local} nor {published} is here, so this "
                  f"would be the first build and it takes hours. Run "
                  f"'python3 scripts/make_containers.py {side} --build' "
                  f"once, or --pull to fetch the image.")
            return 1
        print(f"[WARN] {side}: no {local} yet, so the cache comes from "
              f"{published}. That only helps if it was pushed with inline "
              f"cache, so this rebuild may run in full.")

    if not args.dry_run and logged_in() is None:
        print("[ERROR] Not logged in to Docker Hub. Run 'docker login'.")
        return 2

    os.chdir(REPO)
    pushed, skipped = [], []
    for side in sides:
        print(f"\n=== {side} ===")
        jobs = args.jobs or MAKER.jobs_for(side, mem_gb, cpus)
        code, changed = rebuild(side, jobs, args.dry_run)
        if code != 0:
            print(f"[ERROR] Rebuild failed for {side}, stopping.")
            return 1
        if not (args.force or needs_push(side, moving, changed)):
            print(f"[SKIP] {side}: the rebuild changed nothing and "
                  f"{moving} already points at it.")
            skipped.append(side)
            continue
        names = tags_for(side, moving)
        print(f"[INFO] {side}: " + ("changed" if changed else "unchanged")
              + ", publishing " + ", ".join(names))
        if not (args.yes or args.dry_run
                or confirm(f"Push {side} to {', '.join(names)}?")):
            print(f"[SKIP] {side}: not pushed.")
            skipped.append(side)
            continue
        if publish(side, names, args.dry_run) != 0:
            return 1
        pushed.append(side)

    print(f"\n[INFO] Pushed: {', '.join(pushed) or 'nothing'}. "
          f"Left alone: {', '.join(skipped) or 'nothing'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
