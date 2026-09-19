#!/usr/bin/env python3
"""Create, apply, revert and rebuild MinorCPU_CVA6.patch in the gem5 tree.

The loop for working on the patch. Edit the sources under src/, create the
patch from them, rebuild, measure. Run it from the gem5 root, inside the
container, where /gem5 is the gem5 tree the image patched. The image keeps no
git history, so create diffs the tree against the pristine sources it kept.

    python3 scripts/patch_gem5.py status    # applied or not, and which builds
    python3 scripts/patch_gem5.py create    # the tree becomes the patch file
    python3 scripts/patch_gem5.py revert    # take the patch back out
    python3 scripts/patch_gem5.py apply     # put it back in
    python3 scripts/patch_gem5.py build     # rebuild, asking PATCH or EXP

build/RISCV_PATCH is what every TEST is measured against, so an edited patch
belongs in build/RISCV_EXP until it is worth adopting.
"""
import argparse
import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

# The copy under gem5_configs/config/ mirrors the repository, and run_gem5.py
# hashes it to catch an edited but unrebuilt patch. The root copy is the
# fallback, for an image built before gem5_configs/ existed.
PATCH_IN_TREE = "MinorCPU_CVA6.patch"
PATCH_IN_CONFIGS = os.path.join("gem5_configs", "config",
                                "MinorCPU_CVA6.patch")

# Every file the patch touches is under src/, so the diff is scoped to it and
# an unrelated edit elsewhere in the tree cannot leak into the patch.
PATCH_PATHS = ("src",)

# The pristine PATCH_PATHS, archived by the image before the patch went in and
# before gem5's git history was dropped. create diffs the tree against it.
PRISTINE = ".pristine_src.tar.xz"

# What gem5's .gitignore kept out of a git diff under src/, and the leftovers
# of a failed patch, which a plain diff would otherwise put in the patch.
IGNORED = ("*.pyc", "*~", ".*.swp", ".*.swo", "*.orig", "*.rej",
           "parser.out", "parsetab.py", "cscope.files", "cscope.out")
IGNORED_DIRS = ("__pycache__",)

# The hash of the patch the build was made from, kept beside the tree so a run
# can tell an edited patch from the one the binary carries.
MARKER = ".built_patch_sha1"

BUILDS = {"PATCH": "RISCV_PATCH", "EXP": "RISCV_EXP"}

# Named in the binary only when the patch is in it.
PATCH_MARKER = b"Axi2MemPort"


def git(args, **kwargs):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          **kwargs)


def at_gem5_root():
    """gem5's own tree, which is the only place any of this makes sense."""
    return os.path.isdir("src") and os.path.isdir("build_opts")


def patch_file():
    """The patch to read, preferring the copy under gem5_configs/config/,
    since that is the one the repository keeps."""
    for path in (PATCH_IN_CONFIGS, PATCH_IN_TREE):
        if os.path.isfile(path):
            return path
    return None


