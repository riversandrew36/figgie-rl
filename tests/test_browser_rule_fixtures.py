"""Keep the checked-in browser fixtures in sync with Python's official rules."""

import json
from pathlib import Path

from scripts.export_rule_fixtures import OUTPUT, build_fixtures


def test_official_browser_rule_fixtures_are_current() -> None:
    committed = json.loads(Path(OUTPUT).read_text(encoding="utf-8"))
    assert committed == build_fixtures()
