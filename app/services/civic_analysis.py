import difflib
import hashlib
import re
from sqlalchemy import select

from app.models.entities import (
    CivicDocument,CivicDocumentRevision,CivicAgendaItem,CivicFinding,
    CivicEntityLink,EvidenceEntity,
)
from app.services.graph import get_or_create_entity

MONEY_RE=re.compile(r"(?<!\w)\$\s?\d[\d,]*(?:\.\d{1,2})?(?:\s?(?:million|billion|thousand|M|B|K))?",re.I)
ITEM_RE=re.compile(r"^\s*(?:item\s+)?((?:[A-Z]\.)|(?:\d+(?:\.\d+)*[A-Z]?))[\s:.)-]+(.+)$",re.I)
ACTION_RE=re.compile(r"^\s*(consider|discuss|approve|adopt|authorize|award|public hearing|receive|review|vote|resolution)\b",re.I)
ORG_RE=re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&.'/-]*\s+){0,7}[A-Z][A-Za-z0-9&.'/-]*\s+"
    r"(?:Inc\.?|LLC|L\.L\.C\.|LP|L\.P\.|LLP|Corp\.?|Corporation|Company|Co\.?|"
    r"Association|Foundation|Institute|Council|Partners|Development|Holdings|Group))\b"
)

SIGNALS=[
    ("zoning_development",[
        r"\brezon(?:e|ing)\b",r"\bzoning\b",r"\bplanned development\b",r"\bsite plan\b",
        r"\bplat\b",r"\bland use\b",r"\bcomprehensive plan\b",r"\bdevelopment agreement\b",
    ]),
    ("procurement_contract",[
        r"\bcontract\b",r"\bprocurement\b",r"\bbid\b",r"\brfp\b",r"\brfq\b",
        r"\baward(?:ed|ing)?\b",r"\bvendor\b",r"\bpurchase order\b",
    ]),
    ("budget_finance",[
        r"\bbudget\b",r"\bappropriat",r"\bexpenditure\b",r"\brevenue\b",
        r"\bfund balance\b",r"\bcapital improvement\b",r"\bgrant\b",
    ]),
    ("bond_tax_debt",[
        r"\bbond\b",r"\btax rate\b",r"\bproperty tax\b",r"\bdebt service\b",
        r"\bcertificate of obligation\b",r"\btax increment\b",r"\btirz\b",
    ]),
    ("school_facility_boundary",[
        r"\bschool boundary\b",r"\battendance boundary\b",r"\bcampus consolidation\b",
        r"\bcampus closure\b",r"\bfacilit(?:y|ies)\b",r"\bschool construction\b",
        r"\brenovation\b",r"\btransportation zone\b",
    ]),
    ("policy_rule",[
        r"\bpolicy\b",r"\bcode of conduct\b",r"\bhandbook\b",r"\bordinance\b",
        r"\bregulation\b",r"\brule\b",
    ]),
    ("public_hearing",[
        r"\bpublic hearing\b",r"\bpublic comment\b",r"\bpublic forum\b",
    ]),
    ("vote_action",[
        r"\bapproved?\b",r"\badopted?\b",r"\bauthorized?\b",r"\bvote\b",
        r"\bmotion\b",r"\bresolution\b",
    ]),
    ("property_land",[
        r"\breal property\b",r"\bland acquisition\b",r"\bpurchase of land\b",
        r"\bsale of land\b",r"\bright[- ]of[- ]way\b",r"\beasement\b",
    ]),
    ("election_governance",[
        r"\belection\b",r"\bballot\b",r"\btrustee\b",r"\bcouncilmember\b",
        r"\bcommissioner\b",r"\bcharter amendment\b",
    ]),
]
COMPILED_SIGNALS=[(category,[re.compile(p,re.I) for p in patterns]) for category,patterns in SIGNALS]

def _hash(*parts):
    return hashlib.sha256("\n".join(str(p or "") for p in parts).encode("utf-8","ignore")).hexdigest()

def _latest_revision(db,document_id):
    return db.scalar(
        select(CivicDocumentRevision)
        .where(CivicDocumentRevision.civic_document_id==document_id)
        .order_by(CivicDocumentRevision.observed_at.desc(),CivicDocumentRevision.id.desc())
    )

