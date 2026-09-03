#!/usr/bin/env python3
"""Serve the viewers over HTTP so they can be used from a container.

A container has no browser and no display. Serving the page and publishing the
port puts it in the host's browser while the trace and the JSON stay inside.
Serving also unblocks fetch, which the sample button and a JSON URL need.

    python3 serve_viewers.py                 # port 8000, this folder down
    python3 serve_viewers.py --port 9000
    python3 serve_viewers.py --root viewers

Start the container with the port published, or nothing outside it can connect:

    docker run -it --name gem5 -p 8000:8000 manuel313/gem5_v25 bash
    docker run -it --name cva6 -p 8000:8000 manuel313/cva6 bash
"""
import argparse
import functools
import http.server
import os
import socketserver
import sys

DEFAULT_PORT = 8000

# Only used to print the links, so a layout not listed here still serves.
VIEWER_PAGES = (
    "viewers/MinorFlow/MinorFlow.html",
    "viewers/CVA6Flow/CVA6Flow.html",
    "MinorFlow/MinorFlow.html",
    "CVA6Flow/CVA6Flow.html",
    "MinorFlow.html",
    "CVA6Flow.html",
)


class Handler(http.server.SimpleHTTPRequestHandler):
    """The stock handler, quieter, and without caching."""

    def log_message(self, fmt, *args):
        # One line per request, without the date the log already carries.
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        # A JSON is regenerated in place while the page is open.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(
        description="Serve the viewer pages and their JSONs over HTTP.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to listen on. Defaults to {DEFAULT_PORT}")
    parser.add_argument("--root", default=".",
                        help="Folder to serve. Defaults to the working "
                             "directory")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="Address to bind. Defaults to 0.0.0.0, which is "
                             "what a published container port needs")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"[ERROR] {root} is not a folder")
        return 2

    handler = functools.partial(Handler, directory=root)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = socketserver.TCPServer((args.bind, args.port), handler)
    except OSError as e:
        print(f"[ERROR] Could not listen on {args.bind}:{args.port}: {e}")
        print(f"[ERROR] Another server may already be running. "
              f"Try --port {args.port + 1}.")
        return 2

    print(f"[INFO] Serving {root} on http://localhost:{args.port}/")
    found = [p for p in VIEWER_PAGES if os.path.isfile(os.path.join(root, p))]
    if found:
        print("[INFO] Open one of these in the host's browser:")
        for page in found:
            print(f"           http://localhost:{args.port}/{page}")
    else:
        print("[WARN] No viewer page found under this root. Serve the folder "
              "holding MinorFlow.html or CVA6Flow.html, or pass --root.")
    print("[INFO] The port has to be published when the container starts: "
          "docker run -p "
          f"{args.port}:{args.port} ...")
    print("[INFO] Ctrl-C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
