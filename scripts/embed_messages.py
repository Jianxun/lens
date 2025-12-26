#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import load_dotenv_file  # noqa: E402
from backend.embeddings.pipeline import EmbeddingConfig, run_embedding_job  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate turn-level embeddings into Postgres.")
    parser.add_argument(
        "--dsn",
        help="Postgres DSN (default: built from POSTGRES_* env vars).",
    )
    parser.add_argument(
        "--provider",
        default="supermind",
        help='Embedding provider label (default: "supermind").',
    )
    parser.add_argument(
        "--model",
        default="text-embedding-3-large",
        help='Embedding model name (default: "text-embedding-3-large").',
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of turns per batch (default: 32).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of assistant turns to process (default: unlimited).",
    )
    parser.add_argument(
        "--max-content-len",
        type=int,
        default=32000,
        help="Max characters for built embedding text before truncation (default: 32000).",
    )
    parser.add_argument(
        "--base-url",
        default="https://space.ai-builders.com/backend/v1",
        help="Base URL for student portal API (default: https://space.ai-builders.com/backend/v1).",
    )
    parser.add_argument(
        "--api-key-env",
        default="SUPER_MIND_API_KEY",
        help="Env var containing the API key (default: SUPER_MIND_API_KEY).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max HTTP retries (default: 3).",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="Backoff seconds multiplied by attempt number (default: 2.0).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed even if content_hash matches an existing row.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv_file()
    args = parse_args()
    cfg = EmbeddingConfig(
        dsn=args.dsn,
        provider=args.provider,
        model=args.model,
        batch_size=args.batch_size,
        max_content_len=args.max_content_len,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff,
        force=args.force,
    )
    try:
        stats = run_embedding_job(cfg, limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Embedding job failed: {exc}", file=sys.stderr)
        return 1
    print(
        {
            "embedded": stats.embedded,
            "skipped_existing_hash": stats.skipped_existing_hash,
            "batches": stats.batches,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

