#!/usr/bin/env python3
"""Build the program pairs FlowCompare offers under Load sample pair.

A pair is one program's MinorFlow JSON from the matched gem5 configuration
beside its CVA6Flow JSON from the RTL. Each side is written as
viewers/pairs/<program>.<side>.js, the JSON gzipped and base64-encoded inside
a script, so the page loads it with a script tag, served or opened from disk,
and unpacks it with the browser's own gzip support. viewers/pairs/pairs.js
lists them, and is what FlowCompare reads first. The two folders hold tracer
JSONs named after their programs, as a batch run leaves them once converted.

A program whose JSON on either side is 50 MiB or more is left out, and a
second run replaces what the first wrote.

    python3 scripts/make_flowcompare_pairs.py
    python3 scripts/make_flowcompare_pairs.py --model DIR --label Stock
    python3 scripts/make_flowcompare_pairs.py --dry-run
"""
import argparse
import base64
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(REPO, "viewers", "pairs")
MODEL_DIR = os.path.join(REPO, "container_results", "review", "patch")
RTL_DIR = os.path.join(REPO, "container_results", "review", "rtl")

# The largest JSON a program may have on either side to be paired.
MAX_JSON_BYTES = 50 * 1024 * 1024

# What FlowCompare checks each side against, as in its JSON_KINDS.
SIDES = {
    "minor": {"tool": "minorflow_tracer", "schema": 7,
              "path_key": "trace_path",
              "run_path": "results/run/{}_trace.txt"},
    "cva6": {"tool": "cva6flow_tracer", "schema": 3,
             "path_key": "vcd_path",
             "run_path": "results/run/{}.vcd"},
}

MANIFEST = "pairs.js"
MANIFEST_GLOBAL = "window.__PAIR_MANIFEST__"
PAIR_GLOBAL = "window.__PAIR_GZIP__"


def programs(model_dir, rtl_dir):
    """Programs with a JSON in both folders, by name."""
    def names(folder):
        return {name[:-5] for name in os.listdir(folder)
                if name.endswith(".json")}
    return sorted(names(model_dir) & names(rtl_dir))


def read_side(path, side, program):
    """The JSON, checked against what FlowCompare expects, with the path of
    the run it came from written as a run folder path rather than the
    container's."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    spec = SIDES[side]
    metadata = data.get("metadata", {})
    if (metadata.get("tool") != spec["tool"]
            or metadata.get("schema_version") != spec["schema"]):
        raise ValueError(f"{path} is {metadata.get('tool')} schema "
                         f"{metadata.get('schema_version')}, not "
                         f"{spec['tool']} schema {spec['schema']}")
    metadata[spec["path_key"]] = spec["run_path"].format(program)
    return data


def write_side(data, out_path):
    """The JSON as a script holding it gzipped, the same bytes on every run."""
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    packed = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0))
    text = f'{PAIR_GLOBAL} = "{packed.decode("ascii")}";\n'
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return len(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=MODEL_DIR,
                        help="Folder of MinorFlow JSONs, the gem5 side. "
                             "Defaults to container_results/review/patch")
    parser.add_argument("--rtl", default=RTL_DIR,
                        help="Folder of CVA6Flow JSONs, the RTL side. "
                             "Defaults to container_results/review/rtl")
    parser.add_argument("--label", default="Patch",
                        help="What the gem5 side is called in the manifest. "
                             "Defaults to Patch")
    parser.add_argument("--out", default=OUT_DIR,
                        help="Where the pairs go. Defaults to viewers/pairs")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be paired and write nothing")
    args = parser.parse_args()
    for folder in (args.model, args.rtl):
        if not os.path.isdir(folder):
            print(f"[ERROR] {folder} is not a folder", file=sys.stderr)
            return 1

    chosen, skipped = [], []
    for program in programs(args.model, args.rtl):
        paths = {"minor": os.path.join(args.model, program + ".json"),
                 "cva6": os.path.join(args.rtl, program + ".json")}
        biggest = max(os.path.getsize(path) for path in paths.values())
        if biggest >= MAX_JSON_BYTES:
            skipped.append((program, biggest))
        else:
            chosen.append((program, paths))
    for program, size in skipped:
        print(f"[INFO] {program}: left out, a {size / 2**20:.0f} MiB JSON")
    if args.dry_run:
        for program, _ in chosen:
            print(f"[INFO] {program}: would be paired")
        return 0

    os.makedirs(args.out, exist_ok=True)
    manifest, written = [], set()
    for program, paths in chosen:
        entry = {"label": program, "model": args.label}
        sizes = []
        for side, path in paths.items():
            data = read_side(path, side, program)
            name = f"{program}.{side}.js"
            sizes.append(write_side(data, os.path.join(args.out, name)))
            written.add(name)
            entry[side] = {"file": name, "tool": SIDES[side]["tool"],
                           "schema_version": SIDES[side]["schema"],
                           "n_records": len(data["instructions"])}
        manifest.append(entry)
        print(f"[INFO] {program}: {sum(sizes) / 2**20:.2f} MiB written")
    # Files a previous run wrote for a program no longer paired go too.
    for name in os.listdir(args.out):
        if name.endswith((".minor.js", ".cva6.js")) and name not in written:
            os.remove(os.path.join(args.out, name))
            print(f"[INFO] removed {name}, no longer paired")
    listing = json.dumps(manifest, indent=2)
    with open(os.path.join(args.out, MANIFEST), "w",
              encoding="utf-8") as handle:
        handle.write(f"{MANIFEST_GLOBAL} = {listing};\n")
    total = sum(os.path.getsize(os.path.join(args.out, name))
                for name in written)
    print(f"[INFO] {len(manifest)} pair(s), {total / 2**20:.1f} MiB, in "
          f"{os.path.relpath(args.out, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
