from app.services.rules import analyze_section
from app.services.diffing import summary

def test_detects_money_and_exemption():
    s={"text":"Notwithstanding any other provision, $50 million is authorized for the District."}
    kinds={x["kind"] for x in analyze_section(s)}
    assert "money" in kinds and "exemption" in kinds and "named_geography" in kinds

def test_diff_summary():
    x=summary("a\nb\n","a\nc\n")
    assert x["changed_lines"] >= 1
