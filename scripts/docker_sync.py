#!/usr/bin/env python3
"""Move files between this checkout and the project's containers.

Four things to do, one word each. The container is cva6, gem5, or left out
for both.

    python3 scripts/docker_sync.py push          # send this checkout in
    python3 scripts/docker_sync.py pull          # bring the results back
    python3 scripts/docker_sync.py trace         # pull, then make the JSONs
    python3 scripts/docker_sync.py list          # show what is in there

    python3 scripts/docker_sync.py push gem5     # one container
    python3 scripts/docker_sync.py trace -y      # take every folder, no asking
    python3 scripts/docker_sync.py push -n       # say what would be copied

A container keeps its own copy of everything, so a script edited here changes
nothing inside until it is pushed. That is what push is for, and it is the
step whose absence makes a container quietly run last week's driver.
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
    here = os.path.dirname(os.path.abspath(__file__))
    path = here
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return here
        path = parent


REPO = repo_root()

# Where a pulled folder lands, unless --out-dir says otherwise.
DEFAULT_OUT_DIR = "container_results"

# The cleaners list every folder a run leaves behind, which is not the same as
# every folder worth carrying home. A build tree is remade by the next run and
# runs to gigabytes, so it never reaches the menu.
NEVER_PULL = {"work-ver", "work-dpi", "build", "__pycache__"}

# Echoed by the probe when the container root is absent, which reads very
# differently from a root that is simply empty.
NOROOT = "__no_such_root__"

# What each container holds. The push lists are the two folders the images are
# meant to look like: the tools in scripts/, both benchmark sets under
# benchmarks/, and the viewer in a folder of its own at the root.
CONTAINERS = {
    "gem5": {
        "root": "/gem5",
        "cleaner": "viewers/MinorFlow/scripts/clean_gem5_runs.py",
        "tracer": "viewers/MinorFlow/scripts/create_all_MinorFlow_jsons.py",
        "push": [
            # Drivers and sweeps, in the place they have here, run with the
            # root as the working directory since that is where build/ is.
            ("viewers/MinorFlow/scripts/run_gem5.py", "/gem5/scripts/"),
            ("viewers/MinorFlow/scripts/run_all_gem5_benchmarks.py",
             "/gem5/scripts/"),
            ("viewers/MinorFlow/scripts/clean_gem5_runs.py", "/gem5/scripts/"),
            ("viewers/MinorFlow/scripts/run_MinorFlow_sweep.py",
             "/gem5/scripts/"),
            ("scripts/run_config_search_sweep.py", "/gem5/scripts/"),
            ("scripts/check_patch_parity.py", "/gem5/scripts/"),
            ("scripts/patch_gem5.py", "/gem5/scripts/"),
            ("scripts/serve_viewers.py", "/gem5/scripts/"),
            # Configurations under gem5_configs/, a name gem5's own tree
            # does not use, one folder per origin, plus the patch.
            ("gem5_config_CVA6/gem5/configs/.", "/gem5/gem5_configs/config/"),
            ("viewers/MinorFlow/configs/gem5_config_MinorFlow.py",
             "/gem5/gem5_configs/viewer/"),
            ("viewers/MinorFlow/configs/gem5_config_Reference_Core.py",
             "/gem5/gem5_configs/viewer/"),
            # The published paper's own Reference Core, kept apart so the
            # frozen one is never confused with the live one beside it.
            ("viewers/MinorFlow/docs/CARLA2026/gem5_config_Reference_Core.py",
             "/gem5/gem5_configs/CARLA2026/"),
            # The viewer, at the root rather than under a viewers/ level.
            ("viewers/MinorFlow/MinorFlow.html", "/gem5/MinorFlow/"),
            ("viewers/MinorFlow/MinorFlow_tracer.py", "/gem5/MinorFlow/"),
            ("viewers/MinorFlow/index.html", "/gem5/MinorFlow/"),
            ("viewers/MinorFlow/scripts/create_all_MinorFlow_jsons.py",
             "/gem5/scripts/"),
        ],
        # Folders copied whole, source -> destination.
        "push_dirs": [
            ("gem5_config_CVA6/gem5/benchmarks", "/gem5/benchmarks/config"),
            ("viewers/MinorFlow/benchmarks", "/gem5/benchmarks/viewer"),
        ],
    },
    "CVA6": {
        "root": "/CVA6",
        "cleaner": "viewers/CVA6Flow/scripts/clean_CVA6_runs.py",
        "tracer": "viewers/CVA6Flow/scripts/create_all_CVA6Flow_jsons.py",
        "push": [
            ("viewers/CVA6Flow/scripts/run_CVA6.py", "/CVA6/scripts/"),
            ("viewers/CVA6Flow/scripts/run_all_CVA6_benchmarks.py",
             "/CVA6/scripts/"),
            ("viewers/CVA6Flow/scripts/clean_CVA6_runs.py", "/CVA6/scripts/"),
            ("viewers/CVA6Flow/scripts/run_CVA6Flow_sweep.py",
             "/CVA6/scripts/"),
            ("scripts/serve_viewers.py", "/CVA6/scripts/"),
            # Straight to where the build reads it. This is the CVA6Flow
            # package, the one carrying the configuration table and
            # CVA6_CONFIG_SEL, and it replaces the live one.
            ("viewers/CVA6Flow/configs/"
             "cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv",
             "/CVA6/core/include/"),
            ("viewers/CVA6Flow/configs/"
             "cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv",
             "/CVA6/CVA6_configs/"),
            # The viewer, and the server that puts it in the host's browser.
            ("viewers/CVA6Flow/CVA6Flow.html", "/CVA6/CVA6Flow/"),
            ("viewers/CVA6Flow/CVA6Flow_tracer.py", "/CVA6/CVA6Flow/"),
            ("viewers/CVA6Flow/index.html", "/CVA6/CVA6Flow/"),
            ("viewers/CVA6Flow/scripts/create_all_CVA6Flow_jsons.py",
             "/CVA6/scripts/"),
        ],
        "push_dirs": [
            ("gem5_config_CVA6/CVA6/benchmarks", "/CVA6/benchmarks/config"),
            ("viewers/CVA6Flow/benchmarks", "/CVA6/benchmarks/viewer"),
        ],
    },
}


def load_cleaner(rel):
    """Import a cleaner for its folder tables, without running it."""
    spec = importlib.util.spec_from_file_location(
        "cleaner", os.path.join(REPO, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidates(name):
    """[(path relative to the container root, why it exists)], from the
    cleaner that already knows this flow's output folders."""
    spec = CONTAINERS[name]
    try:
        cleaner = load_cleaner(spec["cleaner"])
    except (OSError, ImportError) as e:
        print(f"[WARN] Could not read {spec['cleaner']}: {e}")
        return []
    out = [(d, why) for d, why in cleaner.ROOT_DIRS.items()
           if d not in NEVER_PULL]
    out += [(d, why) for d, why in cleaner.SIBLING_DIRS.items()
            if d not in NEVER_PULL]
    if getattr(cleaner, "OUT_GLOB", None):
        out.append((cleaner.OUT_GLOB, cleaner.OUT_REASON))
    return out


