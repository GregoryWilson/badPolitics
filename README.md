# LegisWatch MVP-1

Evidence-first legislative monitoring. The MVP ingests U.S. federal bills from Congress.gov, preserves every text version, splits bills into sections, runs deterministic review rules, diffs versions, and can send a section plus its evidence to a local OpenAI-compatible LLM endpoint (Ollama/vLLM/etc.).

## Start

1. Copy `.env.example` to `.env` and add an `api.data.gov` key as `CONGRESS_API_KEY`.
2. If using Ollama, expose its OpenAI-compatible API and set `LLM_MODEL` to an installed model.
3. Run:

```bash
docker compose up --build
```

Open `http://localhost:8000/docs`.

## Example

```bash
curl -X POST http://localhost:8000/ingest/federal/119/hr/7567
curl http://localhost:8000/bills
curl http://localhost:8000/bills/1/findings
curl http://localhost:8000/bills/1/diff/latest
curl -X POST http://localhost:8000/sections/123/deep-dive
```

## Current deterministic signals

- explicit dollar amounts
- open-ended `such sums as may be necessary` authorizations
- retroactive language
- grandfathering/existing-arrangement language
- enforcement limitations
- exemptions / `notwithstanding` overrides
- narrow geographic terms
- dense statutory cross-references

These are *review signals*, not accusations or political ratings.

## Next milestones

MVP-2 should add: scheduled polling, normalized sponsor/action/amendment records, full GovInfo XML ingestion, semantic scope-mismatch detection, PostgreSQL/pgvector embeddings, FEC/LDA relationship sources, and a web dashboard.

MVP-3 should add jurisdiction adapters for Texas Legislature, counties, cities, school districts, and agenda/packet ingestion.

## Data principles

Every generated finding should retain the exact source text, source URL, bill version hash, and timestamps. AI analysis explains evidence; deterministic parsers and source records establish facts.
