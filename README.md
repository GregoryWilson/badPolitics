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

## MVP-3A
- evidence entities with stable normalized identity
- bill-to-entity links with exact supporting text
- conservative beneficiary-class extraction
- named-geography extraction
- sponsor/cosponsor entities from Congress.gov
- source-backed entity-to-entity relationships
- one-hop conflict/relationship graph API
- automatic graph sync during bill ingestion

### Evidence semantics

A graph edge is not an accusation. Each edge stores its evidence, source URL, source system, extraction method, and confidence. Deterministic text matches are review leads; official records and imported external datasets can carry higher-confidence relationships.

## MVP-3B
- objective bill metrics instead of political quality scores
- explicit dollar amount counts and sum-of-mentions (not a fiscal score)
- exemptions, retroactivity, grandfathering, enforcement-limit counts
- named geography and beneficiary-class counts
- sponsor/cosponsor/amendment counts
- latest-version change magnitude

## MVP-4
- OpenFEC candidate/committee adapter
- FEC Schedule A receipt importer
- LDA.gov LD-1/LD-2 filing adapter
- raw external evidence record preservation
- explicit source URLs and record identifiers
- bounded two-hop relationship traversal for bill graphs
- no automatic fuzzy matching of politicians to external records

### External evidence semantics

FEC and LDA imports preserve the source record separately from graph relationships. A contribution or lobbying filing establishes the reported transaction/relationship in that filing; it does not establish legislative motive or improper conduct.

LDA.gov permits anonymous API use at a lower rate limit. Its terms require downstream users to make clear that the Senate Office of Public Records cannot vouch for analyses after the data are retrieved.

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
POST /bills/{bill_id}/graph/sync
GET  /bills/{bill_id}/graph
GET  /bills/{bill_id}/metrics
POST /graph/entities
GET  /graph/entities/{entity_id}
POST /graph/relationships
POST /evidence/fec/candidate
POST /evidence/fec/receipts
POST /evidence/lda/client
GET  /evidence/records
```

The system extracts review signals and preserves evidence. It does not declare legislation corrupt or politically good/bad. AI explains evidence; source documents establish facts.
