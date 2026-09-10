#!/usr/bin/env python3
"""Flatten the CVA6 RTL into one folder, following the Flist manifests.

The manifests name the sources the core is built from, spread over the whole
tree and written with variables the tools expand. This resolves them and copies
every file into a single directory, which is what the RTL readers and the
tracer's signal search expect.

  python3 get_CVA6_files.py              # copy into CVA6_files/
  python3 get_CVA6_files.py -o rtl       # a different destination
  python3 get_CVA6_files.py --dry-run    # list what would be copied
  python3 get_CVA6_files.py -v           # name every file as it is copied
"""
import os
import sys
import shutil
import argparse


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

DEFAULT_DEST = "CVA6_files"

# The Flist names the config package through ${TARGET_CFG}, which the build
# system sets. This is the configuration the project measures.
DEFAULT_TARGET_CFG = "cv64a6_imafdc_sv39_hpdcache_wb"

# The two manifests, relative to the repo root. The second is the HPDcache,
# which keeps its own list under its own variable.
FLISTS = [
    os.path.join("core", "Flist.cva6"),
    os.path.join("core", "cache_subsystem",
                 "hpdcache", "rtl", "hpdcache.Flist"),
]

# What an +incdir+ entry contributes. The directory is read one level deep,
# matching how the simulators resolve an include path.
HEADER_SUFFIXES = (".sv", ".v", ".svh", ".vh", ".h")


def manifest_vars(repo_root, target_cfg):
    """The variables the Flist files expand, as the build system sets them."""
    return {
        "${CVA6_REPO_DIR}": repo_root,
        "${HPDCACHE_DIR}": os.path.join(
            repo_root, "core", "cache_subsystem", "hpdcache"),
        "${TARGET_CFG}": target_cfg,
    }


def read_manifest(path, variables):
    """Yield (kind, resolved_path) for every entry, kind being file or incdir.

    Comments, blank lines and -F directives are skipped. A -F pulls in another
    manifest, and both of ours are already listed explicitly.
    """
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("-F"):
                continue
            for name, value in variables.items():
                line = line.replace(name, value)
            if line.startswith("+incdir+"):
                entries.append(("incdir", line[len("+incdir+"):]))
            else:
                entries.append(("file", line))
    return entries


def sources_for(kind, path):
    """The files one entry contributes, and a reason when it contributes none."""
    if kind == "incdir":
        if not os.path.isdir(path):
            return [], f"+incdir+ directory not found: {path}"
        found = sorted(
            os.path.join(path, name) for name in os.listdir(path)
            if name.endswith(HEADER_SUFFIXES)
            and os.path.isfile(os.path.join(path, name)))
        return found, None
    if not os.path.isfile(path):
        return [], f"file not found: {path}"
    return [path], None


def main():
    parser = argparse.ArgumentParser(
        description="Copy the CVA6 RTL named by the Flist manifests into one "
                    "folder.")
    parser.add_argument("-o", "--dest", default=DEFAULT_DEST, metavar="DIR",
                        help=f"Destination directory (default {DEFAULT_DEST}/)")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="List what would be copied and stop")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Name every file as it is copied")
    parser.add_argument("-t", "--target-cfg", default=DEFAULT_TARGET_CFG,
                        metavar="CFG",
                        help=f"Configuration whose config package is copied "
                             f"(default {DEFAULT_TARGET_CFG})")
    parser.add_argument("--repo", default=REPO_ROOT, metavar="DIR",
                        help="CVA6 repository root (default: this script's "
                             "folder)")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo)
    dest = os.path.abspath(args.dest)
    variables = manifest_vars(repo_root, args.target_cfg)

    print(f"[INFO] Repository: {repo_root}")
    print(f"[INFO] Destination: {dest}")
    print(f"[INFO] Target config: {args.target_cfg}")

    # Gather first, copy second, so a missing manifest stops us before the
    # destination has been touched.
    planned = []
    warnings = []
    for relative in FLISTS:
        manifest = os.path.join(repo_root, relative)
        if not os.path.isfile(manifest):
            print(f"[ERROR] Manifest not found: {manifest}")
            return 1
        entries = read_manifest(manifest, variables)
        print(f"[INFO] {relative}: {len(entries)} entries")
        for kind, path in entries:
            found, problem = sources_for(kind, path)
            if problem:
                warnings.append(problem)
            planned.extend(found)

    # The destination is flat, so two sources sharing a basename would leave
    # only the last one. A clash takes the parent directory as a prefix and
    # walks up until the names differ, with a depth limit for deep trees.
    by_name = {}
    for path in planned:
        by_name.setdefault(os.path.basename(path), []).append(path)
    clashes = {name: paths for name, paths in by_name.items()
               if len(set(paths)) > 1}

    # Destination name per source path. Only clashing files are renamed, so a
    # tree with no clash is byte-for-byte what it was before.
    dest_name = {}
    for path in planned:
        name = os.path.basename(path)
        if name in clashes:
            parent = os.path.basename(os.path.dirname(path))
            dest_name[path] = f"{parent}__{name}" if parent else name
        else:
            dest_name[path] = name
    # A prefix can itself collide, when two clashing copies share a parent
    # directory name. Walk further up until the names are distinct.
    for name, paths in clashes.items():
        unique = sorted(set(paths))
        depth = 1
        while len({dest_name[p] for p in unique}) < len(unique) and depth < 6:
            depth += 1
            for path in unique:
                parts = os.path.dirname(path).split(os.sep)[-depth:]
                dest_name[path] = "__".join(parts + [name])

    print(f"[INFO] {len(planned)} source(s) named, {len(by_name)} distinct "
          f"filename(s)")

    for problem in warnings:
        print(f"[WARN] {problem}")
    for name, paths in sorted(clashes.items()):
        print(f"[WARN] name clash on {name}, every copy kept under a "
              f"directory-prefixed name:")
        for path in sorted(set(paths)):
            print(f"           {os.path.relpath(path, repo_root)}"
                  f"  ->  {dest_name[path]}")

    if args.dry_run:
        if args.verbose:
            for path in planned:
                print(f"       {os.path.relpath(path, repo_root)}")
        print("[INFO] Dry run, nothing written")
        return 0

    os.makedirs(dest, exist_ok=True)
    copied = 0
    for path in planned:
        shutil.copy2(path, os.path.join(dest, dest_name[path]))
        copied += 1
        if args.verbose:
            print(f"       {os.path.relpath(path, repo_root)}"
                  f"  ->  {dest_name[path]}")

    print(f"[INFO] Copied {copied} file(s) into {dest}")
    if warnings or clashes:
        print(f"[INFO] {len(warnings)} missing, {len(clashes)} clash(es), "
              f"every clashing copy kept under a prefixed name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
