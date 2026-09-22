from types import SimpleNamespace
from app.services.scope_analysis import analyze_scope_sections, _tokens

def section(number,text,heading=None):
    return SimpleNamespace(section_number=str(number),text=text,heading=heading)

def test_flags_strong_outlier_against_title_and_peers():
    sections=[
        section(1,"Corn producers may receive crop insurance assistance for agricultural losses and farm yields."),
        section(2,"Wheat growers may receive conservation assistance for soil health and agricultural production."),
        section(3,"Farmers may use commodity support programs for crop production and agricultural markets."),
        section(4,"Rural agricultural producers may receive loans for farm equipment and crop storage."),
        section(5,"Agricultural export programs may support producers selling crops in foreign markets."),
        section(6,"Domestic violence shelters may receive grants to house victims with pets, service animals, and companion animals."),
    ]
    rows=analyze_scope_sections(
        "An Act relating to agriculture, farms, crops, and food production.",
        {"subjects":["Agriculture","Farm programs","Crop production"]},
        sections,
    )
    flagged={r["section"].section_number:r for r in rows}
    assert "6" in flagged
    assert flagged["6"]["peer_similarity"] < 0.20
    assert "pets" in flagged["6"]["metadata"]["divergent_terms"] or "shelters" in flagged["6"]["metadata"]["divergent_terms"]

def test_cohesive_bill_does_not_flag_every_section():
    sections=[
        section(1,"Property tax appraisal procedures apply to residential property and local appraisal districts."),
        section(2,"Property tax exemptions may be claimed by eligible homeowners through appraisal districts."),
        section(3,"County appraisal districts shall publish property tax notices and appraisal information."),
        section(4,"Property tax protest hearings shall be scheduled by appraisal review boards."),
        section(5,"School district property tax rates shall reflect the applicable taxable property valuation."),
    ]
    rows=analyze_scope_sections(
        "An Act relating to property taxation and appraisal districts.",
        {"subjects":["Property tax","Tax appraisal"]},
        sections,
    )
    assert len(rows) <= 1

def test_too_few_sections_returns_no_scope_outlier():
    rows=analyze_scope_sections(
        "An Act relating to agriculture.",
        {"subjects":["Agriculture"]},
        [
            section(1,"Agricultural producers may apply for grants supporting farms and crops."),
            section(2,"Farm operators may receive conservation assistance for agricultural land."),
            section(3,"Crop producers may participate in agricultural insurance programs."),
        ],
    )
    assert rows==[]

def test_scope_tokens_remove_legislative_boilerplate():
    tokens=_tokens("SECTION 4. This Act shall provide assistance for citrus growers and orchards.")
    assert "section" not in tokens
    assert "shall" not in tokens
    assert "citrus" in tokens
    assert "orchards" in tokens
