from app.services.evidence_packets import _stable_hash_payload, audit_narrative_citations

def test_stable_hash_payload_removes_internal_ids_recursively():
    payload={
        "bill":{"id":10,"title":"Example"},
        "section":{"section_id":20,"number":"4"},
        "evidence":[
            {
                "evidence_id":"D1",
                "kind":"deterministic_finding",
                "metadata":{
                    "finding_id":30,
                    "relationship_ids":[1,2],
                    "confidence":0.8,
                },
            }
        ],
    }
    stable=_stable_hash_payload(payload)
    assert "id" not in stable["bill"]
    assert "section_id" not in stable["section"]
    assert "evidence_id" not in stable["evidence"][0]
    assert "finding_id" not in stable["evidence"][0]["metadata"]
    assert "relationship_ids" not in stable["evidence"][0]["metadata"]
    assert stable["evidence"][0]["metadata"]["confidence"]==0.8

def test_citation_audit_accepts_only_packet_ids():
    entries=[
        {"evidence_id":"S1"},
        {"evidence_id":"Q1"},
        {"evidence_id":"C1"},
    ]
    audit=audit_narrative_citations(
        "The section text states X [S1]. Scope review surfaced Y [Q1].",
        entries,
    )
    assert audit["has_citations"] is True
    assert audit["invalid_ids"]==[]
    assert audit["used_ids"]==["Q1","S1"]

def test_citation_audit_rejects_unknown_id():
    entries=[{"evidence_id":"S1"}]
    audit=audit_narrative_citations("A claim [S1] and another [Z99].",entries)
    assert audit["invalid_ids"]==["Z99"]

def test_citation_audit_detects_uncited_narrative():
    entries=[{"evidence_id":"S1"}]
    audit=audit_narrative_citations("This narrative has no packet citation.",entries)
    assert audit["has_citations"] is False
    assert audit["invalid_ids"]==[]
