"""Capture real Urwid canvases using live metrics, with host/IP/SSID identifiers redacted."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs/screenshots"


def capture():
    # Keep Pillow out of the monitored renderer process so its RSS is representative.
    import time

    from hctui import __version__
    from hctui.app import DEFAULT_WIDGET
    from hctui.metrics import MetricSampler
    from hctui.themes import THEMES
    from hctui.views.dialogs import DialogOverlay
    from hctui.views.main_view import MainView
    from hctui.widget_composer import WidgetComposer

    composer = WidgetComposer(DEFAULT_WIDGET)
    with MetricSampler() as sampler:
        sampler.configure(composer.intervals)
        view = MainView(sampler.record_render)
        view.set_pages(composer.page_names)
        for _ in range(7):
            started = time.perf_counter()
            context = sampler.sample(composer.sources)
            sampled = time.perf_counter()
            view.update(composer.update(context), 1000)
            view.widget.render((80, 24), focus=True)
            sampler.record_refresh(
                (sampled - started) * 1000, (time.perf_counter() - sampled) * 1000, 0
            )
            time.sleep(1)
        context = sampler.sample(composer.sources)
        system = context["system"]
        context["system"] = system._replace(
            hostname="demo-host",
            rows=tuple(
                (key, "demo-host" if key == "Host" else value) for key, value in system.rows
            ),
            addresses=tuple(
                (interface, f"192.0.2.{index + 10}")
                for index, (interface, _) in enumerate(system.addresses)
            ),
        )
        wifi = context["wifi"]
        context["wifi"] = wifi._replace(ssid="Example Wi-Fi" if wifi.ssid != "N/A" else "N/A")
        requests = [
            (index, (80, 24), name.lower()) for index, name in enumerate(composer.page_names)
        ]
        requests += [
            (0, (40, 12), "overview-small"),
            (5, (40, 12), "processes-small"),
            (1, (120, 32), "cpu-wide"),
        ]
        frames = []

        def record(widget, size, name, theme=0):
            canvas = widget.render(size, focus=True)
            rows = [
                [
                    (str(attribute) if attribute is not None else "body", segment.decode("utf-8"))
                    for attribute, charset, segment in row
                ]
                for row in canvas.content()
            ]
            frames.append({"name": name, "size": size, "rows": rows, "theme": theme})

        for index, size, name in requests:
            composer.select_page(index)
            view.set_pages(composer.page_names, index)
            view.update(composer.update(context), 1000)
            record(view.widget, size, name)
        composer.select_page(0)
        view.set_pages(composer.page_names)
        view.update(composer.update(context), 1000)
        for kind, size, name in [
            ("help", (80, 24), "help"),
            ("help", (40, 12), "help-small"),
            ("credits", (40, 12), "credits"),
            ("themes", (40, 12), "themes"),
        ]:
            record(DialogOverlay(view.widget, kind, lambda: None, THEMES), size, name)
        for index, theme in enumerate(THEMES):
            record(view.widget, (40, 12), "theme-" + theme["name"].lower().replace(" ", "-"), index)
        record(
            DialogOverlay(
                view.widget,
                "report",
                lambda: None,
                message="Report saved: /home/demo/reports/hctui-snapshot.html",
            ),
            (80, 24),
            "report",
        )
        print(json.dumps({"version": __version__, "frames": frames}))


def write_images(data, output_dir):
    from PIL import Image, ImageDraw, ImageFont
    from urwid import calc_width

    font_paths = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/mnt/c/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
    ]
    font_path = next((path for path in font_paths if path.exists()), None)
    if font_path is None:
        raise SystemExit("Install a DejaVu Sans Mono font to render screenshots")
    font = ImageFont.truetype(str(font_path), 16)
    cell_width = round(font.getlength("M"))
    cell_height = sum(font.getmetrics())
    from hctui.themes import THEMES, palette

    output_dir.mkdir(parents=True, exist_ok=True)
    for frame in data["frames"]:
        columns, height = frame["size"]
        theme = THEMES[frame.get("theme", 0)]
        colors = {entry[0]: (entry[4], entry[5]) for entry in palette(theme)}
        default = (theme["foreground"], theme["background"])
        picture = Image.new(
            "RGB", (columns * cell_width + 24, height * cell_height + 24), theme["background"]
        )
        draw = ImageDraw.Draw(picture)
        for index, row in enumerate(frame["rows"]):
            x, y = 12, 12 + index * cell_height
            for attribute, text in row:
                foreground, background = colors.get(attribute, default)
                width = calc_width(text, 0, len(text)) * cell_width
                draw.rectangle((x, y, x + width, y + cell_height), fill=background)
                # Terminal cells have integer widths. Drawing entire spans at the font's
                # fractional advance causes accumulating gaps at the right frame corners.
                cursor = x
                strokes = {
                    "─": "lr",
                    "│": "ud",
                    "┌": "rd",
                    "┐": "ld",
                    "└": "ru",
                    "┘": "lu",
                    "├": "urd",
                    "┤": "uld",
                    "┬": "lrd",
                    "┴": "lru",
                    "┼": "lrud",
                }
                for character in text:
                    advance = calc_width(character, 0, len(character)) * cell_width
                    if character in strokes:
                        center = (cursor + cell_width // 2, y + cell_height // 2)
                        ends = {
                            "l": (cursor, center[1]),
                            "r": (cursor + cell_width, center[1]),
                            "u": (center[0], y),
                            "d": (center[0], y + cell_height),
                        }
                        for direction in strokes[character]:
                            draw.line((center, ends[direction]), fill=foreground)
                    else:
                        draw.text((cursor, y), character, font=font, fill=foreground)
                    cursor += advance
                x += width
        path = output_dir / (frame["name"] + ".png")
        picture.save(path, optimize=True)
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump-canvas", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    arguments = parser.parse_args()
    if arguments.dump_canvas:
        capture()
    else:
        result = subprocess.run(
            [sys.executable, __file__, "--dump-canvas"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        write_images(json.loads(result.stdout), arguments.output)


if __name__ == "__main__":
    main()
