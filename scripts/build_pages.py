"""Stage only the packaged, browser-only arena for GitHub Pages."""

from pathlib import Path
import shutil
import runpy

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path) -> None:
    source = ROOT / "figgie_rl" / "arena"
    destination.mkdir(parents=True, exist_ok=True)
    # Read the static manifest by path so this script also runs before package install.
    names = runpy.run_path(str(source / "__init__.py"))["ARENA_ASSETS"]
    for name in names:
        target = destination / ("index.html" if name == "figgie_play.html" else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)


if __name__ == "__main__":
    build(ROOT / "_site" / "figgie-rl")
