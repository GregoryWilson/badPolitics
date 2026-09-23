import re
from collections import defaultdict
from datetime import datetime,timedelta,date
from sqlalchemy import select

from app.models.entities import Bill,BillAction,CivicDocument,CivicFinding,CivicAgendaItem
from app.services.civic_sources import CIVIC_SOURCES

SOURCE_GROUPS=[
    {"id":"sachse","label":"Sachse","kind":"civic","prefixes":["sachse_"]},
    {"id":"wylie","label":"Wylie","kind":"civic","source_keys":["wylie_development_projects"]},
    {"id":"wylie_isd","label":"Wylie ISD","kind":"civic","source_keys":["wylie_isd_board"]},
    {"id":"gisd","label":"Garland ISD","kind":"civic","prefixes":["gisd_"]},
    {"id":"dallas_county","label":"Dallas County","kind":"civic","prefixes":["dallas_"]},
    {"id":"collin_county","label":"Collin County","kind":"civic","prefixes":["collin_"]},
    {"id":"texas","label":"Texas Legislature","kind":"legislative","jurisdiction":"TX"},
    {"id":"federal","label":"U.S. Congress","kind":"legislative","jurisdiction":"US"},
]

CATEGORY_LABELS={
    "zoning_development":"Development & land use",
    "procurement_contract":"Contracts & procurement",
    "budget_finance":"Budget & finance",
    "bond_tax_debt":"Taxes, bonds & debt",
    "school_facility_boundary":"Schools, facilities & boundaries",
    "policy_rule":"Policies, ordinances & rules",
    "public_hearing":"Public hearings & comment",
    "vote_action":"Votes & official actions",
    "property_land":"Property & land",
    "election_governance":"Elections & governance",
    "education":"Education",
    "tax_budget":"Taxes & budget",
    "health":"Health",
    "public_safety":"Public safety & justice",
    "infrastructure_transportation":"Infrastructure & transportation",
    "business_labor":"Business & labor",
    "environment_energy":"Environment & energy",
    "housing_property":"Housing & property",
    "other_legislation":"Other legislation",
    "other_civic":"Other civic business",
}

LEGISLATIVE_TOPIC_PATTERNS=[
    ("education",[r"\bschool\b",r"\beducation\b",r"\bstudent\b",r"\bteacher\b",r"\bcollege\b",r"\buniversity\b"]),
    ("tax_budget",[r"\btax\b",r"\bbudget\b",r"\bappropriat",r"\brevenue\b",r"\bdebt\b",r"\btreasury\b"]),
    ("health",[r"\bhealth\b",r"\bmedical\b",r"\bmedicaid\b",r"\bmedicare\b",r"\bhospital\b",r"\bdrug\b"]),
    ("public_safety",[r"\bcrime\b",r"\bcriminal\b",r"\bpolice\b",r"\blaw enforcement\b",r"\bfirearm\b",r"\bcourt\b",r"\bprison\b"]),
    ("infrastructure_transportation",[r"\broad\b",r"\bhighway\b",r"\btransport",r"\brail\b",r"\bairport\b",r"\binfrastructure\b",r"\bwater\b"]),
    ("election_governance",[r"\belection\b",r"\bvoting\b",r"\bballot\b",r"\bgovernment\b",r"\bagency\b",r"\bethics\b"]),
    ("business_labor",[r"\bbusiness\b",r"\bemploy",r"\blabor\b",r"\bworker\b",r"\bwage\b",r"\bcommerce\b",r"\bindustry\b"]),
    ("environment_energy",[r"\benvironment",r"\benergy\b",r"\boil\b",r"\bgas\b",r"\belectric",r"\bclimate\b",r"\bconservation\b"]),
    ("housing_property",[r"\bhousing\b",r"\bproperty\b",r"\breal estate\b",r"\bland\b",r"\brent\b",r"\bmortgage\b"]),
]
COMPILED_TOPICS=[(key,[re.compile(p,re.I) for p in patterns]) for key,patterns in LEGISLATIVE_TOPIC_PATTERNS]