def _extract_items(text):
    lines=[line.strip() for line in (text or "").splitlines() if line.strip()]
    items=[]; current=None
    for line in lines:
        m=ITEM_RE.match(line)
        action=ACTION_RE.match(line)
        if m or (action and len(line)<=1200):
            if current:
                items.append(current)
            if m:
                current={"item_number":m.group(1),"heading":m.group(2)[:500],"lines":[line]}
            else:
                current={"item_number":None,"heading":line[:500],"lines":[line]}
        elif current and len(current["lines"])<30:
            current["lines"].append(line)
    if current:
        items.append(current)
    # Avoid treating navigation-heavy webpages as giant agendas.
    return [x for x in items if len(" ".join(x["lines"]))>=20][:250]

def _evidence_excerpt(text,match,window=500):
    start=max(0,match.start()-window)
    end=min(len(text),match.end()+window)
    return " ".join(text[start:end].split())[:1800]

def _create_finding(db,doc,revision,category,statement,evidence,agenda_item=None,confidence=1.0,metadata=None):
    digest=_hash(category,evidence,agenda_item.id if agenda_item else "")
    existing=db.scalar(select(CivicFinding).where(
        CivicFinding.civic_document_id==doc.id,
        CivicFinding.revision_id==revision.id,
        CivicFinding.agenda_item_id==(agenda_item.id if agenda_item else None),
        CivicFinding.category==category,
        CivicFinding.evidence_hash==digest,
    ))
    if existing:
        return existing,False
    row=CivicFinding(
        civic_document_id=doc.id,revision_id=revision.id,
        agenda_item_id=agenda_item.id if agenda_item else None,
        category=category,statement=statement,evidence=evidence[:4000],
        confidence=confidence,evidence_hash=digest,metadata_json=metadata or {},
    )
    db.add(row); db.flush()
    return row,True

def _analyze_entities(db,doc,revision,agenda_items,text):
    created=0
    for match in ORG_RE.finditer(text or ""):
        name=" ".join(match.group(1).split())
        if len(name)<5:
            continue
        entity=get_or_create_entity(
            db,"organization",name,
            metadata={"first_seen_civic_source":doc.source_key},
        )
        item=next((i for i in agenda_items if name in i.text),None)
        existing=db.scalar(select(CivicEntityLink).where(
            CivicEntityLink.civic_document_id==doc.id,
            CivicEntityLink.revision_id==revision.id,
            CivicEntityLink.agenda_item_id==(item.id if item else None),
            CivicEntityLink.entity_id==entity.id,
            CivicEntityLink.link_type=="named_organization",
        ))
        if existing:
            continue
        db.add(CivicEntityLink(
            civic_document_id=doc.id,revision_id=revision.id,
            agenda_item_id=item.id if item else None,entity_id=entity.id,
            link_type="named_organization",evidence=name,confidence=1.0,
            metadata_json={"extraction_method":"deterministic_name_suffix"},
        ))
        created+=1
    return created

def analyze_civic_document(db,document_id):
    doc=db.get(CivicDocument,document_id)
    if not doc:
        raise ValueError("Civic document not found")
    revision=_latest_revision(db,document_id)
    if not revision:
        raise ValueError("Civic document has no revision to analyze")
    text=revision.text or doc.text or ""

    item_rows=db.scalars(select(CivicAgendaItem).where(
        CivicAgendaItem.civic_document_id==doc.id,
        CivicAgendaItem.revision_id==revision.id,
    ).order_by(CivicAgendaItem.ordinal)).all()
    if not item_rows:
        for ordinal,item in enumerate(_extract_items(text),1):
            item_text="\n".join(item["lines"])[:12000]
            digest=_hash(item["item_number"],item_text)
            row=CivicAgendaItem(
                civic_document_id=doc.id,revision_id=revision.id,ordinal=ordinal,
                item_number=item["item_number"],heading=item["heading"],
                text=item_text,evidence_hash=digest,
                metadata_json={"extraction_method":"deterministic_line_structure"},
            )
            db.add(row)
        db.flush()
        item_rows=db.scalars(select(CivicAgendaItem).where(
            CivicAgendaItem.civic_document_id==doc.id,
            CivicAgendaItem.revision_id==revision.id,
        ).order_by(CivicAgendaItem.ordinal)).all()

    created=0
    for category,patterns in COMPILED_SIGNALS:
        for pattern in patterns:
            match=pattern.search(text)
            if not match:
                continue
            evidence=_evidence_excerpt(text,match)
            item=next((i for i in item_rows if match.group(0).casefold() in i.text.casefold()),None)
            _,was_created=_create_finding(
                db,doc,revision,category,
                f"Source text contains an explicit {category.replace('_',' ')} signal.",
                evidence,item,1.0,
                {"matched_term":match.group(0),"scope":"agenda_item" if item else "document"},
            )
            created+=int(was_created)
            break

    money=list(MONEY_RE.finditer(text))
    if money:
        evidence="; ".join(dict.fromkeys(m.group(0) for m in money[:25]))
        _,was_created=_create_finding(
            db,doc,revision,"explicit_money_mentions",
            f"Source text contains {len(money)} explicit monetary mention(s).",
            evidence,None,1.0,
            {"mention_count":len(money),"values":[m.group(0) for m in money[:100]]},
        )
        created+=int(was_created)

    previous=db.scalar(
        select(CivicDocumentRevision)
        .where(
            CivicDocumentRevision.civic_document_id==doc.id,
            CivicDocumentRevision.id!=revision.id,
        )
        .order_by(CivicDocumentRevision.observed_at.desc(),CivicDocumentRevision.id.desc())
    )
    if previous and (previous.text or "")!=(revision.text or ""):
        old=(previous.text or "").splitlines()
        new=(revision.text or "").splitlines()
        diff="\n".join(difflib.unified_diff(old,new,fromfile=previous.sha256[:12],tofile=revision.sha256[:12],lineterm=""))
        added=sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        removed=sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        _,was_created=_create_finding(
            db,doc,revision,"document_revision_change",
            "The official source document text changed from the previously captured revision.",
            diff[:12000],None,1.0,
            {"previous_revision_id":previous.id,"added_lines":added,"removed_lines":removed},
        )
        created+=int(was_created)

    entity_links_created=_analyze_entities(db,doc,revision,item_rows,text)
    db.commit()
    return civic_analysis_result(db,document_id,revision.id) | {
        "created_findings":created,
        "created_entity_links":entity_links_created,
    }

