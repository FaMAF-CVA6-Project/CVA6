#!/usr/bin/env python3
"""Build the project's images and create their containers, sized to the host.

Both builds are heavy and both fail the same way when memory runs short: a
compiler is killed and the log says nothing useful. This reads what the Docker
daemon actually has and picks a job count that fits, rather than leaving it to
a default that suits the machine the recipe was written on.

    python3 scripts/make_containers.py                 # containers, both sides
    python3 scripts/make_containers.py gem5            # one side
    python3 scripts/make_containers.py --build         # build the images too
    python3 scripts/make_containers.py --check         # report and stop
    python3 scripts/make_containers.py -n              # print the commands

The images can also be pulled instead of built, which is what --pull does and
what most readers want. Building is for running a modified core.
"""
import argparse
import os
import shutil
import subprocess
import sys

# Memory a single compile job peaks at, per side. Linking gem5 is the worst
# case in the project and the number the job count is divided out of.
JOB_MEMORY_GB = {"cva6": 2.0, "gem5": 4.0}

# Free space each build needs, which is several times the finished image
# because the intermediate layers are not reclaimed until it ends.
BUILD_DISK_GB = {"cva6": 30, "gem5": 37}

# What a finished container needs on disk, well short of the build figure.
IMAGE_DISK_GB = {"cva6": 14, "gem5": 17}

SIDES = {
    "cva6": {
        "dockerfile": "dockerfiles/CVA6/Dockerfile",
        "local_tag": "manuel313/famaf_cva6:build",
        "published": "manuel313/famaf_cva6:latest",
        "container": "CVA6",
        "host_port": 8001,
    },
    "gem5": {
        "dockerfile": "dockerfiles/gem5/Dockerfile",
        "local_tag": "manuel313/famaf_gem5:build",
        "published": "manuel313/famaf_gem5:latest",
        "container": "gem5",
        "host_port": 8000,
    },
}

# Published so the viewer's server can reach the host's browser, and it cannot
# added later. The port inside is the same on both sides and the host one
# differs per side above, so both containers can serve at the same time.
VIEWER_PORT = 8000

# A Verilator build writes large temporaries here, and the 64 MB default is
# what makes it fail with an out-of-space error that names no file.
SHM_SIZE = "2g"

# What this project adds to a container. git in there reports every one as
# untracked, which buries the source change someone is actually looking for.
OVERLAY = ("scripts/", "gem5_configs/", "CVA6_configs/", "benchmarks/", "results/",
           "MinorFlow/", "CVA6Flow/", "MinorCPU_CVA6.patch",
           ".built_patch_sha1", "container_results/")

# Written once, and recognised on a second run so the list is not repeated.
EXCLUDE_MARKER = "# added by make_containers.py"


def repo_root():
    """The repository this script sits in, found by walking up to the nearest
    .git. Counting parents would be one more thing to fix if the tree moves."""
    path = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.dirname(os.path.abspath(__file__))
        path = parent


REPO = repo_root()


def run(cmd, dry_run, capture=False):
    """Echo a command and run it unless this is a dry run."""
    print("  $ " + " ".join(cmd))
    if dry_run:
        return 0, ""
    if capture:
        done = subprocess.run(cmd, capture_output=True, text=True)
        return done.returncode, done.stdout
    return subprocess.run(cmd).returncode, ""


def docker_resources():
    """(memory GB, CPUs, free disk GB) as the daemon sees them, or None.

    The daemon's figures, not the host's: on Docker Desktop the VM has its own
    caps and they are what a build actually gets."""
    done = subprocess.run(
        ["docker", "info", "--format",
         "{{.MemTotal}}|{{.NCPU}}|{{.DockerRootDir}}"],
        capture_output=True, text=True)
    if done.returncode != 0:
        return None
    try:
        mem_raw, cpu_raw, root = done.stdout.strip().split("|")
        mem_gb = int(mem_raw) / (1024 ** 3)
        cpus = int(cpu_raw)
    except ValueError:
        return None
    try:
        free_gb = shutil.disk_usage(root).free / (1024 ** 3)
    except OSError:
        # The daemon's storage directory is not readable from here, which is
        # normal on Docker Desktop. Fall back to this filesystem.
        free_gb = shutil.disk_usage(REPO).free / (1024 ** 3)
    return mem_gb, cpus, free_gb


def jobs_for(side, mem_gb, cpus):
    """How many compile jobs this machine can hold for one side.

    Memory is the binding constraint, not cores. One job is always returned,
    because refusing to build is worse than building slowly."""
    by_memory = int(mem_gb // JOB_MEMORY_GB[side])
    return max(1, min(cpus, by_memory))


def container_state(name):
    """'running', 'exited', a bare state, or None when there is no such
    container."""
    done = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$",
         "--format", "{{.State}}"], capture_output=True, text=True)
    if done.returncode != 0:
        return None
    state = done.stdout.strip()
    return state or None


