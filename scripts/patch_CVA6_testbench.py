#!/usr/bin/env python3
"""Apply or revert the testbench changes kept in verilator_changes/.

Two changes, each usable alone or with the other:

    vcd_window    bounds the waveform dump to a window of clock cycles, so a
                  long benchmark's VCD stays small enough to keep
    ddr3_memory   replaces the testbench's single-transaction axi2mem with a
                  DDR3-1600 model of gem5's DDR3_1600_8x8 and its MemCtrl

Each is a diff against the upstream files, and the DDR3 model also brings its
own RTL into corev_apu/tb/. This acts on the checkout it sits in, which is
/CVA6 inside the container, or on --cva6-root.

    python3 scripts/patch_CVA6_testbench.py status
    python3 scripts/patch_CVA6_testbench.py apply --vcd-window
    python3 scripts/patch_CVA6_testbench.py apply --ddr3
    python3 scripts/patch_CVA6_testbench.py apply --vcd-window --ddr3
    python3 scripts/patch_CVA6_testbench.py revert --ddr3
    python3 scripts/patch_CVA6_testbench.py revert

Apply adds to what is already in, and revert with no change named takes
everything out. Either one changes nothing until the model is rebuilt, so the
next run_CVA6.py goes without --keep-build. The window is a compile-time
define that has to be exported, since cva6.py's make target runs make
verilate again and a window given only on the command line is lost:

    export trace_start=100000 trace_end=200000
    python3 scripts/run_CVA6.py benchmarks/viewer/daxpy.S
"""
import argparse
import os
import shutil
import subprocess
import sys

CHANGES_DIR = "verilator_changes"

# Every upstream file a change edits, relative to the CVA6 root, with the
# comment marker its notice is written in.
TARGETS = {
    os.path.join("corev_apu", "tb", "ariane_tb.cpp"): "//",
    os.path.join("corev_apu", "tb", "ariane_testharness.sv"): "//",
    "Makefile": "#",
}

# In the order they are applied. Each diff edits some of TARGETS, and a change
# may bring whole files of its own, copied from its folder into the tree.
CHANGES = {
    "vcd_window": {
        "diff": os.path.join("vcd_window", "vcd_window.patch"),
        "adds": {},
    },
    "ddr3_memory": {
        "diff": os.path.join("ddr3_memory", "ddr3_memory.patch"),
        "adds": {
            os.path.join("ddr3_memory", "rtl", name):
                os.path.join("corev_apu", "tb", name)
            for name in ("ddr3_pkg.sv", "ddr3_scheduler.sv",
                         "axi_ddr3_slave.sv")
        },
    },
}
FLAGS = {"vcd_window": "--vcd-window", "ddr3_memory": "--ddr3"}

# Where apply keeps each upstream file. The container has no git repository
# to restore one from, so the copy is the only way back.
BACKUP_SUFFIX = ".upstream"

NOTICE_MARK = "NOTICE OF MODIFICATION"
APPLIED_MARK = "Applied:"
NOTICE = """\
---------------------------------------------------------------------------
NOTICE OF MODIFICATION

This file has been modified by the FaMAF CVA6 Project, Universidad Nacional
de Cordoba, and is NOT the upstream file. scripts/patch_CVA6_testbench.py
applied the changes below from verilator_changes/, and its revert puts the
upstream file back.

Applied: {applied}

This notice is required by section 4(b) of the Apache License 2.0, which
Solderpad 0.51 is built on and which governs the original file: a modified
file must carry a prominent notice stating that it was changed.
---------------------------------------------------------------------------
"""


def default_root():
    """The checkout this script sits in, which is /CVA6 in the container."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def usable(root):
    """What is missing for this to work on root, or None."""
    for change in CHANGES.values():
        for rel in [change["diff"], *change["adds"]]:
            if not os.path.isfile(os.path.join(root, CHANGES_DIR, rel)):
                return f"no {CHANGES_DIR}/{rel}"
    for rel in TARGETS:
        if not os.path.isfile(os.path.join(root, rel)):
            return f"no {rel}"
    if not shutil.which("patch"):
        return "no patch command on PATH"
    return None


def read_notice(path):
    """The changes a target's notice lists, None with no notice, and 'legacy'
    for the notice of a whole modified copy, as the earlier window tool put
    in."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        head = handle.read(4096)
    if NOTICE_MARK not in head:
        return None
    for line in head.splitlines():
        text = line.lstrip("/# ").strip()
        if text.startswith(APPLIED_MARK):
            names = text[len(APPLIED_MARK):].split(",")
            return [name.strip() for name in names if name.strip()]
    return "legacy"


def applied(root):
    """The changes in, as the notices and the added files say, and whether the
    tree is in a state this script made."""
    found, legacy = set(), False
    for rel in TARGETS:
        names = read_notice(os.path.join(root, rel))
        if names == "legacy":
            legacy = True
        elif names:
            found.update(names)
    for name, change in CHANGES.items():
        adds = [os.path.join(root, dest) for dest in change["adds"].values()]
        if adds and all(os.path.isfile(path) for path in adds):
            found.add(name)
    return [name for name in CHANGES if name in found], legacy


def notice_for(marker, names):
    text = NOTICE.format(applied=", ".join(names))
    return "".join(f"{marker} {line}".rstrip() + "\n"
                   for line in text.splitlines()) + "\n"


