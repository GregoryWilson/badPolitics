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

## MVP-5
- deterministic correlation between bill entities and imported external evidence
- identifier-backed matches
- normalized exact-name matches
- explicitly stored alias matches
- persistent correlation findings with confidence and evidence
- no fuzzy string matching and no motive inference

### Correlation semantics

Correlation means two records appear to refer to the same entity based on a documented identifier, exact normalized name, or explicitly stored alias. A correlation does not establish influence, causation, conflict of interest, or wrongdoing.

## MVP-6
- persisted research runs with step-level audit trail
- deterministic source selection by entity type and verified identifiers
- verified FEC candidate-ID research
- exact-name LDA client research
- explicit completed/no-match/skipped/failed outcomes
- automatic post-import correlation
- reproducible investigation packets

### Research orchestration semantics

Automatic research is deliberately conservative. A person is queried against FEC only when a verified FEC candidate ID is already attached. An organization is queried against LDA only when it was explicitly named in bill text, and only exact normalized client-name matches are retained. Ambiguous cases are skipped rather than guessed.

## MVP-7
- persisted investigation reports
- structured finding categories
- exact bill-section/source provenance
- external correlation provenance
- research-run audit context
- objective metrics embedded in the report
- explicit caveats and interpretation boundaries
- no aggregate political/corruption score

### Report semantics

Reports separate factual source records, deterministic review signals, correlations, and caveats. A report can identify reported campaign-finance relationships, lobbying records, narrow beneficiaries, exemptions, retroactivity, spending language, and other review-worthy facts without concluding that a political actor acted improperly.

## MVP-8
- local dashboard served directly by FastAPI
- searchable bill watchlist
- neutral objective metric cards
- deterministic finding drill-down
- sponsor/action/amendment timeline
- latest version diff viewer
- evidence graph viewer
- one-click conservative research run
- one-click investigation report generation
- source-link protocol hardening

## MVP-9
- persisted bill and Congress watch rules
- scan history with completed/failed status
- deduplicated change events for new bill versions, actions, amendments, and newly discovered bills
- optional automatic research/report refresh when watched bills change
- manual scan-all endpoint
- opt-in in-process polling loop via `WATCH_POLL_MINUTES`
- dashboard Watch Bill / Scan Watches controls
- recent-change feed with bill drill-down

### Monitoring semantics

Monitoring records that a legislative source changed; it does not interpret the political significance of that change. Background polling is disabled by default. Set `WATCH_POLL_MINUTES` to a positive integer to enable periodic scans while the application is running.

## MVP-10
- normalized jurisdiction adapter contract
- adapter registry with federal (US) and Texas (TX) implementations
- unified ingestion pipeline across jurisdictions
- Texas Legislature Online bulk FTP bill-history XML adapter
- official Texas bill-text HTML retrieval
- Texas actions, authors/coauthors, sponsors/cosponsors, subjects, and text versions
- jurisdiction-aware bill watches
- jurisdiction/session identity in API, metrics, reports, and dashboard
- fixture-based Texas parser tests with no live-network CI dependency

### Texas source semantics

Texas Legislature Online asks legislative data services to use its bulk FTP files rather than data-mine the public website. The TX adapter follows that model: bill-history XML is read from `ftp.legis.state.tx.us`, while bill text uses the official TLO HTML URLs embedded in the XML. TLO states that bulk data is subject to revision and is not a substitute for official versions.

Texas MVP-10 supports direct bill ingestion and bill-level watches. Session-wide Texas discovery is intentionally deferred until the adapter gains a bounded update-index reader.

## MVP-11
- bounded Texas session discovery from TLO `billhistory/history.xml`
- optional bounded ingest of discovered/updated Texas bills
- fiscal notes and bill analyses persisted as first-class legislative documents
- HTML document text capture when available; PDF-only sources preserved by URL
- document-aware bill watches and change events
- Texas session-level watch rules
- dashboard Documents tab
- dashboard Watch Session control for non-federal jurisdictions
- investigation reports include supporting-document provenance

### Texas discovery semantics

Texas session discovery reads the official TLO `billhistory/history.xml` update index and processes only the configured bounded result count. It does not crawl the TLO public search UI. Session watches ingest that bounded set, then emit events only for newly stored bill versions, actions, supporting documents, or newly created bills.

A fiscal note or bill analysis is treated as source material, not as a negative finding by itself.

## MVP-12
- deterministic fiscal-impact signals across bill text, fiscal notes, and bill analyses
- appropriation and dedicated-fund detection
- tax-credit/exemption/rate-change detection
- fee/surcharge/assessment change detection
- required-government implementation signals
- implementation-cost and revenue-effect signals
- defined-recipient funding/benefit signals
- bill-text versus bill-analysis scope comparison
- fiscal-note versus bill-text amount comparison
- persisted comparative findings with provenance and confidence
- fiscal review API, report integration, and dashboard tab

