# badPolitics / LegisWatch

Evidence-first legislative monitoring and analysis.

## MVP-1
- Congress.gov bill ingestion
- version preservation + SHA-256 provenance
- section parsing
- deterministic review signals
- version diffing
- local OpenAI-compatible LLM deep dives

## MVP-2
- normalized actions
- sponsor/cosponsor records
- amendment records
- recently-updated federal bill polling
- GovInfo client scaffold
- bill timeline endpoint

## Start
Copy `.env.example` to `.env`, add your api.data.gov key, configure the local LLM endpoint, then:

```bash
docker compose up --build
```

Open `http://localhost:8000/docs`.

## Endpoints
```
POST /ingest/federal/{congress}/{bill_type}/{number}
POST /monitor/federal/{congress}?limit=50
GET  /bills
GET  /bills/{bill_id}/timeline
GET  /bills/{bill_id}/findings
GET  /bills/{bill_id}/diff/latest
POST /sections/{section_id}/deep-dive
```

The system extracts review signals and preserves evidence. It does not declare legislation corrupt or politically good/bad. AI explains evidence; source documents establish facts.
