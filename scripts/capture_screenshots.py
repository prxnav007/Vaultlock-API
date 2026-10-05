#!/usr/bin/env python
"""Capture the report's screenshots from the running application.

Every image here is a real page rendered against the real API and the real
generated dataset. The exemplar merchants come from `artifacts/exemplars.json`,
and each is scored at its own snapshot via `as_of` -- at the default `as_of`
(the end of the ledger) a genuine churner has been silent for months and is
correctly refused, so a capture without it would show a 409.

    .venv/bin/uvicorn app.main:app --port 8000
    python scripts/capture_screenshots.py

Writes PNGs into report/screenshots/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import config  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "report" / "screenshots"


def capture(host: str, scale: int) -> list[Path]:
    from playwright.sync_api import sync_playwright

    exemplars = json.loads(config.EXEMPLARS_PATH.read_text())
    high, low = exemplars["high_risk"], exemplars["low_risk"]
    written: list[Path] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 900}, device_scale_factor=scale
        )

        # --- Swagger: the interface the model is served through -------------
        page.goto(f"{host}/docs", wait_until="networkidle")
        page.wait_for_selector(".opblock", timeout=30_000)
        # Operations stay collapsed. Expanding each one unfolds a generated
        # schema panel and pushes the figure past nine thousand pixels, which
        # buries the thing the figure is for: the list of routes the service
        # actually exposes.
        # Drop the generated schema dump and the topbar: they add thousands of
        # pixels of boilerplate and say nothing about this project.
        page.evaluate(
            "document.querySelectorAll('section.models, .topbar, .information-container')"
            ".forEach(el => el.remove())"
        )
        page.wait_for_timeout(500)
        path = OUT_DIR / "fig_swagger_docs.png"
        page.locator(".swagger-ui .wrapper").first.screenshot(path=path)
        written.append(path)

        # --- The churn-risk response, executed through Swagger ---------------
        # Captured via "Try it out" rather than by visiting the URL directly:
        # the browser renders a raw response body as one unbroken line, while
        # this shows the pretty-printed body next to the request that produced
        # it, which is what makes the figure readable in print.
        page.goto(f"{host}/docs", wait_until="networkidle")
        page.wait_for_selector(".opblock", timeout=30_000)
        operation = page.locator("#operations-analytics-read_churn_risk").first
        if operation.count() == 0:
            operation = page.locator(".opblock", has_text="churn-risk").first
        operation.locator(".opblock-summary").click()
        page.wait_for_timeout(300)
        operation.locator("button.try-out__btn").click()
        operation.locator("input[placeholder='merchant_id']").fill(
            high["merchant_id"]
        )
        operation.locator("input[placeholder='as_of']").fill(high["snapshot_at"])
        operation.locator("button.execute").click()
        page.wait_for_selector(".responses-table .microlight", timeout=30_000)
        page.wait_for_timeout(800)
        # Just the live result: the request URL, the status code and the
        # pretty-printed body. The static response-schema documentation below
        # it is generated boilerplate and triples the height of the figure.
        path = OUT_DIR / "fig_churn_risk_json.png"
        operation.locator(".live-responses-table").first.screenshot(path=path)
        written.append(path)

        # --- The dashboard, both exemplars -----------------------------------
        for entry, name in ((high, "fig_dashboard_high_risk"), (low, "fig_dashboard_low_risk")):
            url = (
                f"{host}/dashboard?merchant={entry['merchant_id']}"
                f"&as_of={quote(entry['snapshot_at'])}"
            )
            page.goto(url, wait_until="networkidle")
            # The page scores on load; wait for the result, not just the DOM.
            page.wait_for_selector("#result:not(.hidden)", timeout=30_000)
            page.wait_for_timeout(500)
            band = page.inner_text("#band")
            score = page.inner_text("#score")
            print(f"  {name}: band={band} score={score}", file=sys.stderr)
            path = OUT_DIR / f"{name}.png"
            # The <main> element, not the page: a full-page shot pads the
            # figure with most of a viewport of empty background.
            page.locator("main").screenshot(path=path)
            written.append(path)

        browser.close()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument(
        "--scale", type=int, default=2, help="device scale factor; 2 for print"
    )
    args = parser.parse_args(argv)

    for path in capture(args.host, args.scale):
        print(f"wrote {path.relative_to(Path.cwd())} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