### Fiscal comparison semantics

Fiscal and document-comparison findings are review signals, not conclusions about intent. A bill-analysis scope gap means the deterministic subject signal found in bill text was not explicitly detected in that analysis text. It does not establish concealment or inaccuracy. Likewise, a larger amount in a fiscal note may reflect implementation cost, revenue effects, or accounting context rather than spending directly appropriated by the bill.

## MVP-13
- persisted provision lineage across stored bill-text versions
- introduced / modified / removed / renumbered section events
- section-level unified diffs and similarity
- candidate amendment association requiring descriptive text overlap, with version-date proximity strengthening confidence
- amendment sponsor/offerer names preserved when present in source metadata
- report findings for provisions added or modified after initial text
- provision-lineage API and dashboard tab

### Lineage and amendment-attribution semantics

Provision lineage is a version-history fact: it records when a section appears, changes, or disappears across stored bill versions. Amendment attribution is deliberately conservative. Unless an authoritative source directly identifies an amendment as the source of a change, the application labels the relationship as a candidate association. Date proximity alone is not enough to create an amendment association. Descriptive text overlap can create a candidate lead, and temporal proximity can strengthen it; neither establishes authorship, intent, or responsibility.

## MVP-14
- explainable semantic scope analysis across bill sections
- TF-IDF-style token weighting with no external ML dependency
- comparison against stated bill scope from title and available subject metadata
- comparison against the dominant vocabulary of peer sections
- persisted scope findings with anchor similarity, peer similarity, confidence, and divergent terms
- stronger `late_scope_outlier` classification when a later-added provision is also semantically distant
- report integration and dashboard Scope Review tab

### Scope-mismatch semantics

A scope outlier means a section is unusually distant from both the bill's stated scope and the dominant subject matter of the other eligible sections. It is a review lead, not a conclusion that the provision is an improper rider. Omnibus legislation, cross-cutting implementation language, and specialized technical provisions can produce legitimate outliers.

The analyzer requires at least four substantive sections and uses relative peer similarity so short or heterogeneous bills are less likely to be over-flagged.

## MVP-15
- persisted provision-level cross-source evidence packets
- section text and deterministic findings with evidence IDs
- scope-outlier and provision-lineage context
- candidate amendment associations
- named entities / beneficiary classes tied to the section
- external correlation and relationship context tied to section entities, including FEC/LDA where imported
- bill-level fiscal/document signals clearly marked as non-section-specific context
- stable packet hashing that ignores volatile internal database IDs
- opt-in local-LLM synthesis constrained to packet evidence
- citation audit rejects unknown evidence IDs and uncited narratives
- investigation-report packet references
- dashboard Evidence Packets tab with explicit Generate Local Synthesis action

### Evidence-packet synthesis semantics

Evidence packets are reproducible bundles of source-backed records and deterministic review signals. Packet creation does not require an LLM. Local synthesis is opt-in and receives only the packet evidence. The prompt prohibits motive, causation, authorship, corruption, or conflict conclusions unless an evidence record explicitly establishes the fact. Candidate amendment associations and external correlations remain leads rather than proof.

Bill-level fiscal context is labeled as bill-level and must not be attributed to a specific section merely because it appears in that section's packet.

## MVP-16
- persisted provision-level investigation queue
- packet-driven trigger tags without political quality scoring
- evidence coverage checklist and explicit provenance gaps
- analyst workflow states: new, reviewing, needs evidence, completed, archived
- superseded historical queue records when packet evidence changes
- analyst notes stored separately from evidence packets
- bill-level queue sync API and global queue list/summary APIs
- changed watched bills automatically attempt queue refresh
- queue refresh failures are recorded without failing legislative monitoring
- global dashboard Investigation Queue with status filtering
- bill-level Triage tab with editable status and analyst notes

### Investigation-queue semantics

The queue is an analyst workflow surface, not a political ranking system. Queue position, trigger count, evidence coverage, evidence gaps, and workflow status describe what information is available and what review work remains. They do not state that a bill, provision, sponsor, amendment, or external relationship is good, bad, improper, corrupt, or more important than another.

A changed evidence packet creates a new queue record and active older records are marked `superseded` rather than overwritten, preserving the analyst audit trail.

## MVP-17
- Alembic migration framework with a frozen MVP-16 baseline revision
- separate hot-path index revision for queue/evidence growth
- application startup no longer creates or mutates schema with `Base.metadata.create_all()`
- strict schema-revision check before background monitoring starts
- Docker startup runs `alembic upgrade head`
- guarded legacy-schema adoption for pre-Alembic databases
- legacy adoption validates every expected table and column before stamping
- incomplete legacy schemas are refused rather than silently marked current
- migration regression tests cover fresh databases and legacy adoption
- CI runs `alembic upgrade head`, `alembic check`, and the application schema check

