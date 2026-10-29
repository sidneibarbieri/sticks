"""Exercise browser-state transitions without a browser or network."""

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


class TabMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tabs: list[dict[str, str | None]] = []
        self.panels: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("role") == "tab":
            self.tabs.append(attributes)
        elif attributes.get("role") == "tabpanel":
            self.panels.append(attributes)


def test_tabs_have_unique_bidirectional_panel_associations() -> None:
    markup = TabMarkup()
    root = Path(__file__).resolve().parents[1]
    markup.feed((root / "web/realization-workbench/index.html").read_text())
    assert len(markup.tabs) == len(markup.panels) == 5
    panels = {panel["id"]: panel for panel in markup.panels}
    assert len(panels) == 5
    assert len({tab["id"] for tab in markup.tabs}) == 5
    assert sum(tab["tabindex"] == "0" for tab in markup.tabs) == 1
    for tab in markup.tabs:
        panel = panels[tab["aria-controls"]]
        assert panel["aria-labelledby"] == tab["id"]
        assert panel["tabindex"] == "0"
        assert (tab["aria-selected"] == "true") == (tab["tabindex"] == "0")
        assert (tab["aria-selected"] == "false") == ("hidden" in panel)


def test_campaign_changes_invalidate_results_and_pending_requests() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the JavaScript state regression.")
    script = Path(__file__).parent / "workbench_state.cjs"
    completed = subprocess.run(
        [node, str(script)], capture_output=True, text=True, check=True
    )
    assert "workbench state regression passed" in completed.stdout
