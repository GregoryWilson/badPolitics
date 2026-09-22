import hashlib
import re
from collections import Counter
from sqlalchemy import select, delete

from app.models.entities import (
    Bill, BillVersion, LegislativeDocument, ComparativeFinding,
)
from app.services.parser import MONEY_RE

SIGNALS=[
    ("appropriation",0.88,re.compile(r"\b(?:appropriat(?:e|ed|ion|ions)|general revenue fund|special fund|dedicated account)\b",re.I),"Appropriation or dedicated-fund language"),
    ("tax_change",0.86,re.compile(r"\b(?:tax credit|tax exemption|exempt from .*tax|deduction|taxable|tax rate|franchise tax|sales and use tax|property tax)\b",re.I),"Tax-base, rate, credit, deduction, or exemption language"),
    ("fee_change",0.82,re.compile(r"\b(?:fee|surcharge|assessment)\b.{0,100}\b(?:increase|decrease|impose|collect|charge|set|amount|dollar|\$)",re.I|re.S),"Fee, surcharge, or assessment change"),
    ("mandate",0.78,re.compile(r"\b(?:shall|must|required to)\b.{0,160}\b(?:county|municipality|school district|agency|department|local government|political subdivision)\b",re.I|re.S),"Required governmental implementation"),
    ("implementation_cost",0.78,re.compile(r"\b(?:implementation cost|administrative cost|cost to implement|additional full-time equivalent|FTE|technology cost|staffing cost)\b",re.I),"Implementation or administrative cost"),
    ("revenue_effect",0.80,re.compile(r"\b(?:revenue loss|revenue gain|revenue decrease|revenue increase|loss of revenue|gain in revenue|fiscal implication|fiscal impact)\b",re.I),"Revenue or fiscal-effect language"),
    ("beneficiary_specific_funding",0.72,re.compile(r"\b(?:grant|award|payment|reimbursement|credit|subsidy|assistance)\b.{0,180}\b(?:eligible|recipient|entity|organization|company|association|district|county|municipality)\b",re.I|re.S),"Funding or benefit directed to a defined recipient class"),
]

ANALYSIS_TERMS={
    "appropriation":re.compile(r"appropriat|general revenue|special fund|dedicated account",re.I),
    "tax_change":re.compile(r"tax credit|tax exemption|deduction|tax rate|franchise tax|sales and use tax|property tax",re.I),
    "fee_change":re.compile(r"fee|surcharge|assessment",re.I),
    "mandate":re.compile(r"mandate|required|shall|must",re.I),
    "implementation_cost":re.compile(r"implementation|administrative cost|FTE|staff|technology cost",re.I),
    "revenue_effect":re.compile(r"revenue|fiscal impact|fiscal implication",re.I),
}

def _excerpt(text,start,end,before=220,after=320):
    return text[max(0,start-before):min(len(text),end+after)].strip()

def _money_values(text):
    values=[]
    for match in MONEY_RE.finditer(text or ""):
        raw=match.group(1).replace(",","")
        try:
            value=float(raw)
        except ValueError:
            continue
        scale=(match.group(2) or "").lower()
        value*= {"thousand":1_000,"million":1_000_000,"billion":1_000_000_000}.get(scale,1)
        values.append({"text":match.group(0),"value":value})
    return values

def _candidate(category,confidence,statement,evidence,source_kind,document_id=None,metadata=None):
    digest=hashlib.sha256(f"{category}|{source_kind}|{document_id}|{evidence}".encode()).hexdigest()
    return {
        "category":category,
        "confidence":confidence,
        "statement":statement,
        "evidence":evidence,
        "source_kind":source_kind,
        "document_id":document_id,
        "evidence_hash":digest,
        "metadata":metadata or {},
    }

def analyze_text(text,source_kind="bill_text",document_id=None):
    findings=[]
    category_counts={}
    for category,confidence,pattern,label in SIGNALS:
        for match in pattern.finditer(text or ""):
            if category_counts.get(category,0)>=5:
                break
            findings.append(_candidate(
                category,confidence,label,_excerpt(text,match.start(),match.end()),
                source_kind,document_id,
            ))
            category_counts[category]=category_counts.get(category,0)+1
    monies=_money_values(text or "")
    if monies:
        largest=max(monies,key=lambda x:x["value"])
        findings.append(_candidate(
            "explicit_fiscal_amount",0.92,
            "Explicit monetary amount appears in fiscal or legislative text.",
            largest["text"],source_kind,document_id,
            {"amount_count":len(monies),"largest_amount":largest["value"],"largest_amount_text":largest["text"]},
        ))
    return findings