### Database migration and legacy adoption

Fresh databases are created through Alembic:

```bash
alembic upgrade head
```

Databases created by releases before MVP-17 do not have an `alembic_version` table. Before starting the new container against an existing persistent database, run the guarded adoption command once:

```bash
python -m app.db.migrate adopt-legacy
```

For Docker Compose with an existing database volume:

```bash
docker compose run --rm api python -m app.db.migrate adopt-legacy
docker compose up --build
```

The adoption command verifies that all MVP-16 tables and required columns exist before stamping revision `0001`; it then applies managed migrations through `head`. If the schema is incomplete, adoption stops and reports the missing tables/columns instead of stamping the database.

After MVP-17, all schema changes should be represented by Alembic revisions. `Base.metadata.create_all()` is no longer an application schema-management mechanism.

## MVP-18
- automatic background discovery enabled by default
- resumable federal Congress-wide bill cursor
- pageable full-session Texas TLO bill-history discovery
- persistent discovery cursor/status/error state
- repeated discovery cycles for incremental self-healing after initial bootstrap
- local civic-document crawler with revision history
- PDF text extraction for agendas, packets, minutes, policies, and attachments
- GISD Board of Trustees / BoardBook monitoring
- GISD bond, campus consolidation, and policy monitoring
- Wylie ISD BoardBook/agenda monitoring
- City of Wylie structured development/P&Z project ingestion from official ArcGIS services
- Collin County Commissioners Court/eAgenda monitoring
- dashboard discovery progress and recent civic records
- manual discovery/status/civic-document APIs

### Automatic discovery semantics

When `AUTO_DISCOVERY_ENABLED=true`, the application starts a background discovery loop after database migration validation. Legislative discovery is resumable: federal and Texas source cursors advance in bounded batches and persist their offsets in the database. Reaching the end of a source starts a new cycle from the beginning, allowing later cycles to pick up records that moved because of source-side update ordering.

The default federal corpus is the 119th Congress and the default Texas corpus is the 89th Regular Session. These are configurable with `AUTO_DISCOVERY_US_CONGRESS` and `AUTO_DISCOVERY_TX_SESSIONS`.

Local civic discovery preserves the source document URL and extracted text. If an agenda, packet, policy page, meeting record, or structured development record changes, a new `CivicDocumentRevision` is stored rather than overwriting history.

GISD is intentionally treated as a high-priority local source. Current roots include Board of Trustees/BoardBook materials, Bond 2023, campus consolidation, and district policies. City of Sachse is also high priority, including City Council/P&Z, EDC/MDD/TIRZ, public hearings, legal notices, planned developments, development reports, permits, resolutions, and elections. Dallas County high-priority sources include Commissioners Court, the Commissioners Court Clerk, court orders/contracts/meeting records, and county budget materials. Wylie ISD, City of Wylie development/P&Z data, and Collin County Commissioners Court records are also included.

Automatic discovery records source material and changes; it does not assign political importance, motive, or wrongdoing.

## MVP-19
- deterministic local civic analysis for discovered municipal, county, and school-board records
- structured agenda/action-item extraction from official source text
- review signals for zoning/development, procurement/contracts, budgets/finance, bonds/taxes/debt, school facilities/boundaries, policy/rules, hearings, votes/actions, land/property, and elections/governance
- explicit monetary-mention extraction with exact source evidence
- civic document revision diffs preserved as a distinct change signal
- deterministic named-organization/vendor/developer extraction linked into the shared evidence-entity graph
- automatic analysis of newly changed civic records
- idempotent backfill analysis for civic records captured before MVP-19
- civic analysis APIs and dedicated dashboard Civic Review workspace

### Civic analysis semantics

Civic analysis is evidence-first and deterministic. Findings indicate that explicit source text matched a documented category or that a captured source revision changed. A category match is a review lead, not a conclusion about importance, intent, influence, conflict, impropriety, or wrongdoing.

Named organization links record that an organization name appeared in the source using a deterministic name pattern. They do not establish that the organization benefited from, influenced, or was responsible for an action.

Revision-change findings record differences between captured official-source revisions. They do not imply that the change was unusual, concealed, or improper.

## Civic source reliability fixes
- GISD and Wylie ISD use direct BoardBook organization feeds instead of generic district-page crawling
- current Sachse meetings use the public read-only CivicClerk API; historical Sachse Archive Center collections remain available
- Dallas County Commissioners Court notices use the County Clerk official/legal-notices record surface
- City of Wylie ArcGIS records are normalized into non-null human-readable source facts before analysis
- civic document lists are source-balanced so a large GIS feed cannot hide school/county/municipal sources
- opening a civic record automatically runs the current analyzer when that revision has not been analyzed yet
- discovery status reports records enumerated, documents captured, documents analyzed, and fetch errors per source
- Texas bills use exact session identity, allowing 89R, 89S1, and 89S2 to coexist; all three are discovered by default

