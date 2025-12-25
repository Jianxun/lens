#!/usr/bin/env python3
"""
Stream-split a ChatGPT conversations export (array JSON) into JSONL.

Usage:
  python scripts/split_conversations_jsonl.py \
    --input data/chatgpt_dump/2025-12-23/conversations.json \
    --output data/chatgpt_dump/2025-12-23/conversations.jsonl

Defaults:
  - If --output is omitted, writes alongside the input as <name>.jsonl.
  - Refuses to overwrite unless --force is provided.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Generator, Any


def iter_json_array(path: str, chunk_size: int = 131_072) -> Generator[Any, None, None]:
    """
    Incrementally parse a top-level JSON array and yield each element.
    Avoids loading the entire file into memory.
    """
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as f:
        buffer = ""
        idx = 0

        # Load until we find the opening '['
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                raise ValueError("Input does not contain a JSON array.")
            buffer += chunk
            stripped = buffer.lstrip()
            trimmed = len(buffer) - len(stripped)
            buffer = stripped
            idx = max(idx - trimmed, 0)
            if buffer.startswith("["):
                idx = 1  # move past '['
                break

        while True:
            # Skip whitespace and commas between elements
            while idx < len(buffer) and buffer[idx] in " \r\n\t,":
                idx += 1

            # Ensure buffer has data
            while idx >= len(buffer):
                more = f.read(chunk_size)
                if not more:
                    break
                buffer += more

            # End of array
            if idx < len(buffer) and buffer[idx] == "]":
                break

            # Decode next element; if incomplete, pull more data
            while True:
                try:
                    obj, offset = decoder.raw_decode(buffer, idx)
                    yield obj
                    idx = offset
                    break
                except json.JSONDecodeError:
                    more = f.read(chunk_size)
                    if not more:
                        raise
                    buffer += more

            # Compact buffer occasionally to keep memory bounded
            if idx > chunk_size:
                buffer = buffer[idx:]
                idx = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a ChatGPT conversations JSON array into JSONL."
    )
    parser.add_argument("--input", required=True, help="Path to conversations.json")
    parser.add_argument(
        "--output",
        help="Output JSONL path (default: same as input with .jsonl extension)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=131_072,
        help="Chunk size in bytes for streaming decode (default: 128 KiB)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    in_path = args.input
    out_path = args.output or os.path.splitext(in_path)[0] + ".jsonl"

    if not os.path.exists(in_path):
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 1

    if os.path.exists(out_path) and not args.force:
        print(f"Refusing to overwrite existing file: {out_path}", file=sys.stderr)
        print("Use --force to override.", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    total = 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for obj in iter_json_array(in_path, chunk_size=args.chunk_size):
            out_f.write(json.dumps(obj, ensure_ascii=False))
            out_f.write("\n")
            total += 1

    print(f"Wrote {total} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

