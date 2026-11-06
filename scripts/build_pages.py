"""Stage only the packaged, browser-only arena for GitHub Pages."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path) -> None:
    source = ROOT / "figgie_rl" / "arena"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("figgie_play.html", "figgie_arena.css", "figgie_arena.js"):
        target = "index.html" if name.endswith(".html") else name
        shutil.copyfile(source / name, destination / target)


if __name__ == "__main__":
    build(ROOT / "_site" / "figgie-rl")
