#!/usr/bin/env python3
"""Export a contractor-ready print bundle PDF from Top1 SVG files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    from reportlab.graphics import renderPDF
    from reportlab.graphics.shapes import String
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from svglib.svglib import svg2rlg
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency. Install with: "
        "python -m pip install --user reportlab svglib"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "structured" / "candidates" / "svg" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "structured" / "candidates" / "print_bundle.pdf"
SCHEMA_VERSION = "layout-print-bundle-v1"
# Every room label in this project is Traditional Chinese, and Helvetica cannot
# draw a single one of those glyphs — so the fallback at the end of this list is
# not a graceful degradation, it is an unreadable PDF. The pipeline runs from
# both Windows PowerShell and WSL, hence the mounted /mnt/c paths and the native
# Linux entries: a WSL run used to find nothing here and silently produce a
# bundle with blank labels.
CJK_FONT_CANDIDATES = [
    {
        "regular_name": "MSJH",
        "regular_path": [Path(r"C:\Windows\Fonts\msjh.ttc"), Path("/mnt/c/Windows/Fonts/msjh.ttc")],
        "bold_name": "MSJH-Bold",
        "bold_path": [Path(r"C:\Windows\Fonts\msjhbd.ttc"), Path("/mnt/c/Windows/Fonts/msjhbd.ttc")],
    },
    {
        "regular_name": "NotoSansTC",
        "regular_path": [
            Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf"),
            Path("/mnt/c/Windows/Fonts/NotoSansTC-VF.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ],
        "bold_name": "NotoSansTC-Bold",
        "bold_path": [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        ],
    },
    {
        "regular_name": "MingLiu",
        "regular_path": [Path(r"C:\Windows\Fonts\mingliu.ttc"), Path("/mnt/c/Windows/Fonts/mingliu.ttc")],
        "bold_name": "MingLiu-Bold",
        "bold_path": [Path(r"C:\Windows\Fonts\mingliub.ttc"), Path("/mnt/c/Windows/Fonts/mingliub.ttc")],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a print-ready PDF bundle from exported SVG layouts."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Path to SVG manifest (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to output PDF (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--paper",
        choices=("a3", "a4"),
        default="a3",
        help="Paper size in landscape mode (default: a3).",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize(value: str) -> str:
    return " ".join((value or "").split())


def extract_floor_order(floor_id: str) -> int:
    match = re.search(r"(\d+)", floor_id or "")
    if match:
        return int(match.group(1))
    return 9999


def sort_exports(exports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        exports,
        key=lambda rec: (
            normalize(str(rec.get("building_id", ""))),
            extract_floor_order(str(rec.get("floor_id", ""))),
            normalize(str(rec.get("floor_id", ""))),
        ),
    )


def page_size(paper: str) -> tuple[float, float]:
    base = A3 if paper == "a3" else A4
    return landscape(base)


def register_font_if_needed(font_name: str, font_paths: Any) -> bool:
    """Register the first of ``font_paths`` that exists on this machine."""

    if not font_paths:
        return False
    if font_name in pdfmetrics.getRegisteredFontNames():
        return True
    if isinstance(font_paths, Path):
        font_paths = [font_paths]
    for font_path in font_paths:
        if not font_path or not font_path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        except Exception:
            # A .ttc collection reportlab cannot open is not fatal; try the next
            # location rather than losing CJK for the whole bundle.
            continue
        return True
    return False


def resolve_pdf_fonts() -> tuple[str, str]:
    for candidate in CJK_FONT_CANDIDATES:
        regular_name = candidate["regular_name"]
        if not register_font_if_needed(regular_name, candidate["regular_path"]):
            continue

        bold_name = candidate["bold_name"]
        if register_font_if_needed(bold_name, candidate["bold_path"]):
            return regular_name, bold_name
        return regular_name, regular_name

    # Say so loudly. Every label in this bundle is Traditional Chinese and
    # Helvetica has none of those glyphs, so the PDF is about to come out with
    # blank room names — a defect that is invisible in the exit code.
    print(
        "WARNING: no CJK font found; falling back to Helvetica. "
        "Chinese labels in the PDF will be blank or boxed.\n"
        "         Searched: "
        + ", ".join(
            str(p)
            for c in CJK_FONT_CANDIDATES
            for p in (c["regular_path"] if isinstance(c["regular_path"], list) else [c["regular_path"]])
        ),
        file=sys.stderr,
    )
    return "Helvetica", "Helvetica-Bold"


def drawing_set_font(node: Any, font_name: str) -> None:
    if isinstance(node, String):
        node.fontName = font_name
    if hasattr(node, "contents"):
        for child in node.contents:
            drawing_set_font(child, font_name)


def draw_cover(
    pdf: canvas.Canvas,
    page_height: float,
    exports: list[dict[str, Any]],
    output_file: Path,
    regular_font: str,
    bold_font: str,
) -> None:
    margin_x = 18 * mm
    y = page_height - 30 * mm

    pdf.setFont(bold_font, 26)
    pdf.drawString(margin_x, y, "Contractor Print Bundle")

    y -= 12 * mm
    pdf.setFont(regular_font, 14)
    pdf.drawString(margin_x, y, "Top-1 layout package for on-site printing")

    y -= 16 * mm
    pdf.setFont(regular_font, 11)
    pdf.drawString(margin_x, y, f"Generated: {now_iso()}")
    y -= 7 * mm
    pdf.drawString(margin_x, y, f"Total floor pages: {len(exports)}")
    y -= 7 * mm
    pdf.drawString(margin_x, y, f"Output: {output_file}")
    y -= 7 * mm
    pdf.drawString(margin_x, y, f"Schema: {SCHEMA_VERSION}")

    count_by_building = Counter(str(rec.get("building_id", "?")) for rec in exports)
    y -= 14 * mm
    pdf.setFont(bold_font, 12)
    pdf.drawString(margin_x, y, "Building Summary")
    y -= 8 * mm
    pdf.setFont(regular_font, 11)
    for building_id in sorted(count_by_building):
        pdf.drawString(
            margin_x,
            y,
            f"- Building {building_id}: {count_by_building[building_id]} floor pages",
        )
        y -= 7 * mm

    y -= 7 * mm
    pdf.setFont(bold_font, 12)
    pdf.drawString(margin_x, y, "Print Suggestion")
    y -= 8 * mm
    pdf.setFont(regular_font, 11)
    pdf.drawString(margin_x, y, "- A3 landscape, color print, fit to printable area")
    y -= 7 * mm
    pdf.drawString(margin_x, y, "- One floor per page for field discussion and markups")


def draw_toc(
    pdf: canvas.Canvas,
    page_height: float,
    exports: list[dict[str, Any]],
    regular_font: str,
    bold_font: str,
) -> None:
    margin_x = 18 * mm
    y = page_height - 24 * mm

    pdf.setFont(bold_font, 18)
    pdf.drawString(margin_x, y, "Table of Contents")

    y -= 10 * mm
    pdf.setFont(regular_font, 10)
    pdf.drawString(margin_x, y, "Pg  Building/Floor            Strategy       Score   File")
    y -= 4 * mm
    pdf.line(margin_x, y, margin_x + 240 * mm, y)

    y -= 6 * mm
    pdf.setFont(regular_font, 9)
    for idx, rec in enumerate(exports, start=1):
        page_no = idx + 2
        building = normalize(str(rec.get("building_id", "?")))
        floor_id = normalize(str(rec.get("floor_id", "?")))
        strategy = normalize(str(rec.get("strategy", "-")))
        score = float(rec.get("score_total", 0) or 0)
        file_name = normalize(str(rec.get("file", "")))
        label = f"{building}/{floor_id}"

        line = f"{page_no:>2}  {label:<24.24} {strategy:<13.13} {score:>6.2f}   {file_name}"
        pdf.drawString(margin_x, y, line)
        y -= 5.5 * mm
        if y < 18 * mm:
            break


def resolve_svg_path(manifest_dir: Path, rec: dict[str, Any]) -> Path:
    file_name = rec.get("file")
    if file_name:
        candidate = manifest_dir / str(file_name)
        if candidate.exists():
            return candidate

    raw_path = rec.get("path")
    if raw_path:
        candidate = Path(str(raw_path))
        if candidate.exists():
            return candidate

    return manifest_dir / str(file_name or "")


def load_svg_drawing(svg_path: Path, cjk_font_name: str) -> Any:
    raw = svg_path.read_text(encoding="utf-8")
    sanitized = raw.replace('fill="url(#bgGrad)"', 'fill="#0f1a2d"')
    sanitized = sanitized.replace('fill="url(#headerGrad)"', 'fill="#22395f"')
    drawing = svg2rlg(BytesIO(sanitized.encode("utf-8")))
    if drawing is not None and cjk_font_name:
        drawing_set_font(drawing, cjk_font_name)
    return drawing


def draw_svg_floor_page(
    pdf: canvas.Canvas,
    page_width: float,
    page_height: float,
    rec: dict[str, Any],
    svg_path: Path,
    page_index: int,
    total: int,
    regular_font: str,
    bold_font: str,
    cjk_font_name: str,
) -> None:
    margin_x = 12 * mm
    top_pad = 14 * mm
    header_h = 14 * mm
    bottom_pad = 10 * mm
    footer_h = 8 * mm

    building = normalize(str(rec.get("building_id", "?")))
    floor_id = normalize(str(rec.get("floor_id", "?")))
    title = normalize(str(rec.get("title", "")))
    strategy = normalize(str(rec.get("strategy", "-")))
    score = float(rec.get("score_total", 0) or 0)

    header = f"Building {building} | {floor_id} | Strategy: {strategy} | Score: {score:.2f}"

    pdf.setFont(bold_font, 12)
    pdf.drawString(margin_x, page_height - top_pad, header)
    if title:
        pdf.setFont(regular_font, 10)
        pdf.drawString(margin_x, page_height - top_pad - 5 * mm, title)

    drawing = load_svg_drawing(svg_path, cjk_font_name)
    if drawing is None:
        raise RuntimeError(f"Failed to parse SVG: {svg_path}")

    avail_w = page_width - 2 * margin_x
    avail_h = page_height - top_pad - header_h - bottom_pad - footer_h
    scale = min(avail_w / drawing.width, avail_h / drawing.height)

    render_w = drawing.width * scale
    render_h = drawing.height * scale
    render_x = (page_width - render_w) / 2
    render_y = bottom_pad + footer_h + (avail_h - render_h) / 2

    pdf.saveState()
    pdf.translate(render_x, render_y)
    pdf.scale(scale, scale)
    renderPDF.draw(drawing, pdf, 0, 0)
    pdf.restoreState()

    footer = f"Page {page_index + 2}/{total + 2} | {svg_path.name}"
    pdf.setFont(regular_font, 9)
    pdf.drawString(margin_x, 7 * mm, footer)


def draw_failed_page(
    pdf: canvas.Canvas,
    page_height: float,
    failures: list[dict[str, str]],
    regular_font: str,
    bold_font: str,
) -> None:
    margin_x = 18 * mm
    y = page_height - 24 * mm

    pdf.setFont(bold_font, 16)
    pdf.drawString(margin_x, y, "Failed Pages")
    y -= 10 * mm
    pdf.setFont(regular_font, 10)
    for item in failures:
        line = f"- {item['building_id']}/{item['floor_id']}: {item['reason']}"
        pdf.drawString(margin_x, y, line)
        y -= 6 * mm
        if y < 18 * mm:
            break


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    output_path = args.output.resolve()

    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exports = sort_exports(list(manifest.get("exports", [])))
    if not exports:
        raise SystemExit("No exports found in manifest.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = page_size(args.paper)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
    regular_font, bold_font = resolve_pdf_fonts()
    cjk_font_name = regular_font

    draw_cover(pdf, page_height, exports, output_path, regular_font, bold_font)
    pdf.showPage()
    draw_toc(pdf, page_height, exports, regular_font, bold_font)

    manifest_dir = manifest_path.parent
    failures: list[dict[str, str]] = []
    for idx, rec in enumerate(exports, start=1):
        pdf.showPage()
        svg_path = resolve_svg_path(manifest_dir, rec)
        try:
            draw_svg_floor_page(
                pdf,
                page_width,
                page_height,
                rec,
                svg_path,
                idx,
                len(exports),
                regular_font,
                bold_font,
                cjk_font_name,
            )
        except Exception as exc:  # pragma: no cover
            failures.append(
                {
                    "building_id": str(rec.get("building_id", "?")),
                    "floor_id": str(rec.get("floor_id", "?")),
                    "reason": str(exc),
                }
            )

    if failures:
        pdf.showPage()
        draw_failed_page(pdf, page_height, failures, regular_font, bold_font)

    pdf.save()

    print(f"PDF written: {output_path}")
    print(f"Floor pages: {len(exports)}")
    print(f"Failures:    {len(failures)}")
    print(f"Fonts:       regular={regular_font}, bold={bold_font}")


if __name__ == "__main__":
    main()