def civic_analysis_result(db,document_id,revision_id=None):
    doc=db.get(CivicDocument,document_id)
    if not doc:
        raise ValueError("Civic document not found")
    revision=db.get(CivicDocumentRevision,revision_id) if revision_id else _latest_revision(db,document_id)
    if not revision:
        raise ValueError("Civic document has no revision")
    items=db.scalars(select(CivicAgendaItem).where(
        CivicAgendaItem.civic_document_id==doc.id,CivicAgendaItem.revision_id==revision.id
    ).order_by(CivicAgendaItem.ordinal)).all()
    findings=db.scalars(select(CivicFinding).where(
        CivicFinding.civic_document_id==doc.id,CivicFinding.revision_id==revision.id
    ).order_by(CivicFinding.category,CivicFinding.id)).all()
    links=db.execute(
        select(CivicEntityLink,EvidenceEntity)
        .join(EvidenceEntity,CivicEntityLink.entity_id==EvidenceEntity.id)
        .where(CivicEntityLink.civic_document_id==doc.id,CivicEntityLink.revision_id==revision.id)
        .order_by(EvidenceEntity.canonical_name)
    ).all()
    return {
        "document":{
            "id":doc.id,"source_key":doc.source_key,"jurisdiction":doc.jurisdiction,
            "governing_body":doc.governing_body,"document_type":doc.document_type,
            "title":doc.title,"meeting_date":doc.meeting_date,"source_url":doc.source_url,
        },
        "revision":{"id":revision.id,"sha256":revision.sha256,"observed_at":revision.observed_at.isoformat()},
        "agenda_items":[{
            "id":i.id,"ordinal":i.ordinal,"item_number":i.item_number,
            "heading":i.heading,"text":i.text,
        } for i in items],
        "findings":[{
            "id":f.id,"category":f.category,"statement":f.statement,
            "evidence":f.evidence,"confidence":f.confidence,
            "agenda_item_id":f.agenda_item_id,"metadata":f.metadata_json,
        } for f in findings],
        "entities":[{
            "link_id":link.id,"entity_id":entity.id,"entity_type":entity.entity_type,
            "name":entity.canonical_name,"link_type":link.link_type,
            "evidence":link.evidence,"agenda_item_id":link.agenda_item_id,
        } for link,entity in links],
        "interpretation_note":"These are deterministic review signals and source-linked entities. They do not establish political importance, motive, influence, conflict, impropriety, or wrongdoing.",
    }

def analyze_changed_civic_documents(db,document_ids):
    results=[]
    for document_id in sorted(set(document_ids or [])):
        try:
            results.append({"document_id":document_id,"status":"completed","analysis":analyze_civic_document(db,document_id)})
        except Exception as exc:
            db.rollback()
            results.append({"document_id":document_id,"status":"failed","error":str(exc)})
    return results
