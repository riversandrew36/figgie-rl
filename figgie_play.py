"""Serve the standalone Figgie Bot Arena locally."""

from __future__ import annotations

import argparse
import atexit
import functools
import http.server
import shutil
import tempfile
import webbrowser
from importlib.resources import as_file, files
from pathlib import Path

from figgie_rl.arena import ARENA_ASSETS


def _as_directory(root: object) -> Path | None:
    if isinstance(root, Path):
        return root if root.is_dir() else None
    try:
        candidate = Path(str(root))
    except (TypeError, ValueError):
        return None
    return candidate if candidate.is_dir() else None


def arena_directory() -> Path:
    """Locate the packaged arena assets.

    Wheel installs and editable installs both expose the HTML, CSS, and JS
    through importlib.resources. When those resources are already real files,
    the package directory is used directly. Otherwise the three assets are
    copied into a temporary directory that lives until the process exits.
    """
    root = files("figgie_rl.arena")
    candidate = _as_directory(root)
    if candidate is not None and all((candidate / name).is_file() for name in ARENA_ASSETS):
        return candidate

    temp_dir = Path(tempfile.mkdtemp(prefix="figgie-arena-"))
    atexit.register(shutil.rmtree, temp_dir, True)
    missing: list[str] = []
    for name in ARENA_ASSETS:
        resource = root.joinpath(name)
        if not resource.is_file():
            missing.append(name)
            continue
        with as_file(resource) as source:
            shutil.copy(source, temp_dir / name)
    if missing:
        raise FileNotFoundError(
            "Figgie arena assets are not installed: " + ", ".join(missing)
        )
    return temp_dir


def make_server(host: str, port: int) -> http.server.ThreadingHTTPServer:
    directory = str(arena_directory())
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    return http.server.ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Figgie Bot Arena.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the arena in a browser.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}/figgie_play.html"
    print(f"Figgie Bot Arena: {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