def image_present(tag):
    done = subprocess.run(["docker", "image", "inspect", tag],
                          capture_output=True, text=True)
    return done.returncode == 0


def container_root(name):
    """The project root inside a container, read from the image's own working
    directory rather than assumed, so an image built before a rename still
    answers correctly."""
    done = subprocess.run(
        ["docker", "inspect", "-f", "{{.Config.WorkingDir}}", name],
        capture_output=True, text=True)
    root = done.stdout.strip() if done.returncode == 0 else ""
    return root or "/" + name


def tidy_git(name, dry_run):
    """Leave git inside the container reporting source changes only.

    The overlay goes in the container's own .gitignore. Files the image
    deleted are marked skip-worktree, which .gitignore cannot reach and which
    is all 759 entries on the CVA6 side."""
    root = container_root(name)
    script = (
        'cd "$1" 2>/dev/null || exit 0\n'
        '[ -d .git ] || exit 0\n'
        'shift\n'
        'if ! grep -qF "$MARKER" .gitignore 2>/dev/null; then\n'
        '  { echo ""; echo "$MARKER"; for p in "$@"; do echo "$p"; done; } '
        '>> .gitignore\n'
        'fi\n'
        'git ls-files --deleted -z | xargs -0 -r git update-index '
        '--skip-worktree 2>/dev/null\n'
        'git status --porcelain | wc -l\n')
    cmd = ["docker", "exec", "-e", f"MARKER={EXCLUDE_MARKER}", name,
           "sh", "-c", script, "sh", root] + list(OVERLAY)
    print(f"[INFO] Quieting git in '{name}' at {root}")
    if dry_run:
        print("  $ " + " ".join(cmd[:6]) + " ...")
        return 0
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        print(f"[WARN] Could not reach git in '{name}', left alone")
        return 0
    left = done.stdout.strip().splitlines()
    print(f"[INFO] git status in '{name}' now reports "
          f"{left[-1] if left else '?'} entry(ies)")
    return 0


def report(mem_gb, cpus, free_gb, sides, build):
    print(f"[INFO] Docker sees {mem_gb:.1f} GB of memory, {cpus} CPU(s), "
          f"{free_gb:.0f} GB free")
    ok = True
    for side in sides:
        n = jobs_for(side, mem_gb, cpus)
        need = BUILD_DISK_GB[side] if build else IMAGE_DISK_GB[side]
        what = "build" if build else "image"
        line = (f"[INFO] {side}: JOBS={n} "
                f"({JOB_MEMORY_GB[side]:.0f} GB per job), "
                f"{what} needs about {need} GB")
        print(line)
        if mem_gb < JOB_MEMORY_GB[side]:
            print(f"[WARN] {side}: under {JOB_MEMORY_GB[side]:.0f} GB, so "
                  f"even one job may be killed mid-compile. Raise the memory "
                  f"the daemon is allowed before building.")
            ok = False
        if free_gb < need:
            print(f"[WARN] {side}: {free_gb:.0f} GB free is under the "
                  f"{need} GB this needs. 'docker system prune' reclaims what "
                  f"earlier attempts left behind.")
            ok = False
    return ok


def build_image(side, jobs, dry_run, no_cache, extra_args=()):
    """Build one image from the repository root, which is where the recipe
    expects its context. extra_args is for a caller that needs more of the
    build than a plain build, such as seeding the cache when publishing."""
    cfg = SIDES[side]
    cmd = ["docker", "build",
           "--build-arg", f"JOBS={jobs}",
           "-f", cfg["dockerfile"],
           "-t", cfg["local_tag"]]
    if no_cache:
        cmd.append("--no-cache")
    cmd += list(extra_args)
    cmd.append(".")
    print(f"[INFO] Building {cfg['local_tag']} with JOBS={jobs}. "
          f"This takes hours.")
    code, _ = run(cmd, dry_run)
    return code


def pull_image(side, dry_run):
    cfg = SIDES[side]
    code, _ = run(["docker", "pull", cfg["published"]], dry_run)
    return code


