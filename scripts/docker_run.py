#!/usr/bin/env python3
"""Work inside the project's containers without the docker incantations.

Six things to do, one word each. The container is cva6, gem5, or left out
where both make sense. A stopped container is started first.

    python3 scripts/docker_run.py status           # what is up, and where
    python3 scripts/docker_run.py shell gem5       # a shell inside
    python3 scripts/docker_run.py serve CVA6       # the viewer in a browser
    python3 scripts/docker_run.py stop             # stop both

    python3 scripts/docker_run.py run gem5 daxpy   # through the side's driver
    python3 scripts/docker_run.py exec CVA6 -- ls /CVA6/benchmarks

run puts the side's driver in front of what follows, so the driver's own name
and place are one less thing to remember. exec runs the command as given.
Neither copies anything in: scripts/docker_sync.py push is what does that.

shell is the one command for start, enter and pass the display through, so
    docker start gem5 && docker exec -e DISPLAY=$DISPLAY -it gem5 bash
is shell gem5. Use --display for a value other than the host's own.
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


def load_module(rel, name):
    """Import a sibling script for its tables and helpers, without running
    it."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(REPO, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The container names, their roots and the start-it-first handling are all
# there already, and the viewer port is fixed at creation by the other.
SYNC = load_module("scripts/docker_sync.py", "docker_sync")
MAKER = load_module("scripts/make_containers.py", "make_containers")
CONTAINERS = SYNC.CONTAINERS
PORT = MAKER.VIEWER_PORT

# The driver each side runs its workloads through, at the container root. The
# repository's script-names check is what keeps these two names honest.
DRIVERS = {"gem5": "run_gem5.py", "CVA6": "run_CVA6.py"}

# What serve puts in the browser, and the name it is recognised by inside.
SERVER = "serve_viewers.py"


def docker(args, **kwargs):
    return subprocess.run(["docker"] + args, **kwargs)


def display_args(args):
    """The -e DISPLAY a GUI inside the container needs, or nothing.

    make_containers.py sets it at creation, so this is for a container made
    without it and for overriding the value, which Docker Desktop spells
    host.docker.internal:0 rather than as the host's own DISPLAY."""
    if args.no_display:
        return []
    value = args.display or os.environ.get("DISPLAY")
    return ["-e", f"DISPLAY={value}"] if value else []


def ready(name, assume_yes):
    """True when the container exists and is running, having offered to start
    it. Everything below needs that much."""
    exists = SYNC.container_exists(name)
    if exists is None:
        print("[ERROR] Could not reach the Docker daemon. Is it running, and "
              "is this user in the docker group?")
        return False
    if not exists:
        print(f"[ERROR] No container named '{name}'. Make it with "
              f"'python3 scripts/make_containers.py {name} --pull'.")
        return False
    if not SYNC.ensure_running(name, assume_yes):
        return False
    # Without this the working directory is set to a folder that is not
    # there, and docker answers with a raw OCI error naming config.json.
    root = CONTAINERS[name]["root"]
    if docker(["exec", name, "test", "-d", root],
              capture_output=True).returncode != 0:
        print(f"[ERROR] '{name}' has no {root}. An image built before the "
              f"root was renamed carries the old one, so rebuild it before "
              f"working in there.")
        return False
    return True


