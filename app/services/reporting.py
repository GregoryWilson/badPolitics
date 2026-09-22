from collections import Counter
from sqlalchemy import select
from app.models.entities import (
    Bill, BillVersion, Section, Finding, LegislativeEntityLink, EvidenceEntity,
    CorrelationFinding, EntityRelationship, ResearchRun, ResearchStep, InvestigationReport,
)
from app.services.metrics import bill_metrics
from app.services.correlation import correlations_for_bill

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
            "id":bill.id,"jurisdiction":bill.jurisdiction,"congress":bill.congress,
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
