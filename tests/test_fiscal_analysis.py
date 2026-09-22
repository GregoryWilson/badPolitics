from types import SimpleNamespace
from app.services.fiscal_analysis import analyze_text, _comparison_findings

def categories(rows):
    return {r["category"] for r in rows}

def test_detects_appropriation_tax_fee_and_mandate_signals():
    text="""
    SECTION 1. The department shall administer the program for each county.
    SECTION 2. $5 million is appropriated from the general revenue fund.
    SECTION 3. A tax credit is allowed for eligible applicants.
    SECTION 4. The agency shall impose a fee in the amount of $125.
    """
    found=categories(analyze_text(text))
    assert "appropriation" in found
    assert "tax_change" in found
    assert "fee_change" in found
    assert "mandate" in found
    assert "explicit_fiscal_amount" in found

def test_fiscal_note_amount_can_exceed_bill_text_amount():
    bill=SimpleNamespace(text="The program may receive $10,000.")
    fiscal=SimpleNamespace(
        id=7,
        document_type="fiscal_note",
        description="Fiscal Note",
        source_url="https://example.test/fiscal",
        text="The fiscal impact is estimated at $2 million in implementation cost.",
    )
    rows=_comparison_findings(bill,[fiscal])
    found=categories(rows)
    assert "fiscal_note_amount_exceeds_bill_text" in found
    assert "fiscal_effect_not_explicit_in_bill_text" in found

def test_analysis_scope_gap_is_descriptive_not_motive_claim():
    bill=SimpleNamespace(text="SECTION 1. $1 million is appropriated from the general revenue fund.")
    analysis=SimpleNamespace(
        id=8,
        document_type="bill_analysis",
        description="Bill Analysis",
        source_url="https://example.test/analysis",
        text="This bill changes program administration.",
    )
    rows=_comparison_findings(bill,[analysis])
    gaps=[r for r in rows if r["category"]=="analysis_scope_gap"]
    assert gaps
    combined=" ".join(r["statement"]+" "+r["evidence"] for r in gaps).lower()
    assert "conceal" not in combined
    assert "corrupt" not in combined

def test_no_scope_gap_when_analysis_mentions_same_subject():
    bill=SimpleNamespace(text="SECTION 1. Money is appropriated from the general revenue fund.")
    analysis=SimpleNamespace(
        id=9,
        document_type="bill_analysis",
        description="Bill Analysis",
        source_url="https://example.test/analysis",
        text="The bill contains an appropriation from the general revenue fund.",
    )
    rows=_comparison_findings(bill,[analysis])
    assert not [r for r in rows if r["category"]=="analysis_scope_gap"]
