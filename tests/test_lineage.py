from types import SimpleNamespace
from app.services.lineage import _candidate_attributions, _version_key, _tokens

def amendment(number,date,description,sponsors=None):
    return SimpleNamespace(
        id=int(number),
        amendment_type="samdt",
        amendment_number=str(number),
        description=description,
        latest_action="Amendment agreed to",
        raw_json={
            "latestAction":{"actionDate":date},
            "sponsors":sponsors or [],
        },
        source_url=f"https://example.test/amendment/{number}",
    )

def version(id,issued_on):
    return SimpleNamespace(id=id,issued_on=issued_on,version_code=f"v{id}")

def test_version_order_prefers_issued_date():
    older=version(20,"2026-01-01")
    newer=version(10,"2026-02-01")
    assert sorted([newer,older],key=_version_key)==[older,newer]

def test_candidate_amendment_uses_temporal_and_text_overlap():
    old=version(1,"2026-01-01")
    new=version(2,"2026-02-01")
    a=amendment(
        12,
        "2026-01-15",
        "Provides a property tax exemption for qualifying school districts.",
        [{"fullName":"Alex Example"}],
    )
    rows=_candidate_attributions(
        [a],
        old,
        new,
        "SECTION 4. A property tax exemption applies to qualifying school districts.",
    )
    assert rows
    candidate,confidence,evidence,overlap,basis=rows[0]
    assert candidate.amendment_number=="12"
    assert basis=="temporal_text_overlap"
    assert confidence>=0.5
    assert overlap>0
    assert "between" in evidence

def test_temporal_only_attribution_is_low_confidence():
    old=version(1,"2026-01-01")
    new=version(2,"2026-02-01")
    a=amendment(13,"2026-01-20","Renames an unrelated commission.")
    rows=_candidate_attributions(
        [a],old,new,
        "SECTION 9. A tax credit is created for eligible manufacturers.",
    )
    assert rows
    assert rows[0][1]==0.40
    assert rows[0][4]=="temporal_only"

def test_outside_window_without_text_overlap_is_not_attributed():
    old=version(1,"2026-01-01")
    new=version(2,"2026-02-01")
    a=amendment(14,"2026-03-01","Renames an unrelated commission.")
    assert _candidate_attributions(
        [a],old,new,
        "SECTION 9. A tax credit is created for eligible manufacturers.",
    )==[]

def test_tokens_drop_common_legislative_words():
    tokens=_tokens("This section shall provide a tax exemption for manufacturers.")
    assert "section" not in tokens
    assert "shall" not in tokens
    assert "exemption" in tokens
    assert "manufacturers" in tokens
