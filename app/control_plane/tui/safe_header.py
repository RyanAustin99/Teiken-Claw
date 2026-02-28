"""Compatibility wrapper for Textual header lifecycle edge-cases."""

from __future__ import annotations

from textual.css.query import NoMatches
from textual.dom import NoScreen
from textual.events import Mount
from textual.widgets import Header, Static
from textual.widgets._header import HeaderTitle


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


def _patch_textual_header_mount() -> None:
    """Patch Textual Header mount watcher to tolerate transient missing title nodes.

    Textual 8 can raise NoMatches from Header._on_mount watcher callbacks when
    screens switch quickly and HeaderTitle is already unmounted.
    """

    if getattr(Header, "_teiken_header_mount_patched", False):
        return

    def _safe_on_mount(self: Header, _: Mount) -> None:
        async def set_title() -> None:
            try:
                self.query_one(HeaderTitle).update(self.format_title())
            except (NoScreen, NoMatches):
                return

        self.watch(self.app, "title", set_title)
        self.watch(self.app, "sub_title", set_title)
        self.watch(self.screen, "title", set_title)
        self.watch(self.screen, "sub_title", set_title)

    Header._on_mount = _safe_on_mount  # type: ignore[assignment]
    setattr(Header, "_teiken_header_mount_patched", True)


_patch_textual_header_mount()
