# ADR-0008: API key handling and environment loading
Status: Accepted  
Date: 2025-12-26

## Context
- Multiple services (embeddings via Supermind, chat orchestration via OpenAI, future providers) require API keys.
- Executors were relying on long `SUPER_MIND_API_KEY=... POSTGRES_PORT=... uvicorn ...` commands to pass secrets into the backend, which was error-prone and easy to forget.
- A repo-level `.env` file already exists for local defaults, but there was no deterministic way to ensure the backend loaded it, nor any documented precedence rules.
- We need a consistent rule set that works locally (no secret manager) while still aligning with production practices (env vars injected by deployment tooling).

## Decision
- **Source of truth**: All credentials (API keys, tokens, DSNs) are provided via environment variables. Application code must never read secrets from config files, command-line flags, or checked-in JSON/YAML.
- **Local convenience**: The backend automatically calls `backend.config.load_dotenv_file()` at import time. It loads `${repo}/.env` using `python-dotenv` but does **not** override variables that are already defined in the shell. This allows devs to keep `.env` for defaults while letting per-shell overrides win.
- **Production / CI**: Deployments and automation continue to set env vars directly (Kubernetes secrets, GitHub Actions, etc.). They SHOULD NOT rely on `.env` files, and `.env` must never contain production credentials.
- **Key rotation**: `.env` values are considered disposable development tokens. Rotating a key only requires updating environment variables (and optionally `.env` for dev). No code changes are needed.
- **Scope**: Any component that needs secrets (FastAPI backend, ingest/embedding scripts, future workers) imports `backend.config.load_dotenv_file()` or equivalent so behavior stays consistent.

## Consequences
- Local developers can simply run `uvicorn backend.main:app --reload` (or scripts) as long as `.env` contains the expected keys, reducing 500 errors like “Embedding client not configured.”
- Enforcing env-vars-only configuration keeps secrets out of code and enables deployment platforms to manage them securely.
- Because `.env` is loaded automatically, we must ensure real production secrets are never added to the repo; reviewers should treat `.env` changes carefully.

## Alternatives
- **Manual exports**: Keep instructions that require `export SUPER_MIND_API_KEY=...` each time. Rejected because it causes frequent failures and noisy launch commands.
- **Config files per environment**: Introduce YAML/JSON config readers. Rejected because they add complexity, risk accidental commits, and do not align with how most hosting providers surface secrets.
