#!/usr/bin/env python
"""Swap the Chapter 6 chart images in the report for the regenerated ones.

The figures keep their position, caption and display width; only the picture
bytes change, with the height recomputed from the new aspect ratio so nothing
is stretched. Figures outside Chapter 6 are not touched.

    python scripts/replace_figures.py --list
    python scripts/replace_figures.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "report"

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# caption prefix -> regenerated image
REPLACEMENTS = {
    "Figure 6.1": "fig_class_balance.png",
    "Figure 6.2": "fig_pr_curves.png",
    "Figure 6.3": "fig_confusion_matrix.png",
    "Figure 6.4": "fig_shap_beeswarm.png",
    "Figure 6.5": "fig_shap_waterfall.png",
}


def is_caption(paragraph, text: str) -> bool:
    """Distinguish a figure caption from prose that merely cites the figure.

    Body text like "Figure 6.4 is the SHAP beeswarm over the test split..."
    starts with the same words as the caption, and matching it would swap the
    picture belonging to the *previous* figure. Captions are centred, bold and
    short; running text is none of those.
    """
    if paragraph.alignment != WD_ALIGN_PARAGRAPH.CENTER:
        return False
    if len(text) > 110:
        return False
    return any(run.bold for run in paragraph.runs if run.text.strip())


def picture_paragraph(paragraphs, caption_index: int):
    """The nearest paragraph above a caption that actually holds a picture."""
    for i in range(caption_index - 1, max(caption_index - 4, -1), -1):
        if paragraphs[i]._element.findall(f".//{A}blip"):
            return paragraphs[i]
    return None


def swap(document, paragraph, image: Path) -> tuple[float, float]:
    """Replace the picture's bytes and resize to the new aspect ratio."""
    blip = paragraph._element.findall(f".//{A}blip")[0]
    rid = blip.get(f"{R}embed")
    part = document.part.related_parts[rid]
    part._blob = image.read_bytes()

    width_px, height_px = Image.open(image).size
    aspect = height_px / width_px

    # Keep the width the document already uses; derive the height from it.
    extent = paragraph._element.findall(f".//{WP}extent")[0]
    cx = int(extent.get("cx"))
    cy = int(round(cx * aspect))
    extent.set("cy", str(cy))
    for ext in paragraph._element.findall(f".//{A}ext"):
        ext.set("cx", str(cx))
        ext.set("cy", str(cy))
    return Emu(cx).inches, Emu(cy).inches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", default=str(ROOT / "vault_api_PBL_report.docx"))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.docx)
    document = Document(str(path))
    paragraphs = document.paragraphs

    targets = []
    for i, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if not is_caption(paragraph, text):
            continue
        for prefix, image in REPLACEMENTS.items():
            if text.startswith(prefix):
                holder = picture_paragraph(paragraphs, i)
                targets.append((prefix, image, holder, text))

    if args.list:
        for prefix, image, holder, text in targets:
            state = "found picture" if holder is not None else "NO PICTURE FOUND"
            print(f"{prefix}: {state}  <- {image}\n    {text[:70]}")
        return 0

    missing = [i for _, i, _, _ in targets if not (FIGURES / i).exists()]
    if missing:
        raise SystemExit(f"missing regenerated charts: {missing}")

    shutil.copy2(path, path.with_suffix(".docx.bak"))
    for prefix, image, holder, _ in targets:
        if holder is None:
            print(f"  ! {prefix}: no picture found above the caption", file=sys.stderr)
            continue
        w, h = swap(document, holder, FIGURES / image)
        print(f"  replaced {prefix}  <- {image}  ({w:.2f} x {h:.2f} in)")

    document.save(str(path))
    print(f"\nsaved {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
