from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_dashboard_assets_exist():
    for relative in ("app/static/index.html","app/static/styles.css","app/static/app.js"):
        assert (ROOT/relative).is_file()

def test_dashboard_uses_neutral_review_language():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    combined=(html+" "+js).lower()
    assert "review signals are not political ratings" in combined
    assert "corruption score" not in combined
    assert "vote for" not in combined

def test_dashboard_source_links_are_protocol_guarded():
    js=(ROOT/"app/static/app.js").read_text()
    assert 'u.protocol==="http:"||u.protocol==="https:"' in js
    assert "safeUrl(r.source_url)" in js


def test_dashboard_includes_watch_controls_and_change_feed():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'id="watchBill"' in html
    assert 'id="scanWatches"' in html
    assert 'id="changeFeed"' in html
    assert 'api("/watch-events?limit=30")' in js
    assert 'api("/watches/run-all"' in js


def test_dashboard_uses_jurisdiction_and_session_labels():
    js=(ROOT/"app/static/app.js").read_text()
    assert "b.jurisdiction" in js
    assert "b.session" in js
    assert "state.selected.jurisdiction" in js


def test_dashboard_supports_non_federal_session_watches_and_documents():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'id="watchSession"' in html
    assert 'data-tab="documents"' in html
    assert 'api(`/bills/${state.selected.id}/documents`)' in js
    assert 'target_type:"session"' in js


def test_dashboard_supports_fiscal_review():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'data-tab="fiscal"' in html
    assert 'id="fiscal"' in html
    assert '/fiscal-analysis' in js
    assert "Fiscal Review" in html


def test_dashboard_supports_provision_lineage():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'data-tab="lineage"' in html
    assert 'id="lineage"' in html
    assert '/lineage' in js
    assert "Candidate amendment associations" in js


def test_dashboard_supports_scope_review():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'data-tab="scope"' in html
    assert 'id="scope"' in html
    assert '/scope-analysis' in js
    assert "Scope Review" in html


def test_dashboard_supports_evidence_packets_and_opt_in_synthesis():
    html=(ROOT/"app/static/index.html").read_text()
    js=(ROOT/"app/static/app.js").read_text()
    assert 'data-tab="packets"' in html
    assert 'id="packets"' in html
    assert '/evidence-packets?generate_narrative=false' in js
    assert 'generate_narrative=true' in js
    assert "Generate Local Synthesis" in js
