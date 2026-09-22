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