def restore_upstream(root, dry_run):
    """Put every backed-up target back and delete the added files."""
    for rel in TARGETS:
        target = os.path.join(root, rel)
        backup = target + BACKUP_SUFFIX
        if os.path.isfile(backup):
            print(f"[INFO] {rel}: upstream copy back in")
            if not dry_run:
                shutil.copy2(backup, target)
                os.remove(backup)
        elif read_notice(target) is not None:
            print(f"[ERROR] {rel} is modified and there is no "
                  f"{os.path.basename(backup)} to put back. On the host, "
                  f"'git checkout -- {rel}' restores it.")
            return False
    for change in CHANGES.values():
        for dest in change["adds"].values():
            path = os.path.join(root, dest)
            if os.path.isfile(path):
                print(f"[INFO] {dest}: removed")
                if not dry_run:
                    os.remove(path)
    return True


def build(root, names, dry_run):
    """From the upstream files, put the named changes in, in CHANGES order."""
    if not names:
        return True
    for rel in TARGETS:
        target = os.path.join(root, rel)
        print(f"[INFO] {rel}: upstream copy kept as "
              f"{os.path.basename(target + BACKUP_SUFFIX)}")
        if not dry_run:
            shutil.copy2(target, target + BACKUP_SUFFIX)
    touched = {}
    for name in names:
        change = CHANGES[name]
        diff = os.path.join(root, CHANGES_DIR, change["diff"])
        print(f"[INFO] {name}: applying {CHANGES_DIR}/{change['diff']}")
        cmd = ["patch", "-p1", "--forward", "--no-backup-if-mismatch",
               "-s", "-d", root, "-i", diff]
        if dry_run:
            cmd.append("--dry-run")
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            print(f"[ERROR] {name} did not apply:\n"
                  f"{(done.stdout + done.stderr).strip()}")
            return False
        with open(diff, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("+++ b/"):
                    touched.setdefault(line[6:].strip(), []).append(name)
        for src, dest in change["adds"].items():
            print(f"[INFO] {name}: {dest} added")
            if not dry_run:
                shutil.copy2(os.path.join(root, CHANGES_DIR, src),
                             os.path.join(root, dest))
    if not dry_run:
        # Each file's notice names the changes that edited it.
        for rel, by in sorted(touched.items()):
            target = os.path.join(root, rel)
            with open(target, encoding="utf-8") as handle:
                body = handle.read()
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(notice_for(TARGETS[rel], by) + body)
    return True


def do_status(root):
    names, legacy = applied(root)
    print(f"[INFO] CVA6 root: {root}")
    for rel in TARGETS:
        target = os.path.join(root, rel)
        notice = read_notice(target)
        where = ("upstream" if notice is None else "legacy modified copy"
                 if notice == "legacy" else "modified: " + ", ".join(notice))
        kept = (" (upstream copy kept)"
                if os.path.isfile(target + BACKUP_SUFFIX) else "")
        print(f"  {rel:34} {where}{kept}")
    if legacy:
        print("[WARN] A whole modified copy from an earlier tool is in. "
              "apply or revert replaces it from its upstream copy")
    elif names:
        print(f"[INFO] In: {', '.join(names)}. Rebuild the model, which the "
              f"next run_CVA6.py without --keep-build does")
    else:
        print("[INFO] Upstream, both changes out")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Apply or revert the testbench changes in "
                    "verilator_changes/: the VCD window and the DDR3 memory.")
    parser.add_argument("action", choices=["status", "apply", "revert"],
                        help="Status reports, apply puts the named changes in "
                             "beside those already in, revert takes the named "
                             "ones out, or all of them")
    parser.add_argument("--vcd-window", action="store_true",
                        help="The windowed waveform dump")
    parser.add_argument("--ddr3", action="store_true",
                        help="The DDR3-1600 memory model in place of axi2mem")
    parser.add_argument("--cva6-root", default=None, metavar="DIR",
                        help="The checkout to change. Defaults to the one "
                             "this script sits in, which is /CVA6 inside the "
                             "container")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Say what would change and stop")
    args = parser.parse_args()

    root = os.path.abspath(args.cva6_root or default_root())
    why = usable(root)
    if why:
        print(f"[ERROR] Cannot patch '{root}': {why}. Point --cva6-root at a "
              f"CVA6 checkout with {CHANGES_DIR}/ in it.")
        return 2
    if args.action == "status":
        return do_status(root)

    named = [name for name in CHANGES if getattr(args, FLAGS[name][2:]
                                                 .replace("-", "_"))]
    current, legacy = applied(root)
    if args.action == "apply":
        if not named:
            parser.error("apply needs --vcd-window, --ddr3 or both")
        wanted = [name for name in CHANGES
                  if name in current or name in named]
    else:
        wanted = ([name for name in current if name not in named]
                  if named else [])
    if wanted == current and not legacy:
        print(f"[INFO] Nothing to do, in: {', '.join(current) or 'none'}")
        return 0
    if not restore_upstream(root, args.dry_run):
        return 1
    if not build(root, wanted, args.dry_run):
        restore_upstream(root, args.dry_run)
        return 1
    if args.dry_run:
        print(
            f"[INFO] Dry run, would leave: {', '.join(wanted) or 'upstream'}")
        return 0
    print(f"[INFO] In: {', '.join(wanted) or 'none, upstream again'}. "
          f"Rebuild the model: the next run_CVA6.py without --keep-build")
    if "vcd_window" in wanted:
        print("[INFO] Export the window, in clock cycles, before the run:"
              "\n           export trace_start=100000 trace_end=200000")
    if "ddr3_memory" in wanted:
        print("[INFO] The DDR3 report prints from a final block into the "
              "run's log, verif/sim/out_<date>/veri-testharness_sim/*.log.iss")
    return 0


if __name__ == "__main__":
    sys.exit(main())