## MVP-20 weekly source dashboard
- a default "What's happening this week" workspace grouped by institution
- selectable Sachse, Wylie, Wylie ISD, Garland ISD, Dallas County, Collin County, Texas Legislature, and U.S. Congress views
- combines multiple underlying feeds into one institution-level synopsis
- civic meeting documents are broken into agenda/action items when structured agenda items are available
- BoardBook agenda rows are read as numbered items, including Roman numbered sections, without attachment lists or page navigation
- activity is grouped into deterministic logical categories such as development/land use, contracts/procurement, budget/finance, taxes/bonds/debt, school facilities/boundaries, policies/rules, hearings, votes/actions, property/land, and elections/governance
- legislative activity is grouped into deterministic subject categories and uses dated legislative actions for the current calendar week
- every summary item retains a drill-down record ID and official source URL
- weekly civic items omit routine meeting procedure and crawler index pages, and merge matching agenda subjects across overlapping records before applying the item limit
- Wylie development projects require a source dated event in the current week; a newly imported historical project is not counted as current activity
- Collin County agendas are read from the Commissioners Court eAgenda index and their agenda items are summarized for the meeting week
- empty weekly views report captured record count and latest dated record so a coverage gap can be distinguished from no current activity
- administrative legislative actions do not displace substantive actions in the weekly synopsis
- lettered agenda section headings organize substantive items without becoming summary cards; meeting addresses, contact details, and routine procedure are omitted
- the weekly layer is intentionally deterministic/source-backed so future research and conversational LLM controls can sit on top without deciding the underlying facts

API:
- `GET /dashboard/sources`
- `GET /dashboard/weekly/{source_id}`

## Start
Copy `.env.example` to `.env`, add your api.data.gov key, configure the local LLM endpoint, then:

```bash
docker compose up --build
```

The API container runs `alembic upgrade head` before starting Uvicorn. Existing pre-MVP-17 volumes must be adopted once as described above.

Open `http://localhost:8000/` for the dashboard or `http://localhost:8000/docs` for the API. With the default configuration, automatic discovery begins in the background after startup.

## Endpoints
```
GET  /discovery/sources
POST /discovery/run
GET  /discovery/status
GET  /civic-documents
GET  /civic-documents/{document_id}/revisions
POST /civic-documents/{document_id}/analyze
GET  /civic-documents/{document_id}/analysis
GET  /jurisdictions
POST /jurisdictions/{jurisdiction}/ingest/{session}/{bill_type}/{number}
POST /jurisdictions/{jurisdiction}/discover/{session}?limit=100&ingest=false
POST /ingest/federal/{congress}/{bill_type}/{number}
POST /monitor/federal/{congress}?limit=50
GET  /bills
GET  /bills/{bill_id}/documents
POST /bills/{bill_id}/fiscal-analysis
GET  /bills/{bill_id}/fiscal-analysis
POST /bills/{bill_id}/lineage
GET  /bills/{bill_id}/lineage
POST /bills/{bill_id}/scope-analysis
GET  /bills/{bill_id}/scope-analysis
POST /bills/{bill_id}/evidence-packets
GET  /bills/{bill_id}/evidence-packets
POST /sections/{section_id}/evidence-packet
GET  /evidence-packets/{packet_id}
POST /bills/{bill_id}/queue/sync
GET  /investigation-queue
GET  /investigation-queue/summary
PATCH /investigation-queue/{item_id}
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
POST /bills/{bill_id}/correlate
GET  /bills/{bill_id}/correlations
POST /bills/{bill_id}/research
GET  /research/{run_id}
POST /bills/{bill_id}/reports
GET  /reports/{report_id}
POST /watches
GET  /watches
PATCH /watches/{watch_id}
POST /watches/{watch_id}/scan
POST /watches/run-all
GET  /watch-scans/{scan_id}
GET  /watch-events
```

The system extracts review signals and preserves evidence. It does not declare legislation corrupt or politically good/bad. AI explains evidence; source documents establish facts.


### Texas example

```
POST /jurisdictions/TX/ingest/89R/HB/9
```

The legacy federal ingest endpoint remains supported for compatibility.


### Texas session discovery example

```
POST /jurisdictions/TX/discover/89R?limit=100&ingest=true
```

A Texas session watch can then be created with `target_type="session"`, `jurisdiction="TX"`, `congress=89`, and `metadata.session="89R"`.
