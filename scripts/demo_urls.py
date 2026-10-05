#!/usr/bin/env python
"""Print the exact URLs to capture the report's screenshots.

The exemplars are pinned in `artifacts/exemplars.json`, and every URL carries
`as_of` set to the exemplar's own snapshot. That matters: at the default `as_of`
(the end of the ledger) a genuine churner has been silent for months and is
correctly refused, so a screenshot taken without `as_of` would show a 409
instead of the high-risk score the report describes.

Usage:
    python scripts/demo_urls.py [--host http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import quote

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from ml import config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost:8000")
    args = parser.parse_args(argv)

    if not config.EXEMPLARS_PATH.exists():
        raise SystemExit("no exemplars; run python -m ml.explain first")
    exemplars = json.loads(config.EXEMPLARS_PATH.read_text())
    metadata = json.loads(config.MODEL_METADATA_PATH.read_text())

    print(f"model {metadata['model_version']}  "
          f"threshold {metadata['classification_threshold']:.2f}  "
          f"bands MEDIUM>={metadata['risk_band_edges']['medium']:.2f} "
          f"HIGH>={metadata['risk_band_edges']['high']:.2f}\n")

    for which, expected in (("high_risk", "HIGH"), ("low_risk", "LOW")):
        entry = exemplars[which]
        as_of = quote(entry["snapshot_at"])
        print(f"--- {which}  (expect risk_band {expected}, "
              f"score about {entry['score_d']:.3f}) ---")
        print(f"merchant_id : {entry['merchant_id']}")
        print(f"snapshot    : {entry['snapshot_at']}")
        print(f"JSON        : {args.host}/merchants/{entry['merchant_id']}"
              f"/churn-risk?as_of={as_of}")
        print(f"dashboard   : {args.host}/dashboard"
              f"?merchant={entry['merchant_id']}&as_of={as_of}")
        print()

    print("Start the API first:")
    print("  .venv/bin/uvicorn app.main:app --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