def docker(args, **kwargs):
    return subprocess.run(["docker"] + args, **kwargs)


def container_exists(name):
    r = docker(["ps", "-a", "--format", "{{.Names}}"],
               capture_output=True, text=True)
    return name in r.stdout.split() if r.returncode == 0 else None


def running(name):
    r = docker(["inspect", "-f", "{{.State.Running}}", name],
               capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def ensure_running(name, assume_yes):
    """A stopped container cannot be looked into. Offer to start it."""
    if running(name):
        return True
    print(f"[INFO] '{name}' is not running.")
    if not assume_yes:
        # Starting a container changes the machine, so it is never done on its
        # own. Without a terminal to ask, say so and leave it alone.
        if not sys.stdin.isatty():
            print(f"[INFO] Skipping '{name}'. Start it, or pass -y.")
            return False
        try:
            if input("  Start it? [Y/n] ").strip().lower() in ("n", "no"):
                return False
        except (EOFError, KeyboardInterrupt):
            print()
            return False
    if docker(["start", name], capture_output=True).returncode != 0:
        print(f"[ERROR] Could not start '{name}'")
        return False
    print(f"[INFO] Started '{name}'")
    return True


def present(name):
    """[(path, size)] for the candidate folders that exist in the container,
    or None when it could not be looked into."""
    spec = CONTAINERS[name]
    paths = [p for p, _ in candidates(name)]
    if not paths:
        return []
    # The trailing exit 0 matters: the loop's status is that of its last test,
    # so a run whose last candidate is absent would look like a failure. The
    # marker separates a root that is not there from one that is empty.
    script = (f"[ -d {spec['root']} ] || {{ echo {NOROOT}; exit 0; }}; "
              f"cd {spec['root']} || exit 0; "
              "for d in " + " ".join(paths) + "; do "
              "[ -e \"$d\" ] && du -sh \"$d\" 2>/dev/null; done; exit 0")
    r = docker(["exec", name, "sh", "-c", script],
               capture_output=True, text=True)
    if NOROOT in r.stdout:
        print(f"[ERROR] '{name}' has no {spec['root']}. An image built "
              f"before the root was renamed carries the old one, so pull "
              f"anything wanted out by hand before rebuilding.")
        return None
    if r.returncode != 0:
        print(f"[ERROR] Could not look inside '{name}'"
              + (f": {r.stderr.strip().splitlines()[0]}" if r.stderr.strip()
                 else ""))
        return None
    found = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            found.append((parts[1].strip(), parts[0]))
    return found


def choose(found, reasons, take_all):
    """Ask which folders to pull. Returns the chosen paths."""
    print()
    for i, (path, size) in enumerate(found, 1):
        why = reasons.get(path, reasons.get(path.split("/")[0], ""))
        print(f"  {i:2}. {path:32} {size:>7}   {why}")
    if take_all:
        return [p for p, _ in found]
    if not sys.stdin.isatty():
        print("\n  Not a terminal, so nothing is chosen. Use -y to take all.")
        return []
    print("\n  Numbers separated by spaces, 'a' for all, or Enter to skip.")
    try:
        reply = input("  Pull: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return []
    if not reply:
        return []
    if reply in ("a", "all"):
        return [p for p, _ in found]
    chosen = []
    for token in reply.replace(",", " ").split():
        if token.isdigit() and 1 <= int(token) <= len(found):
            chosen.append(found[int(token) - 1][0])
        else:
            print(f"[WARN] Ignoring '{token}'")
    return chosen


# ---------------------------------------------------------------------------
# The four verbs
# ---------------------------------------------------------------------------
def do_list(name, args):
    found = present(name)
    if found is None:
        return 1
    print(f"\n=== {name} ({CONTAINERS[name]['root']}) ===")
    if not found:
        print("  nothing to pull, no run output")
        return 0
    reasons = dict(candidates(name))
    for i, (path, size) in enumerate(found, 1):
        why = reasons.get(path, reasons.get(path.split("/")[0], ""))
        print(f"  {i:2}. {path:32} {size:>7}   {why}")
    return 0


def do_pull(name, args):
    """Returns (failures, [folders that landed])."""
    spec = CONTAINERS[name]
    found = present(name)
    if found is None:
        return 1, []
    if not found:
        print(f"[INFO] {name}: nothing to pull, no run output in "
              f"{spec['root']}")
        return 0, []
    print(f"\n=== {name} ({spec['root']}) ===")
    chosen = choose(found, dict(candidates(name)), args.yes)

    pulled, failed = [], 0
    target = os.path.join(os.path.abspath(args.out_dir), name)
    for path in chosen:
        source = f"{name}:{spec['root']}/{path}"
        print(f"[INFO] {source} -> {target}/")
        if args.dry_run:
            continue
        os.makedirs(target, exist_ok=True)
        if docker(["cp", source, target + os.sep]).returncode == 0:
            pulled.append(os.path.join(target, os.path.basename(path)))
        else:
            print(f"[WARN] Could not copy {path}")
            failed += 1
    return failed, pulled


def do_push(name, args):
    """Send this checkout's scripts, configurations and benchmarks in."""
    spec = CONTAINERS[name]
    print(f"\n=== {name}: pushing into {spec['root']} ===")
    failed = 0
    for rel, dest in spec["push"]:
        source = os.path.join(REPO, rel)
        if not os.path.exists(source.rstrip("/.")):
            print(f"[WARN] {rel} is not here, skipped")
            failed += 1
            continue
        print(f"[INFO] {rel} -> {name}:{dest}")
        if args.dry_run:
            continue
        # A destination naming a folder has to exist before docker cp.
        if dest.endswith("/"):
            docker(["exec", name, "mkdir", "-p", dest], capture_output=True)
        if docker(["cp", source, f"{name}:{dest}"]).returncode != 0:
            print(f"[WARN] Could not copy {rel}")
            failed += 1
    for rel, dest in spec["push_dirs"]:
        source = os.path.join(REPO, rel)
        if not os.path.isdir(source):
            print(f"[WARN] {rel} is not here, skipped")
            failed += 1
            continue
        count = len(os.listdir(source))
        print(f"[INFO] {rel}/ -> {name}:{dest}/  ({count} files)")
        if args.dry_run:
            continue
        # The folder may not exist yet, and docker cp of a folder onto an
        # existing one nests it, so the contents go in rather than the folder.
        docker(["exec", name, "mkdir", "-p", dest], capture_output=True)
        if docker(["cp", source + "/.", f"{name}:{dest}/"]).returncode != 0:
            print(f"[WARN] Could not copy {rel}/")
            failed += 1
    return failed


def shown(path):
    """A path relative to the repository when it is inside it, absolute when
    it is not. --out-dir /tmp would otherwise print a row of ../.."""
    rel = os.path.relpath(path, REPO)
    return path if rel.startswith("..") else rel


def do_trace(name, args, pulled):
    """Turn every trace that came back into a viewer JSON."""
    script = os.path.join(REPO, CONTAINERS[name]["tracer"])
    if not os.path.isfile(script):
        print(f"[WARN] {CONTAINERS[name]['tracer']} not found, nothing traced")
        return 1
    failed = 0
    for folder in pulled:
        if not os.path.isdir(folder):
            continue
        print(f"\n[INFO] Tracing {shown(folder)}")
        if args.dry_run:
            continue
        cmd = [sys.executable, script, folder, "-j", str(args.jobs)]
        code = subprocess.run(cmd).returncode
        # The batch passes --strict by default and ends with 3 when every
        # trace converted but some are degraded, which is not a failure.
        if code == 3:
            print(f"[WARN] {shown(folder)}: some traces are degraded, see "
                  f"metadata.degraded in their JSONs")
        elif code != 0:
            failed += 1
    return failed


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Move files between this checkout and the containers.",
        epilog="push   send this checkout's scripts, configurations and\n"
               "       benchmarks into the container\n"
               "pull   bring the run output back\n"
               "trace  pull, then turn every trace into a viewer JSON\n"
               "list   show what the container holds, copy nothing\n"
               "\n"
               "The container defaults to both.")
    parser.add_argument("action", choices=["push", "pull", "trace", "list"],
                        help="what to do")
    parser.add_argument("container", nargs="*", metavar="CONTAINER",
                        help=f"{' or '.join(sorted(CONTAINERS))}, "
                             f"or left out for both")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="do not ask: take every folder, start a stopped "
                             "container")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="say what would happen, copy nothing")
    parser.add_argument("-j", "--jobs", type=int, default=4, metavar="N",
                        help="traces to convert at a time with trace "
                             "(default 4)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, metavar="DIR",
                        help=f"where pulled folders land. Defaults to "
                             f"{DEFAULT_OUT_DIR}/<container>/")
    args = parser.parse_args()

    sys.stdout.reconfigure(line_buffering=True)

    if subprocess.run(["which", "docker"],
                      capture_output=True).returncode != 0:
        print("[ERROR] docker is not on PATH")
        return 2

    # One container is named CVA6 and the other gem5, so the case typed
    # at the prompt is not held against the reader.
    folded = {name.lower(): name for name in CONTAINERS}
    asked = [folded.get(n.lower(), n) for n in args.container]
    unknown = [n for n in asked if n not in CONTAINERS]
    if unknown:
        print(f"[ERROR] No such container: {', '.join(unknown)}. "
              f"Known: {', '.join(sorted(CONTAINERS))}")
        return 2
    names = asked or sorted(CONTAINERS)

    missing = [n for n in names if container_exists(n) is False]
    if missing:
        print(f"[ERROR] No container named {', '.join(missing)}. "
              f"See the README for how to create one.")
        names = [n for n in names if n not in missing]
    names = [n for n in names if ensure_running(n, args.yes)]
    if not names:
        return 2

    failed, pulled = 0, []
    for name in names:
        if args.action == "list":
            failed += do_list(name, args)
        elif args.action == "push":
            failed += do_push(name, args)
        else:
            hurt, got = do_pull(name, args)
            failed += hurt
            if args.action == "trace":
                failed += do_trace(name, args, got)
            pulled += got

    if args.action in ("pull", "trace"):
        if pulled:
            print(f"\n[INFO] {len(pulled)} folder(s) under "
                  f"{os.path.abspath(args.out_dir)}")
        elif not args.dry_run:
            print("\n[INFO] Nothing copied")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
