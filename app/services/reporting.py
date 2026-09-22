from collections import Counter
from sqlalchemy import select
from app.models.entities import (
    Bill, BillVersion, Section, Finding, LegislativeEntityLink, EvidenceEntity,
    CorrelationFinding, EntityRelationship, ResearchRun, ResearchStep, InvestigationReport,
    LegislativeDocument,
)
from app.services.metrics import bill_metrics
from app.services.correlation import correlations_for_bill
from app.services.fiscal_analysis import run_fiscal_analysis
from app.services.lineage import build_lineage
from app.services.scope_analysis import run_scope_analysis
from app.services.evidence_packets import build_bill_packets

FINDING_LABELS={
    "money":"Explicit monetary amount",
    "unspecified_spending":"Open-ended spending authority",
    "exemption":"Exemption or statutory override",
    "retroactivity":"Potential retroactive application",
    "grandfather":"Existing-arrangement protection",
    "enforcement_limit":"Enforcement limitation",
    "named_geography":"Named geographic specificity",
    "cross_reference_density":"Dense statutory cross-references",
}

def _latest_version(db,bill_id):
    return db.scalar(
        select(BillVersion)
        .where(BillVersion.bill_id==bill_id)
        .order_by(BillVersion.issued_on.desc(),BillVersion.id.desc())
    )

def _source(ref_type,ref_id,url=None,detail=None):
    return {"type":ref_type,"id":ref_id,"url":url,"detail":detail}

