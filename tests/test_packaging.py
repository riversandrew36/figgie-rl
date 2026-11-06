"""Packaging checks for the browser arena assets."""

from __future__ import annotations

import os
import shutil
import threading
import time
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from figgie_play import ARENA_ASSETS, arena_directory, make_server

ROOT = Path(__file__).resolve().parents[1]


def test_arena_directory_serves_packaged_files() -> None:
    root = arena_directory()
    assert root.name == "arena"
    assert not (root / "pyproject.toml").exists()
    html = (root / "figgie_play.html").read_text(encoding="utf-8")
    assert "figgie_arena.css" in html
    assert "figgie_arena.js" in html
    for name in ARENA_ASSETS:
        path = root / name
        assert path.is_file()
        assert path.stat().st_size > 0


def test_pyproject_lists_arena_package_data() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ARENA_ASSETS:
        assert name in text


def test_arena_server_returns_assets() -> None:
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        for name in ARENA_ASSETS:
            body = _fetch(f"http://{host}:{port}/{name}")
            assert body
        html = _fetch(f"http://{host}:{port}/figgie_play.html").decode("utf-8")
        assert "figgie_arena.css" in html
        assert "figgie_arena.js" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_wheel_includes_arena_assets(tmp_path: Path) -> None:
    from setuptools.build_meta import build_wheel

    before_eggs = set(ROOT.glob("*.egg-info"))
    before_build = (ROOT / "build").exists()
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        wheel_name = build_wheel(str(tmp_path))
    finally:
        os.chdir(previous)
        if not before_build and (ROOT / "build").exists():
            shutil.rmtree(ROOT / "build")
        for egg in set(ROOT.glob("*.egg-info")) - before_eggs:
            shutil.rmtree(egg)

    with zipfile.ZipFile(tmp_path / wheel_name) as archive:
        names = set(archive.namelist())
    for name in ARENA_ASSETS:
        assert f"figgie_rl/arena/{name}" in names
    assert "figgie_play.py" in names
    assert not any(name.startswith("artifacts/") for name in names)


def _fetch(url: str) -> bytes:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with urlopen(url, timeout=2) as response:
                assert response.status == 200
                return response.read()
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            time.sleep(0.05)
    raise AssertionError(f"failed to fetch {url}: {last_error}")
