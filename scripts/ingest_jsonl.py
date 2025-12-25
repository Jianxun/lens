#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ingest.pipeline import IngestConfig, ingest_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest ChatGPT JSONL dump into Postgres.")
    parser.add_argument("path", help="Path to conversations JSONL.")
    parser.add_argument(
        "--dsn",
        help="Postgres DSN (default: built from POSTGRES_* env vars).",
    )
    parser.add_argument(
        "--content-limit",
        type=int,
        default=32000,
        help="Max characters for content_text before truncation (default: 32000).",
    )
    parser.add_argument(
        "--turn-summary-limit",
        type=int,
        default=4000,
        help="Max characters for turn_summary before truncation (default: 4000).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = IngestConfig(
        dsn=args.dsn,
        content_limit=args.content_limit,
        turn_summary_limit=args.turn_summary_limit,
    )
    try:
        stats = ingest_jsonl(Path(args.path), config=config)
    except Exception as exc:  # noqa: BLE001
        print(f"Ingest failed: {exc}", file=sys.stderr)
        return 1

    print("Ingest succeeded.")
    print(stats.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