def published_port(name):
    """The host port the viewer port is mapped to, or None when it is not
    published. It cannot be added after creation, which is why serve says so
    rather than failing in the browser."""
    done = docker(["port", name, str(PORT)], capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    return done.stdout.strip().splitlines()[0].rsplit(":", 1)[-1]


def container_ip(name):
    """The container's own address, or None.

    Where the host routes to the container network, which is the normal Linux
    bridge, this reaches a port that was never published."""
    done = docker(["inspect", "-f",
                   "{{range .NetworkSettings.Networks}}{{.IPAddress}}"
                   "{{end}}", name], capture_output=True, text=True)
    address = done.stdout.strip() if done.returncode == 0 else ""
    return address or None


def viewer_url(name):
    """(url, published) for the viewer, or (None, False) when there is no way
    in. A published port is the portable answer and the container address is
    the fallback, so an unpublished port is not a dead end."""
    host = published_port(name)
    if host:
        return f"http://localhost:{host}/", True
    address = container_ip(name)
    if address:
        return f"http://{address}:{PORT}/", False
    return None, False


def server_pid(name):
    """The PID of a server already running inside, or None."""
    done = docker(["exec", name, "pgrep", "-f", SERVER],
                  capture_output=True, text=True)
    pids = done.stdout.split() if done.returncode == 0 else []
    return pids[0] if pids else None


def do_status(names):
    """One line per side: the container, its image and its viewer URL."""
    for name in sorted(names):
        state = MAKER.container_state(name)
        if state is None:
            print(f"  {name:5} no such container")
            continue
        if state != "running":
            print(f"  {name:5} {state}")
            continue
        done = docker(["inspect", "-f", "{{.Config.Image}}", name],
                      capture_output=True, text=True)
        image = done.stdout.strip() if done.returncode == 0 else "?"
        url, published = viewer_url(name)
        where = url or "no route to the viewer"
        if url and not published:
            where += " (not published)"
        served = " (serving)" if server_pid(name) else ""
        print(f"  {name:5} running   {image:28} {where}{served}")
    return 0


def do_shell(name, args):
    if not ready(name, args.yes):
        return 1
    if not sys.stdin.isatty():
        print("[ERROR] A shell needs a terminal. Use exec for a command.")
        return 1
    root = CONTAINERS[name]["root"]
    print(f"[INFO] {name}:{root}, 'exit' to come back", flush=True)
    return docker(["exec", "-it"] + display_args(args)
                  + ["-w", root, name, "bash"]).returncode


def do_exec(name, args, prefix=()):
    """Run a command inside, with the side's driver in front of it for run."""
    if not args.command:
        what = "run" if prefix else "exec"
        print(f"[ERROR] Nothing to run. Put the command after -- , as in "
              f"'{what} {name} -- --help'.")
        return 2
    if not ready(name, args.yes):
        return 1
    root = CONTAINERS[name]["root"]
    command = list(prefix) + list(args.command)
    print(f"[INFO] {name}:{root}$ " + " ".join(command), flush=True)
    if args.dry_run:
        return 0
    # A tty is only asked for where there is one at both ends, so piping the
    # output elsewhere does not put docker in interactive mode.
    flags = ["-i"] if sys.stdin.isatty() else []
    if flags and sys.stdout.isatty():
        flags.append("-t")
    return docker(["exec"] + flags + display_args(args)
                  + ["-w", root, name] + command).returncode


def do_serve(name, args):
    """Start the viewer server inside, and say where to open it."""
    if not ready(name, args.yes):
        return 1
    url, published = viewer_url(name)
    if url is None:
        print(f"[ERROR] '{name}' has no published port and no address, so "
              f"there is no way to reach the viewer. Remake it with "
              f"'python3 scripts/make_containers.py {name} --force', which "
              f"loses what is inside.")
        return 1
    if not published:
        print(f"[WARN] {name}: port {PORT} was never published, so this is "
              f"the container's own address. It works where the host routes "
              f"to the container network, and remaking it is not needed.")
    running_pid = server_pid(name)
    if running_pid:
        print(f"[INFO] {name}: already serving as PID {running_pid}")
        print(f"[INFO] Open {url}")
        return 0
    root = CONTAINERS[name]["root"]
    print(f"[INFO] {name}: starting {SERVER} in {root}")
    if args.dry_run:
        return 0
    code = docker(["exec", "-d", "-w", root, name,
                   "python3", SERVER]).returncode
    if code != 0:
        print(f"[ERROR] Could not start {SERVER} in '{name}'")
        return code
    print(f"[INFO] Open {url}")
    print(f"[INFO] 'docker_run.py exec {name} -- pkill -f {SERVER}' stops it")
    return 0


def do_stop(name, args):
    state = MAKER.container_state(name)
    if state is None:
        print(f"[INFO] No container named '{name}'")
        return 0
    if state != "running":
        print(f"[INFO] '{name}' is already {state}")
        return 0
    print(f"[INFO] Stopping '{name}'")
    if args.dry_run:
        return 0
    return docker(["stop", name], capture_output=True).returncode


# The verbs that act on one side at a time, and so reject being given both.
ONE_SIDED = ("shell", "run", "exec")


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage="%(prog)s ACTION [CONTAINER] [-y] [-n] [-- COMMAND ...]",
        description="Work inside the project's containers.",
        epilog="status  what is up, its image and its viewer URL\n"
               "shell   an interactive shell at the container root\n"
               "run     the side's driver, with what follows -- after it\n"
               "exec    a command as given, after --\n"
               "serve   start the viewer server and print its URL\n"
               "stop    stop the container\n"
               "\n"
               "shell, run and exec need one container. The rest default\n"
               "to both.")
    parser.add_argument("action",
                        choices=["status", "shell", "run", "exec", "serve",
                                 "stop"],
                        help="what to do")
    parser.add_argument("container", nargs="?", metavar="CONTAINER",
                        help=f"{' or '.join(sorted(CONTAINERS))}, or left out "
                             f"for both where that makes sense")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="do not ask before starting a stopped container")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="say what would run, run nothing")
    parser.add_argument("--display", metavar="VALUE",
                        help="DISPLAY to pass in, defaulting to the host's. "
                             "Docker Desktop wants host.docker.internal:0")
    parser.add_argument("--no-display", action="store_true",
                        help="do not pass a display in")
    # Split on -- before argparse sees it. A REMAINDER positional would take
    # this script's own flags too, so -n after the container name became an
    # argument for the command instead of a dry run.
    argv = sys.argv[1:]
    cut = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:cut])
    args.command = argv[cut + 1:]

    # One container is named CVA6 and the other gem5, so the case typed
    # at the prompt is not held against the reader.
    folded = {name.lower(): name for name in CONTAINERS}
    asked = folded.get(args.container.lower()) if args.container else None
    if args.container and asked is None:
        print(f"[ERROR] Unknown container '{args.container}'. "
              f"Use {' or '.join(sorted(CONTAINERS))}.")
        return 2
    names = [asked] if asked else sorted(CONTAINERS)

    if args.action in ONE_SIDED and not args.container:
        print(f"[ERROR] {args.action} needs one container, so name "
              f"{' or '.join(sorted(CONTAINERS))}.")
        return 2

    if args.action == "status":
        return do_status(names)
    if args.action == "shell":
        return do_shell(names[0], args)
    if args.action == "run":
        return do_exec(names[0], args, ("python3", DRIVERS[names[0]]))
    if args.action == "exec":
        return do_exec(names[0], args)

    worst = 0
    for name in names:
        code = do_serve(name, args) if args.action == "serve" \
            else do_stop(name, args)
        worst = worst or code
    return worst


if __name__ == "__main__":
    sys.exit(main())
