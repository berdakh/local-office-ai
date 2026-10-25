"""Create a starter letterhead.docx for the pack so letters and guides render on day one.

Replace the output with the church's own Word letterhead when they have one.
Usage:
  uv run python scripts/make_letterhead.py --name "Grace Community Church" \
      --address "123 Main St, The Woodlands, TX 77380" --phone "(281) 555-0100" \
      --email office@example.org --website example.org
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.render import build_letterhead  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--address", default="")
    ap.add_argument("--phone", default="")
    ap.add_argument("--email", default="")
    ap.add_argument("--website", default="")
    ap.add_argument("--pack", default=os.environ.get("LOA_PACK", "church"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or REPO / "packs" / a.pack / "templates" / "letterhead.docx"
    build_letterhead(out, a.name, a.address, a.phone, a.email, a.website)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