def _week_bounds(today=None):
    today=today or datetime.utcnow().date()
    start=today-timedelta(days=today.weekday())
    end=start+timedelta(days=6)
    return start,end

def _parse_date(value):
    if not value:
        return None
    raw=str(value).strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

def _source_group(group_id):
    row=next((x for x in SOURCE_GROUPS if x["id"]==group_id),None)
    if not row:
        raise ValueError("Unknown dashboard source")
    return row

def _civic_keys(group):
    known=[row["source_key"] for row in CIVIC_SOURCES]
    selected=set(group.get("source_keys",[]))
    for prefix in group.get("prefixes",[]):
        selected.update(key for key in known if key.startswith(prefix))
    return sorted(selected)

def _civic_category(doc,findings):
    priority=[
        "zoning_development","procurement_contract","budget_finance","bond_tax_debt",
        "school_facility_boundary","property_land","policy_rule","election_governance",
        "public_hearing","vote_action",
    ]
    found={f.category for f in findings}
    for key in priority:
        if key in found:
            return key
    mapping={
        "zoning":"zoning_development","bond":"bond_tax_debt","policy":"policy_rule",
        "public_hearing":"public_hearing","budget":"budget_finance",
    }
    return mapping.get(doc.document_type,"other_civic")

def _compact(text,limit=380):
    value=" ".join((text or "").split())
    return value if len(value)<=limit else value[:limit-1].rstrip()+"…"

def _civic_week(db,group,start,end,limit):
    keys=_civic_keys(group)
    if not keys:
        return []
    rows=db.scalars(
        select(CivicDocument)
        .where(CivicDocument.source_key.in_(keys))
        .order_by(CivicDocument.meeting_date.desc(),CivicDocument.last_seen_at.desc())
        .limit(max(limit*5,200))
    ).all()
    items=[]
    for doc in rows:
        meeting=_parse_date(doc.meeting_date)
        seen=doc.last_seen_at.date() if doc.last_seen_at else None
        if meeting:
            if not (start<=meeting<=end):
                continue
            event_date=meeting
            date_basis="meeting_date"
        elif seen and start<=seen<=end:
            event_date=seen
            date_basis="captured_this_week"
        else:
            continue
        findings=db.scalars(
            select(CivicFinding)
            .where(CivicFinding.civic_document_id==doc.id)
            .order_by(CivicFinding.id)
        ).all()
        agenda=db.scalars(
            select(CivicAgendaItem)
            .where(CivicAgendaItem.civic_document_id==doc.id)
            .order_by(CivicAgendaItem.ordinal)
            .limit(6)
        ).all()
        category=_civic_category(doc,findings)
        matched=[f for f in findings if f.category==category]
        synopsis=None
        if agenda:
            synopsis="; ".join(_compact(a.heading or a.text,140) for a in agenda[:3])
        elif matched:
            synopsis=_compact(matched[0].evidence or matched[0].statement)
        else:
            synopsis=_compact(doc.text,380)
        action_findings=[f for f in findings if f.category=="vote_action"]
        hearing=any(f.category=="public_hearing" for f in findings)
        items.append({
            "kind":"civic",
            "record_id":doc.id,
            "source_key":doc.source_key,
            "institution":group["label"],
            "category":category,
            "category_label":CATEGORY_LABELS[category],
            "title":doc.title,
            "date":event_date.isoformat(),
            "date_basis":date_basis,
            "status":"official action recorded" if action_findings else ("public hearing" if hearing else doc.document_type.replace("_"," ")),
            "synopsis":synopsis or "Official source record captured for this week.",
            "source_url":doc.source_url,
            "governing_body":doc.governing_body,
            "evidence_count":len(findings),
            "agenda_item_count":len(agenda),
        })
        if len(items)>=limit:
            break
    return items

def _bill_topic(bill):
    text=" ".join(filter(None,[bill.title,bill.latest_action]))
    for key,patterns in COMPILED_TOPICS:
        if any(p.search(text) for p in patterns):
            return key
    return "other_legislation"

