"""Compatibility wrapper for Textual header lifecycle edge-cases."""

from __future__ import annotations

from textual.css.query import NoMatches
from textual.dom import NoScreen
from textual.events import Mount
from textual.widgets import Header, Static


class SafeHeader(Header):
    """Header that tolerates transient missing title nodes during mount/unmount."""

    def _update_title(self) -> None:
        try:
            title_node = self.query_one("HeaderTitle", Static)
        except NoMatches:
            return

        try:
            title_node.update(self.format_title())
        except NoScreen:
            return

    def _on_mount(self, _: Mount) -> None:
        self.watch(self.app, "title", self._update_title)
        self.watch(self.app, "sub_title", self._update_title)
        self.watch(self.screen, "title", self._update_title)
        self.watch(self.screen, "sub_title", self._update_title)
        self.call_after_refresh(self._update_title)