def short_hash(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return hashlib.sha1(handle.read()).hexdigest()[:12]


def built_hash():
    if not os.path.isfile(MARKER):
        return None
    with open(MARKER) as handle:
        parts = handle.read().split()
    return parts[0][:12] if parts else None


def applied(path):
    """Whether the patch is in the tree, told by whether it reverses. git
    apply needs no repository, so this works in a tree without history."""
    return git(["apply", "--reverse", "--check", path]).returncode == 0


def build_has_patch(name):
    """Whether a built binary carries the SimObject only the patch adds."""
    for suffix in ("gem5.opt", "gem5.fast", "gem5.debug"):
        binary = os.path.join("build", name, suffix)
        if os.path.isfile(binary):
            with open(binary, "rb") as handle:
                return PATCH_MARKER in handle.read()
    return None


def confirm(question, assume_yes):
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("[INFO] Not a terminal, so nothing is changed. Pass -y.")
        return False
    try:
        return input(f"  {question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def ask_build(chosen, assume_yes):
    """Which build to remake. PATCH is the one the tables rest on, so the
    question is asked rather than defaulted."""
    if chosen:
        return BUILDS[chosen]
    if assume_yes or not sys.stdin.isatty():
        print("[ERROR] Which build is not something to assume. Pass "
              "--build PATCH or --build EXP.")
        return None
    print("  PATCH  build/RISCV_PATCH, what every TEST is measured against")
    print("  EXP    build/RISCV_EXP, for a patch being worked on")
    try:
        reply = input("  Rebuild which? [PATCH/EXP] ").strip().upper()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if reply not in BUILDS:
        print(f"[ERROR] Not one of {', '.join(sorted(BUILDS))}.")
        return None
    return BUILDS[reply]


def do_status(args):
    path = patch_file()
    if path is None:
        print(f"[ERROR] No {PATCH_IN_CONFIGS} and no {PATCH_IN_TREE}.")
        return 1
    print(f"  patch file   {path}")
    print(f"  in the tree  {'yes' if applied(path) else 'no'}")
    current, built = short_hash(path), built_hash()
    print(f"  hash         {current}"
          + (f", built from {built}" if built else ", nothing built recorded"))
    if built and current and built != current:
        print("               the patch has changed since a build recorded "
              "it")
    for short, name in sorted(BUILDS.items()):
        has = build_has_patch(name)
        state = ("not built" if has is None
                 else "patched" if has else "NOT patched")
        print(f"  build/{name:11} {state}")
    return 0


def ignored(path):
    """Whether create leaves this path out of the patch."""
    parts = path.split("/")
    return (any(part in IGNORED_DIRS for part in parts)
            or any(fnmatch.fnmatch(parts[-1], pattern) for pattern in IGNORED))


def pristine_diff():
    """The tree against the pristine archive, as (patch, error)."""
    with tempfile.TemporaryDirectory(prefix=".pristine_", dir=".") as tmp:
        tmp = os.path.basename(tmp)
        done = subprocess.run(["tar", "-xJf", PRISTINE, "-C", tmp],
                              capture_output=True, text=True)
        if done.returncode != 0:
            return None, (f"tar could not read {PRISTINE}: "
                          f"{done.stderr.strip()}")
        sections = []
        for top in PATCH_PATHS:
            done = git(["diff", "--no-index", "--no-renames", "--no-color",
                        "--", os.path.join(tmp, top), top])
            # 1 means the two differ, which is the point. Above that is git's
            # own failure.
            if done.returncode > 1:
                return None, f"git diff failed: {done.stderr.strip()}"
            for chunk in re.split(r"(?m)^(?=diff --git )", done.stdout):
                if not chunk:
                    continue
                head, hunks, body = chunk.partition("\n@@")
                head = (head.replace(f"a/{tmp}/", "a/")
                        .replace(f"b/{tmp}/", "b/"))
                path = head.split("\n", 1)[0].split(" b/", 1)[1]
                if not ignored(path):
                    sections.append((path.encode(), head + hunks + body))
    return "".join(text for _, text in sorted(sections)), None


def git_diff():
    """The tree against its git HEAD, as (patch, error), for a container
    whose image still carries gem5's git clone."""
    # git diff ignores a file git has never heard of, and the patch adds nine
    # of them, so the untracked ones are marked intent-to-add for the diff.
    listed = git(["ls-files", "--others", "--exclude-standard", "--"]
                 + list(PATCH_PATHS))
    untracked = listed.stdout.split()
    if untracked:
        git(["add", "-N", "--"] + untracked)
    done = git(["diff", "--"] + list(PATCH_PATHS))
    # Taken straight back out, so reading the tree does not leave the index
    # changed. Without this every create added nine entries to git status.
    if untracked:
        git(["reset", "-q", "--"] + untracked)
    if done.returncode != 0:
        return None, f"git diff failed: {done.stderr.strip()}"
    return done.stdout, None


def do_create(args):
    """Write the patch from the tree, new files included."""
    if os.path.isfile(PRISTINE):
        patch, error = pristine_diff()
    elif os.path.isdir(".git"):
        patch, error = git_diff()
    else:
        patch, error = None, (f"No {PRISTINE} and no .git, so there is "
                              f"nothing to tell the patch from gem5's own "
                              f"sources.")
    if error:
        print(f"[ERROR] {error}")
        return 1
    if not patch.strip():
        print("[ERROR] The tree has no changes under "
              f"{', '.join(PATCH_PATHS)}, so there is no patch to make. "
              f"Apply it first, or edit the sources.")
        return 1

    files = patch.count("\ndiff --git") + patch.count("diff --git", 0, 10)
    hunks = patch.count("\n@@ ")
    print(f"[INFO] {files} file(s), {hunks} hunk(s) from the tree")
    target = PATCH_IN_CONFIGS if os.path.isdir(
        os.path.dirname(PATCH_IN_CONFIGS)) else PATCH_IN_TREE
    existing = short_hash(target)
    if existing:
        print(f"[INFO] {target} is currently {existing}")
    if not confirm(f"Overwrite {target}?", args.yes):
        return 0

    if existing:
        backup = target + ".bak"
        shutil.copy2(target, backup)
        print(f"[INFO] Previous patch kept as {backup}")
    with open(target, "w") as handle:
        handle.write(patch)
    # A patch that does not reverse is not a description of this tree, which
    # is worth knowing now rather than at the next build.
    if not applied(target):
        keep = f" Keep {target}.bak." if existing else ""
        print(f"[WARN] {target} does not reverse against this tree, so it "
              f"does not describe it.{keep}")
    print(f"[INFO] Wrote {target}, now {short_hash(target)}")
    if target != PATCH_IN_TREE and os.path.isfile(PATCH_IN_TREE):
        shutil.copy2(target, PATCH_IN_TREE)
        print(f"[INFO] Refreshed {PATCH_IN_TREE}, the copy an older image "
              f"hashes")
    print("[INFO] Next: 'build' to remake a build from it")
    return 0


def do_apply(args, reverse=False):
    path = patch_file()
    if path is None:
        print(f"[ERROR] No {PATCH_IN_CONFIGS} and no {PATCH_IN_TREE}.")
        return 1
    flags = ["-R"] if reverse else []
    word = "revert" if reverse else "apply"
    if git(["apply"] + flags + ["--check", path]).returncode != 0:
        state = "already out of" if reverse else "already in"
        print(f"[ERROR] Cannot {word} {path}: it is {state} the tree, or the "
              f"tree has moved under it. 'status' says which.")
        return 1
    if not confirm(f"{word.capitalize()} {path}?", args.yes):
        return 0
    done = git(["apply"] + flags + [path])
    if done.returncode != 0:
        print(f"[ERROR] git apply failed: {done.stderr.strip()}")
        return 1
    print(f"[INFO] {'Reverted' if reverse else 'Applied'} {path}")
    print("[INFO] The builds are unchanged until 'build' remakes one")
    return 0


def do_build(args):
    name = ask_build(args.build, args.yes)
    if name is None:
        return 2
    path = patch_file()
    if path and not applied(path):
        print(f"[WARN] {path} is not in the tree, so this would build "
              f"unpatched sources into build/{name}. 'apply' first.")
        if not confirm("Build anyway?", args.yes):
            return 1
    jobs = args.jobs or max(1, (os.cpu_count() or 2) // 2)
    print(f"[INFO] Rebuilding build/{name} with -j{jobs}. The first one "
          f"takes hours, a later one minutes.")
    for cmd in (["scons", "defconfig", f"build/{name}", "build_opts/RISCV"],
                ["scons", f"build/{name}/gem5.opt", f"-j{jobs}"]):
        print("  $ " + " ".join(cmd))
        if args.dry_run:
            continue
        if subprocess.run(cmd).returncode != 0:
            print(f"[ERROR] {cmd[0]} failed, so build/{name} is unfinished.")
            return 1
    if args.dry_run:
        return 0

    # The marker is what run_gem5.py reads, and it speaks for RISCV_PATCH, the
    # build the tables rest on. Moving it for RISCV_EXP would say the measured
    # build had been remade when it had not.
    if name == BUILDS["PATCH"] and path:
        with open(MARKER, "w") as handle:
            handle.write(f"{short_hash(path)}  {os.path.basename(path)}\n")
        print(f"[INFO] {MARKER} now records {short_hash(path)}")
    else:
        print(f"[INFO] {MARKER} still describes build/{BUILDS['PATCH']}, so "
              f"run_gem5.py may call the patch stale. On {name} that is "
              f"expected.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Work on MinorCPU_CVA6.patch inside the gem5 tree.",
        epilog="status  whether the patch is in the tree, and which builds\n"
               "create  write the patch from the tree, new files included\n"
               "apply   put the patch into the tree\n"
               "revert  take it back out\n"
               "build   remake build/RISCV_PATCH or build/RISCV_EXP\n")
    parser.add_argument("action",
                        choices=["status", "create", "apply", "revert",
                                 "build"],
                        help="What to do")
    parser.add_argument("--build", choices=sorted(BUILDS), default=None,
                        help="Which build to remake, instead of being asked")
    parser.add_argument("-j", "--jobs", type=int, default=None, metavar="N",
                        help="Compile jobs. Defaults to half the cores")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Do not ask before changing the tree")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Print the build commands without running "
                             "them. Only build takes it")
    args = parser.parse_args()

    if not at_gem5_root():
        print("[ERROR] This is not a gem5 tree. Run it from the gem5 root, "
              "which is /gem5 in the container.")
        return 2
    if not shutil.which("git"):
        print("[ERROR] No git on PATH. It applies and diffs the patch, "
              "with or without a repository.")
        return 2

    if args.action == "status":
        return do_status(args)
    if args.action == "create":
        return do_create(args)
    if args.action == "apply":
        return do_apply(args)
    if args.action == "revert":
        return do_apply(args, reverse=True)
    return do_build(args)


if __name__ == "__main__":
    sys.exit(main())
