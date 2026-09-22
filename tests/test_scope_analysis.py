from types import SimpleNamespace
from app.services.scope_analysis import analyze_scope_sections, _tokens

def section(number,text,heading=None):
    return SimpleNamespace(section_number=str(number),text=text,heading=heading)

def expand(*sentences):
    return " ".join(sentences*4)

def test_flags_strong_outlier_against_title_and_peers():
    sections=[
        section(1,expand("Corn producers receive crop insurance assistance for agricultural losses, farm yields, planting, harvesting, and commodity production.")),
        section(2,expand("Wheat growers receive conservation assistance for soil health, agricultural land, crop production, irrigation, and farming practices.")),
        section(3,expand("Farmers use commodity support programs for crop production, agricultural markets, farm income, grain prices, and producer assistance.")),
        section(4,expand("Rural agricultural producers receive loans for farm equipment, crop storage, agricultural facilities, machinery, and production infrastructure.")),
        section(5,expand("Agricultural export programs support producers selling crops, grain, food commodities, farm products, and agricultural goods in foreign markets.")),
        section(6,expand("Domestic violence shelters receive grants to house victims with pets, service animals, companion animals, emergency shelter, and transitional housing.")),
    ]
    rows=analyze_scope_sections(
        "An Act relating to agriculture, farms, crops, and food production.",
        {"subjects":["Agriculture","Farm programs","Crop production"]},
        sections,
    )
    flagged={r["section"].section_number:r for r in rows}
    assert "6" in flagged
    assert flagged["6"]["peer_similarity"] < 0.20
    assert set(flagged["6"]["metadata"]["divergent_terms"]).intersection({"pets","shelters","violence","victims","animals"})

def test_cohesive_bill_does_not_flag_every_section():
    sections=[
        section(1,expand("Property tax appraisal procedures apply to residential property, taxable value, local appraisal districts, notices, and valuation records.")),
        section(2,expand("Property tax exemptions may be claimed by eligible homeowners through appraisal districts, tax records, valuation procedures, and exemption applications.")),
        section(3,expand("County appraisal districts publish property tax notices, appraisal information, taxable values, valuation records, and taxpayer procedures.")),
        section(4,expand("Property tax protest hearings are scheduled by appraisal review boards using valuation records, taxpayer notices, hearing procedures, and taxable values.")),
        section(5,expand("School district property tax rates reflect taxable property valuation, appraisal records, tax calculations, local revenue, and valuation procedures.")),
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
            section(1,expand("Agricultural producers apply for grants supporting farms, crops, agricultural production, farm operations, and rural land.")),
            section(2,expand("Farm operators receive conservation assistance for agricultural land, crops, soil practices, farm production, and rural acreage.")),
            section(3,expand("Crop producers participate in agricultural insurance programs covering farms, yields, production losses, commodities, and planting.")),
        ],
    )
    assert rows==[]

def test_scope_tokens_remove_legislative_boilerplate():
    tokens=_tokens("SECTION 4. This Act shall provide assistance for citrus growers and orchards.")
    assert "section" not in tokens
    assert "shall" not in tokens
    assert "citrus" in tokens
    assert "orchards" in tokens