def build_report(db,bill_id:int,research_run_id:int|None=None):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    if research_run_id is not None:
        run=db.get(ResearchRun,research_run_id)
        if not run or run.bill_id!=bill_id:
            raise ValueError("Research run not found for bill")
    else:
        run=db.scalar(
            select(ResearchRun).where(ResearchRun.bill_id==bill_id).order_by(ResearchRun.id.desc())
        )

    latest=_latest_version(db,bill_id)
    findings=[]
    if latest:
        rows=db.execute(
            select(Finding,Section)
            .join(Section,Finding.section_id==Section.id)
            .where(Finding.version_id==latest.id)
            .order_by(Finding.severity.desc(),Finding.id)
        ).all()
        for f,section in rows:
            findings.append({
                "category":f.kind,
                "title":FINDING_LABELS.get(f.kind,f.label),
                "statement":f.label,
                "section":section.section_number,
                "confidence":round(float(f.severity),2),
                "evidence":f.evidence,
                "sources":[_source("bill_finding",f.id,latest.source_url,{
                    "version":latest.version_code,
                    "section_id":section.id,
                    "section":section.section_number,
                })],
                "caveat":"This is a deterministic text signal requiring contextual review.",
            })

    links=db.execute(
        select(LegislativeEntityLink,EvidenceEntity,Section)
        .join(EvidenceEntity,LegislativeEntityLink.entity_id==EvidenceEntity.id)
        .outerjoin(Section,LegislativeEntityLink.section_id==Section.id)
        .where(LegislativeEntityLink.bill_id==bill_id)
    ).all()
    for link,entity,section in links:
        if link.link_type not in {"named_organization","potential_beneficiary_class","named_geography"}:
            continue
        findings.append({
            "category":link.link_type,
            "title":{
                "named_organization":"Named organization",
                "potential_beneficiary_class":"Potential beneficiary class",
                "named_geography":"Named geography",
            }[link.link_type],
            "statement":f"{entity.canonical_name} is explicitly referenced by the bill analysis.",
            "section":section.section_number if section else None,
            "confidence":round(float(link.confidence),2),
            "evidence":link.evidence,
            "sources":[_source("legislative_entity_link",link.id,link.source_url,{
                "entity_id":entity.id,
                "extraction_method":link.extraction_method,
            })],
            "caveat":"A textual reference does not by itself establish special treatment or improper benefit.",
        })

    correlations=correlations_for_bill(db,bill_id)
    for c in correlations["correlations"]:
        sources=[]
        for r in c.get("external_relationships",[]):
            sources.append(_source("external_relationship",r["id"],r.get("source_url"),{
                "source_system":r.get("source_system"),
                "relation_type":r.get("relation_type"),
                "observed_on":r.get("observed_on"),
            }))
        findings.append({
            "category":"external_correlation",
            "title":"External evidence correlation",
            "statement":f'{c["legislative_entity"]["name"]} correlates with external evidence for {c["matched_entity"]["name"]}.',
            "section":None,
            "confidence":round(float(c["confidence"]),2),
            "evidence":c["evidence"],
            "sources":[_source("correlation",c["id"],None,{"match_basis":c["match_basis"]})]+sources,
            "caveat":"Correlation establishes record linkage only; it does not establish influence, causation, conflict of interest, or wrongdoing.",
        })

    fiscal_analysis=run_fiscal_analysis(db,bill_id)
    lineage=build_lineage(db,bill_id)
    scope_analysis=run_scope_analysis(db,bill_id)
    for f in fiscal_analysis.get("findings",[]):
        findings.append({
            "category":f["category"],
            "title":f["statement"],
            "statement":f["statement"],
            "section":None,
            "confidence":round(float(f["confidence"]),2),
            "evidence":f["evidence"],
            "sources":[_source(
                "comparative_fiscal_finding",
                f["id"],
                f.get("source_url"),
                {
                    "source_kind":f.get("source_kind"),
                    "document_id":f.get("document_id"),
                    "document_description":f.get("document_description"),
                },
            )],
            "caveat":"This is a deterministic fiscal/document comparison signal. It does not establish concealment, intent, impropriety, or inaccurate official analysis.",
        })

    later_lineage=[
        event for event in lineage.get("events",[])
        if event["from_version"]["id"] is not None and event["event_type"] in {"introduced","modified"}
    ]
    for event in later_lineage:
        candidates=event.get("candidate_amendments") or []
        candidate_text=""
        if candidates:
            top=candidates[0]
            candidate_text=(
                f' Candidate amendment association: {top["amendment_type"].upper()} '
                f'{top["amendment_number"]} ({top["confidence"]:.2f} confidence).'
            )
        findings.append({
            "category":"provision_lineage",
            "title":"Provision changed after initial bill text",
            "statement":f'Section {event["section_number"]} was {event["event_type"]} in version {event["to_version"]["code"]}.',
            "section":event["section_number"],
            "confidence":0.90 if event["event_type"]=="introduced" else 0.78,
            "evidence":(
                f'From {event["from_version"]["code"]} to {event["to_version"]["code"]}.'
                + candidate_text
            ),
            "sources":[_source(
                "provision_lineage",
                event["id"],
                None,
                {
                    "from_version":event["from_version"],
                    "to_version":event["to_version"],
                    "candidate_amendments":candidates,
                },
            )],
            "caveat":"A later-added or modified provision is a version-history fact. Candidate amendment associations are leads, not proof that an amendment caused the change.",
        })

    for f in scope_analysis.get("findings",[]):
        findings.append({
            "category":f["category"],
            "title":"Provision scope mismatch review",
            "statement":f["statement"],
            "section":f["section_number"],
            "confidence":round(float(f["confidence"]),2),
            "evidence":(
                f'{f["evidence"]} '
                f'Anchor similarity: {f["anchor_similarity"] if f["anchor_similarity"] is not None else "n/a"}; '
                f'peer similarity: {f["peer_similarity"]}.'
            ),
            "sources":[_source(
                "scope_finding",
                f["id"],
                latest.source_url if latest else None,
                {
                    "section_id":f["section_id"],
                    "section_number":f["section_number"],
                    "heading":f["heading"],
                    "divergent_terms":f["metadata"].get("divergent_terms",[]),
                },
            )],
            "caveat":"Semantic distance is a review signal only. Broad bills, technical drafting, or legitimately cross-cutting provisions can produce outliers.",
        })

    packet_result=build_bill_packets(db,bill_id,generate_narrative=False,limit=25,prepare=False)
    packet_rows=[{
        "packet_id":p["packet_id"],
        "section_id":p["section_id"],
        "section_number":(p["packet"].get("section") or {}).get("number"),
        "packet_hash":p["packet_hash"],
        "evidence_count":len((p["packet"] or {}).get("evidence",[])),
        "has_narrative":bool(p.get("narrative")),
    } for p in packet_result.get("packets",[])]

    supporting_documents=db.scalars(
        select(LegislativeDocument)
        .where(LegislativeDocument.bill_id==bill_id)
        .order_by(LegislativeDocument.document_type,LegislativeDocument.id)
    ).all()
    document_rows=[{
        "id":d.id,
        "document_type":d.document_type,
        "description":d.description,
        "source_url":d.source_url,
        "source_system":d.source_system,
        "issued_on":d.issued_on,
        "format":d.format,
        "sha256":d.sha256,
        "has_text":d.text is not None,
        "metadata":d.metadata_json,
    } for d in supporting_documents]

    research_summary=None
    research_steps=[]
    if run:
        steps=db.scalars(select(ResearchStep).where(ResearchStep.run_id==run.id).order_by(ResearchStep.id)).all()
        research_steps=[{
            "id":s.id,"entity_id":s.entity_id,"source_system":s.source_system,
            "action":s.action,"status":s.status,"reason":s.reason,
        } for s in steps]
        research_summary={"run_id":run.id,"status":run.status,"summary":run.summary_json}

    category_counts=Counter(f["category"] for f in findings)
    report={
        "schema_version":"1.0",
        "bill":{
            "id":bill.id,"jurisdiction":bill.jurisdiction,
            "session":(bill.metadata_json or {}).get("jurisdiction_session") or str(bill.congress),
            "congress":bill.congress,
            "bill_type":bill.bill_type,"bill_number":bill.bill_number,"title":bill.title,
            "latest_action":bill.latest_action,
        },
        "version":{
            "code":latest.version_code if latest else None,
            "issued_on":latest.issued_on if latest else None,
            "source_url":latest.source_url if latest else None,
            "sha256":latest.sha256 if latest else None,
        },
        "metrics":bill_metrics(db,bill_id),
        "finding_summary":{
            "total":len(findings),
            "by_category":dict(sorted(category_counts.items())),
        },
        "findings":findings,
        "supporting_documents":document_rows,
        "fiscal_analysis":{
            "finding_count":fiscal_analysis.get("finding_count",0),
            "by_category":fiscal_analysis.get("by_category",{}),
            "interpretation_note":fiscal_analysis.get("interpretation_note"),
        },
        "lineage":{
            "event_count":lineage.get("event_count",0),
            "later_change_count":len(later_lineage),
            "interpretation_note":lineage.get("interpretation_note"),
        },
        "scope_analysis":{
            "finding_count":scope_analysis.get("finding_count",0),
            "interpretation_note":scope_analysis.get("interpretation_note"),
        },
        "evidence_packets":{
            "packet_count":len(packet_rows),
            "packets":packet_rows,
            "interpretation_note":packet_result.get("interpretation_note"),
        },
        "research":research_summary,
        "research_steps":research_steps,
        "interpretation_note":"Findings organize source-backed facts and review signals. They are not a political rating, corruption determination, motive inference, or recommendation.",
    }
    row=InvestigationReport(
        bill_id=bill_id,
        research_run_id=run.id if run else None,
        status="complete",
        report_json=report,
    )
    db.add(row); db.commit(); db.refresh(row)
    return {"report_id":row.id,**report}

def get_report(db,report_id:int):
    row=db.get(InvestigationReport,report_id)
    if not row:
        raise ValueError("Investigation report not found")
    return {"report_id":row.id,**row.report_json}