def _comparison_findings(latest,documents):
    findings=[]
    bill_text=latest.text if latest else ""
    bill_categories={f["category"] for f in analyze_text(bill_text)}
    analysis_docs=[d for d in documents if d.document_type=="bill_analysis" and d.text]
    fiscal_docs=[d for d in documents if d.document_type=="fiscal_note" and d.text]

    for doc in analysis_docs:
        for category in sorted(bill_categories.intersection(ANALYSIS_TERMS)):
            if not ANALYSIS_TERMS[category].search(doc.text or ""):
                findings.append(_candidate(
                    "analysis_scope_gap",0.68,
                    f"Bill text contains {category.replace('_',' ')} language that is not explicitly mentioned in this bill analysis.",
                    f"Bill signal: {category}; analysis: {doc.description or 'bill analysis'}",
                    "comparison",doc.id,
                    {"bill_signal_category":category,"comparison_document_type":"bill_analysis"},
                ))

    bill_money=_money_values(bill_text)
    bill_max=max((x["value"] for x in bill_money),default=0)
    for doc in fiscal_docs:
        fiscal_money=_money_values(doc.text or "")
        fiscal_max=max((x["value"] for x in fiscal_money),default=0)
        if fiscal_max and fiscal_max>bill_max and fiscal_max>=100_000:
            findings.append(_candidate(
                "fiscal_note_amount_exceeds_bill_text",0.84,
                "Fiscal note contains a larger explicit monetary amount than the bill text.",
                f"Largest fiscal-note amount: ${fiscal_max:,.0f}; largest bill-text amount: ${bill_max:,.0f}.",
                "comparison",doc.id,
                {"fiscal_note_largest_amount":fiscal_max,"bill_text_largest_amount":bill_max},
            ))
        doc_categories={f["category"] for f in analyze_text(doc.text or "","fiscal_note",doc.id)}
        for category in ("implementation_cost","revenue_effect"):
            if category in doc_categories and category not in bill_categories:
                findings.append(_candidate(
                    "fiscal_effect_not_explicit_in_bill_text",0.76,
                    f"Fiscal note describes {category.replace('_',' ')} that is not explicit in the bill-text signal set.",
                    f"Fiscal note: {doc.description or doc.source_url}; signal: {category}.",
                    "comparison",doc.id,
                    {"fiscal_signal_category":category},
                ))
    return findings

def run_fiscal_analysis(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    latest=db.scalar(
        select(BillVersion)
        .where(BillVersion.bill_id==bill_id)
        .order_by(BillVersion.issued_on.desc(),BillVersion.id.desc())
    )
    documents=db.scalars(
        select(LegislativeDocument).where(LegislativeDocument.bill_id==bill_id)
    ).all()

    candidates=[]
    if latest:
        candidates.extend(analyze_text(latest.text,"bill_text"))
    for doc in documents:
        if doc.text:
            candidates.extend(analyze_text(doc.text,doc.document_type,doc.id))
    candidates.extend(_comparison_findings(latest,documents))

    db.execute(delete(ComparativeFinding).where(ComparativeFinding.bill_id==bill_id))
    rows=[]
    seen=set()
    for item in candidates:
        key=(item["document_id"],item["category"],item["evidence_hash"])
        if key in seen:
            continue
        seen.add(key)
        row=ComparativeFinding(
            bill_id=bill_id,
            document_id=item["document_id"],
            category=item["category"],
            confidence=item["confidence"],
            statement=item["statement"],
            evidence=item["evidence"],
            source_kind=item["source_kind"],
            evidence_hash=item["evidence_hash"],
            metadata_json=item["metadata"],
        )
        db.add(row); db.flush()
        rows.append(row)
    db.commit()
    return fiscal_analysis_result(db,bill_id)

def fiscal_analysis_result(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    rows=db.scalars(
        select(ComparativeFinding)
        .where(ComparativeFinding.bill_id==bill_id)
        .order_by(ComparativeFinding.confidence.desc(),ComparativeFinding.id)
    ).all()
    docs={d.id:d for d in db.scalars(select(LegislativeDocument).where(LegislativeDocument.bill_id==bill_id)).all()}
    result=[]
    for row in rows:
        doc=docs.get(row.document_id)
        result.append({
            "id":row.id,
            "category":row.category,
            "confidence":row.confidence,
            "statement":row.statement,
            "evidence":row.evidence,
            "source_kind":row.source_kind,
            "document_id":row.document_id,
            "source_url":doc.source_url if doc else (bill.metadata_json or {}).get("source_url"),
            "document_description":doc.description if doc else None,
            "metadata":row.metadata_json,
        })
    counts=Counter(r["category"] for r in result)
    return {
        "bill_id":bill_id,
        "finding_count":len(result),
        "by_category":dict(sorted(counts.items())),
        "findings":result,
        "interpretation_note":"These are deterministic fiscal and document-comparison review signals. A mismatch does not by itself establish concealment, intent, impropriety, or inaccurate official analysis.",
    }