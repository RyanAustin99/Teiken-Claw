from __future__ import annotations

from pathlib import Path

from rich.text import Text

FILL = set("█▇▆▅▄▃▂▁▌▐▀")
OUTLINE = set("┌┐└┘─│├┤┬┴┼╭╮╰╯")


def _banner_path() -> Path:
    return Path(__file__).parent / "assets" / "banner_teiken_claw.txt"


def load_banner_lines() -> list[str]:
    return _banner_path().read_text(encoding="utf-8").splitlines()


def render_banner_frame(lines: list[str], tick: int) -> Text:
    max_w = max((len(line) for line in lines), default=0)
    # Complete left->right sweep roughly every 2 seconds at 12fps.
    cycle = 24
    progress = (tick % cycle) / float(max(1, cycle - 1))
    band_center = int(progress * (max_w + 6)) - 3

    text = Text(no_wrap=True, overflow="ignore")
    for line in lines:
        for col, ch in enumerate(line):
            style = None
            if ch in FILL:
                dist = abs(col - band_center)
                if dist <= 0:
                    style = "bold white"
                elif dist <= 1:
                    style = "bold #5EF0D4"
                elif dist <= 2:
                    style = "bold #24E5C6"
                else:
                    style = "#00D1B2"
            elif ch in OUTLINE:
                style = "dim #00D1B2"
            text.append(ch, style=style)
        text.append("\n")
    return text