def _action_status(text):
    value=(text or "").casefold()
    if "signed by" in value or "became law" in value:
        return "signed / enacted"
    if "veto" in value:
        return "veto action"
    if "passed" in value or "agreed to" in value:
        return "passed / agreed to"
    if "reported" in value or "committee" in value:
        return "committee action"
    if "referred" in value:
        return "referred"
    if "introduced" in value or "filed" in value:
        return "introduced / filed"
    return "legislative action"

def _legislative_week(db,group,start,end,limit):
    bills=db.scalars(
        select(Bill)
        .where(Bill.jurisdiction==group["jurisdiction"])
        .order_by(Bill.updated_at.desc(),Bill.id.desc())
        .limit(max(limit*10,500))
    ).all()
    items=[]
    for bill in bills:
        actions=db.scalars(
            select(BillAction)
            .where(BillAction.bill_id==bill.id)
            .order_by(BillAction.action_date.desc(),BillAction.id.desc())
        ).all()
        weekly=[a for a in actions if (_parse_date(a.action_date) and start<=_parse_date(a.action_date)<=end)]
        if not weekly:
            continue
        action=weekly[0]
        category=_bill_topic(bill)
        source_url=action.source_url
        if not source_url:
            version=db.scalar(select(__import__("app.models.entities",fromlist=["BillVersion"]).BillVersion).where(
                __import__("app.models.entities",fromlist=["BillVersion"]).BillVersion.bill_id==bill.id
            ).order_by(__import__("app.models.entities",fromlist=["BillVersion"]).BillVersion.id.desc()))
            source_url=version.source_url if version else None
        items.append({
            "kind":"bill",
            "record_id":bill.id,
            "source_key":f"legis:{bill.jurisdiction}:{bill.session_code or bill.congress}",
            "institution":group["label"],
            "category":category,
            "category_label":CATEGORY_LABELS[category],
            "title":f"{bill.bill_type.upper()} {bill.bill_number}: {bill.title or 'Untitled bill'}",
            "date":_parse_date(action.action_date).isoformat(),
            "date_basis":"legislative_action",
            "status":_action_status(action.text),
            "synopsis":_compact(action.text or bill.latest_action or bill.title),
            "source_url":source_url,
            "session":bill.session_code or str(bill.congress),
            "action_count_this_week":len(weekly),
        })
        if len(items)>=limit:
            break
    return items

def dashboard_sources(db=None):
    return [{
        "id":row["id"],
        "label":row["label"],
        "kind":row["kind"],
        "source_keys":_civic_keys(row) if row["kind"]=="civic" else [],
        "jurisdiction":row.get("jurisdiction"),
    } for row in SOURCE_GROUPS]

def weekly_source_summary(db,group_id,limit=150,today=None):
    group=_source_group(group_id)
    start,end=_week_bounds(today)
    if group["kind"]=="civic":
        items=_civic_week(db,group,start,end,limit)
    else:
        items=_legislative_week(db,group,start,end,limit)
    categories=defaultdict(list)
    for item in items:
        categories[item["category"]].append(item)
    category_rows=[
        {
            "category":key,
            "label":CATEGORY_LABELS.get(key,key.replace("_"," ").title()),
            "count":len(values),
            "items":sorted(values,key=lambda row:(row["date"],row["title"]),reverse=True),
        }
        for key,values in categories.items()
    ]
    category_rows.sort(key=lambda row:(-row["count"],row["label"]))
    return {
        "source":{"id":group["id"],"label":group["label"],"kind":group["kind"]},
        "window":{"start":start.isoformat(),"end":end.isoformat(),"label":"This week"},
        "item_count":len(items),
        "category_count":len(category_rows),
        "categories":category_rows,
        "interpretation_note":"This dashboard is a source-backed activity synopsis. Categories describe documented subject matter or process; they do not rate political importance, desirability, motive, or wrongdoing.",
    }