def create_container(side, image, mem_gb, cpus, dry_run, force, x11):
    """Create one container with limits, or report why it was left alone."""
    cfg = SIDES[side]
    name = cfg["container"]
    state = container_state(name)
    if state and not force:
        print(f"[SKIP] A container named {name} already exists ({state}). "
              f"Its limits are fixed at creation, so --force removes and "
              f"remakes it. Anything inside it is lost.")
        return 0
    if state and force:
        code, _ = run(["docker", "rm", "-f", name], dry_run)
        if code != 0:
            return code

    # Left a core and a couple of gigabytes so the host stays usable while a
    # simulation runs, and so the OOM killer picks the container first.
    limit_cpus = max(1, cpus - 1)
    limit_mem = max(2, int(mem_gb) - 2)
    cmd = ["docker", "run", "-dit", "--name", name,
           "-p", f"{cfg['host_port']}:{VIEWER_PORT}",
           "--cpus", str(limit_cpus),
           "--memory", f"{limit_mem}g",
           "--shm-size", SHM_SIZE]
    if x11 and os.environ.get("DISPLAY"):
        cmd += ["-e", f"DISPLAY={os.environ['DISPLAY']}",
                "-v", "/tmp/.X11-unix:/tmp/.X11-unix"]
    cmd += [image, "bash"]
    print(f"[INFO] Creating {name}: {limit_cpus} CPU(s), {limit_mem} GB, "
          f"port {cfg['host_port']} published as {VIEWER_PORT} inside")
    code, _ = run(cmd, dry_run)
    return code


def main():
    parser = argparse.ArgumentParser(
        description="Build the project's images and create their containers, "
                    "sized to what Docker on this machine actually has.")
    parser.add_argument("side", nargs="?", choices=sorted(SIDES) + ["both"],
                        default="both",
                        help="Which side to prepare. Defaults to both")
    parser.add_argument("--build", action="store_true",
                        help="Build the image from this working tree first. "
                             "Needed only to run a modified core, and it "
                             "takes hours")
    parser.add_argument("--pull", action="store_true",
                        help="Pull the published image first, which is "
                             "what most readers want")
    parser.add_argument("--no-cache", action="store_true",
                        help="Build without Docker's layer cache")
    parser.add_argument("--jobs", type=int, default=None, metavar="N",
                        help="Override the computed build job count")
    parser.add_argument("--force", action="store_true",
                        help="Remove and remake a container that already "
                             "exists. Everything inside it is lost")
    parser.add_argument("--no-x11", action="store_true",
                        help="Do not pass the host's display through")
    parser.add_argument("--no-git-tidy", action="store_true",
                        help="Leave git inside the container reporting this "
                             "project's files. Without this they are added to "
                             "the container's .gitignore and the image's own "
                             "deletions are marked skip-worktree")
    parser.add_argument("--check", action="store_true",
                        help="Report what this machine can do and stop")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Print the commands without running them")
    args = parser.parse_args()

    if args.build and args.pull:
        print("[ERROR] --build and --pull both decide where the image comes "
              "from. Pick one.")
        return 2

    if not shutil.which("docker"):
        print("[ERROR] No docker on PATH.")
        return 2

    resources = docker_resources()
    if resources is None:
        print("[ERROR] Could not query the Docker daemon. Is it running, and "
              "is this user in the docker group?")
        return 2
    mem_gb, cpus, free_gb = resources

    sides = sorted(SIDES) if args.side == "both" else [args.side]
    fits = report(mem_gb, cpus, free_gb, sides, args.build)
    if args.check:
        return 0 if fits else 1
    if not fits and not args.dry_run:
        print("[ERROR] Refusing to start: the warnings above say this will "
              "fail partway through. Pass --check to see them alone, or -n to "
              "print the commands.")
        return 1

    os.chdir(REPO)
    for side in sides:
        cfg = SIDES[side]
        image = cfg["local_tag"] if args.build else cfg["published"]
        if args.build:
            jobs = args.jobs or jobs_for(side, mem_gb, cpus)
            if build_image(side, jobs, args.dry_run, args.no_cache) != 0:
                print(f"[ERROR] Build failed for {side}, stopping.")
                return 1
        elif args.pull:
            if pull_image(side, args.dry_run) != 0:
                print(f"[ERROR] Pull failed for {side}, stopping.")
                return 1
        elif not image_present(image) and not args.dry_run:
            # The image is only needed to make a container, so one that is
            # already there is no reason to stop. Re-running this to tidy git
            # in an existing container should not demand a pull.
            if container_state(cfg["container"]):
                print(f"[INFO] No image {image} here, but '"
                      f"{cfg['container']}' exists, so there is nothing to "
                      f"create.")
                if not args.no_git_tidy:
                    tidy_git(cfg["container"], args.dry_run)
                continue
            print(f"[ERROR] No image {image} here. Pass --pull to fetch it "
                  f"or --build to build it from this tree.")
            return 1
        if create_container(side, image, mem_gb, cpus, args.dry_run,
                            args.force, not args.no_x11) != 0:
            print(f"[ERROR] Could not create the {side} container.")
            return 1
        if not args.no_git_tidy:
            tidy_git(cfg["container"], args.dry_run)

    print("[INFO] Done. 'docker exec -it <name> bash' to get a shell, and "
          "'python3 scripts/docker_sync.py push' to send this checkout in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
