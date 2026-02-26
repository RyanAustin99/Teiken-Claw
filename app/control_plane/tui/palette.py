"""Command palette provider and typed command descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from textual.command import DiscoveryHit, Hit, Provider


@dataclass(frozen=True)
class PaletteCommand:
    title: str
    group: str
    callback: Callable[[], None]
    help_text: str = ""
    key_hint: str = ""

    @property
    def display(self) -> str:
        hint = f" [{self.key_hint}]" if self.key_hint else ""
        return f"{self.group} > {self.title}{hint}"


class PaletteSource(Protocol):
    def get_palette_commands(self) -> Iterable[PaletteCommand]:
        """Return commands available for current UI context."""


class TeikenCommandProvider(Provider):
    """Global + screen-aware command provider for Ctrl+K palette."""

    async def discover(self):
        source = self.screen.app
        if not isinstance(source, PaletteSource):
            return
        for command in source.get_palette_commands():
            yield DiscoveryHit(command.display, command.callback, help=command.help_text)

    async def search(self, query: str):
        source = self.screen.app
        if not isinstance(source, PaletteSource):
            return
        matcher = self.matcher(query)
        for command in source.get_palette_commands():
            haystack = f"{command.group} {command.title} {command.help_text} {command.key_hint}".strip()
            score = max(matcher.match(command.title), matcher.match(haystack))
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(command.display),
                    command.callback,
                    help=command.help_text,
                )

