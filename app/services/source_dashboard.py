import re
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import datetime,timedelta,date
from sqlalchemy import select

from app.models.entities import Bill,BillAction,BillVersion,CivicDocument,CivicDocumentRevision,CivicFinding,CivicAgendaItem
from app.services.civic_analysis import ACTION_RE,ITEM_RE,agenda_section_label
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

# Meeting procedure is useful in the source record, but it is not a weekly issue.
ROUTINE_AGENDA=re.compile(
    r"^(?:call to order|roll call|establish(?:ment of)? (?:a )?quorum|"
    r"invocation|pledge(?: of allegiance)?|opening (?:prayer|remarks)|"
    r"approval of (?:the )?(?:agenda|minutes)|approve (?:the )?(?:agenda|minutes)|"
    r"consent agenda|public (?:comment|forum|participation)|citizen(?:s|) (?:comment|forum)|"
    r"announcements?|recognitions?|presentations?|staff reports?|"
    r"board reports?|committee reports?|future agenda items?|"
    r"(?:old|new|unfinished) business|(?:discussion|action|information) items?|"
    r"executive (?:session|closed session)|reconvene|adjourn(?:ment)?)\b",
    re.I,
)
ROUTINE_BILL_ACTION=re.compile(
    r"\b(?:cosponsor(?:s)? added|text (?:received|available)|"
    r"read (?:the )?(?:first|second|third) time|held at the desk|"
    r"received in the (?:house|senate)|message on (?:house|senate) action)\b",
    re.I,
)
SUBSTANTIVE_HINT=re.compile(
    r"\b(?:ordinance|contract|budget|tax|zoning|bond|development|grant|"
    r"policy|school|construction|property|project|hearing|election)\b",re.I,
)
SUBSTANTIVE_CATEGORIES=set(CATEGORY_LABELS)-{"other_civic","vote_action","public_hearing"}
CONTACT_HEADING=re.compile(
    r"^(?:contact us|hours|phone|fax|helpful links|meeting location|"
    r"(?:\d{3,5}\s+)?sachse\s+(?:road|rd)(?:\s+building\s+b)?|"
    r"sachse\s+(?:tx|texas)\s+75048)$",re.I,
)

def _normal(text):
    value=re.sub(r"^\s*(?:item\s+)?(?:\d+(?:\.\d+)*[a-z]?|[a-z])\s*[.): -]+", "",text or "",flags=re.I)
    return " ".join(re.findall(r"[\w]+",value.casefold()))

def _routine_agenda(heading):
    # Match the heading, not the entire item: a specific contract in the body
    # of a consent item still merits display when it was extracted separately.
    subject=_normal(heading)
    return bool(ROUTINE_AGENDA.match(subject) and not SUBSTANTIVE_HINT.search(subject))

def _contact_heading(heading,body):
    subject=_normal(heading)
    return bool(CONTACT_HEADING.fullmatch(subject) or
                ("3815 sachse" in _normal(body) and
                 subject in {"sachse road building b","sachse rd building b","3815"}))

def _sections_in_text(text):
    # Recover section names for agenda items analyzed before this feature was
    # added. The headings are matched to the original revision, in source order.
    sections=defaultdict(list)
    current=None
    for line in (text or "").splitlines():
        line=line.strip()
        match=ITEM_RE.match(line)
        if match:
            number,heading=match.groups()
            current=agenda_section_label(number,heading) or current
            if not agenda_section_label(number,heading):
                sections[_normal(heading)].append(current)
        elif agenda_section_label("A",line):
            current=line
        elif ACTION_RE.match(line):
            sections[_normal(line)].append(current)
    return sections

def _issue_key(item):
    subject=_normal(item["title"])
    if len(subject)<25 or subject in {"agenda","minutes","meeting packet","discussion and possible action"}:
        subject=_normal(item["synopsis"])
    for _ in range(2):
        subject=re.sub(r"^(?:(?:consider|discuss)(?: and (?:take )?action on)?|"
                       r"approval of|approve|adoption of|adopt|authorization of|authorize)\s+(?:the\s+)?",
                       "",subject)
    return subject

def _dedupe_civic(items,limit):
    # Keep distinct meetings and distinct issues within a meeting. Documents
    # from multiple feeds may still describe the same item on that date.
    chosen=[]
    keys=defaultdict(list)
    for item in items:
        subject=_issue_key(item)
        if not subject:
            continue
        bucket=(item["date"],item["institution"])
        duplicate=None
        for existing in keys[bucket]:
            other=_issue_key(existing)
            same_body=(len(_normal(item["synopsis"]))>=60 and
                       _normal(item["synopsis"])==_normal(existing["synopsis"]))
            if (subject==other or same_body or
                (min(len(subject),len(other))>=40 and
                 SequenceMatcher(None,subject,other).ratio()>=0.94)):
                duplicate=existing
                break
        if duplicate is None:
            keys[bucket].append(item)
            chosen.append(item)
        elif ((item["status"]=="official action recorded",item["category"] in SUBSTANTIVE_CATEGORIES,
               len(item["synopsis"])) >
              (duplicate["status"]=="official action recorded",duplicate["category"] in SUBSTANTIVE_CATEGORIES,
               len(duplicate["synopsis"]))):
            chosen[chosen.index(duplicate)]=item
            keys[bucket][keys[bucket].index(duplicate)]=item
    return chosen[:limit]

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
        .limit(max(limit*10,500))
    ).all()
    items=[]
    for doc in rows:
        # Crawler seed/index pages contain navigation and often a date from an
        # unrelated link. They are not themselves a dated civic decision.
        if (doc.metadata_json or {}).get("crawl_depth")==0:
            continue
        revision=db.scalar(
            select(CivicDocumentRevision)
            .where(CivicDocumentRevision.civic_document_id==doc.id)
            .order_by(CivicDocumentRevision.observed_at.desc(),CivicDocumentRevision.id.desc())
        )
        meeting=_parse_date(doc.meeting_date)
        is_feature=(doc.metadata_json or {}).get("record_type")=="arcgis_feature"
        changed=(revision.observed_at.date() if revision and revision.observed_at else
                 doc.first_seen_at.date() if doc.first_seen_at else None)
        if is_feature and changed and start<=changed<=end:
            event_date=changed
            date_basis="updated_this_week"
        elif is_feature:
            continue
        elif meeting:
            if not (start<=meeting<=end):
                continue
            event_date=meeting
            date_basis="meeting_date"
        else:
            continue
        revision_id=revision.id if revision else None
        findings=db.scalars(
            select(CivicFinding)
            .where(
                CivicFinding.civic_document_id==doc.id,
                CivicFinding.revision_id==revision_id,
            )
            .order_by(CivicFinding.id)
        ).all()
        agenda=db.scalars(
            select(CivicAgendaItem)
            .where(
                CivicAgendaItem.civic_document_id==doc.id,
                CivicAgendaItem.revision_id==revision_id,
            )
            .order_by(CivicAgendaItem.ordinal)
            .limit(100)
        ).all()

        if agenda:
            section=None
            legacy_sections=_sections_in_text(revision.text if revision else doc.text)
            for agenda_item in agenda:
                item_title=agenda_item.heading or _compact(agenda_item.text,180) or doc.title
                header=agenda_section_label(agenda_item.item_number,item_title)
                if header:
                    section=header
                    continue
                matched_sections=legacy_sections.get(_normal(item_title),[])
                if matched_sections:
                    section=matched_sections.pop(0) or section
                section=(agenda_item.metadata_json or {}).get("agenda_section") or section
                if (_contact_heading(item_title,agenda_item.text) or
                    _routine_agenda(item_title)):
                    continue
                linked=[f for f in findings if f.agenda_item_id==agenda_item.id]
                category=_civic_category(doc,linked)
                # A stray numbered line from a scraped page is not an agenda issue.
                if (category=="other_civic" and
                    (len(_normal(agenda_item.text))<35 or
                     not (ACTION_RE.match(item_title) or SUBSTANTIVE_HINT.search(item_title)))):
                    continue
                action=any(f.category=="vote_action" for f in linked)
                hearing=any(f.category=="public_hearing" for f in linked)
                status=("official action recorded" if doc.document_type=="minutes" else "proposed action") if action else (
                    "public hearing" if hearing else "agenda item")
                items.append({
                    "kind":"civic",
                    "record_id":doc.id,
                    "agenda_item_id":agenda_item.id,
                    "source_key":doc.source_key,
                    "institution":group["label"],
                    "category":category,
                    "category_label":CATEGORY_LABELS[category],
                    "title":item_title,
                    "parent_title":doc.title,
                    "agenda_section":section,
                    "date":event_date.isoformat(),
                    "date_basis":date_basis,
                    "status":status,
                    "synopsis":_compact(agenda_item.text,500),
                    "source_url":doc.source_url,
                    "governing_body":doc.governing_body,
                    "evidence_count":len(linked),
                    "agenda_item_count":1,
                })
        else:
            category=_civic_category(doc,findings)
            # An unparsed packet/agenda is a container, not a second issue.
            if (category not in SUBSTANTIVE_CATEGORIES or
                _routine_agenda(doc.title) or _contact_heading(doc.title,doc.text or "") or
                (doc.document_type in {"agenda","minutes","meeting_packet"} and
                 len(_normal(doc.title))<45)):
                continue
            matched=[f for f in findings if f.category==category]
            action_findings=[f for f in findings if f.category=="vote_action"]
            hearing=any(f.category=="public_hearing" for f in findings)
            synopsis=_compact(matched[0].evidence,500) if matched else _compact(doc.text,500)
            items.append({
                "kind":"civic",
                "record_id":doc.id,
                "agenda_item_id":None,
                "source_key":doc.source_key,
                "institution":group["label"],
                "category":category,
                "category_label":CATEGORY_LABELS[category],
                "title":doc.title,
                "parent_title":None,
                "date":event_date.isoformat(),
                "date_basis":date_basis,
                "status":(("official action recorded" if doc.document_type=="minutes" else "proposed action")
                          if action_findings else ("public hearing" if hearing else doc.document_type.replace("_"," "))),
                "synopsis":synopsis or "Official source record captured for this week.",
                "source_url":doc.source_url,
                "governing_body":doc.governing_body,
                "evidence_count":len(findings),
                "agenda_item_count":0,
            })
    return _dedupe_civic(items,limit)

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
    if "referred" in value:
        return "referred"
    if "introduced" in value or "filed" in value:
        return "introduced / filed"
    if "reported" in value or "committee" in value:
        return "committee action"
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
        weekly=[a for a in actions if (_parse_date(a.action_date) and start<=_parse_date(a.action_date)<=end)
                and not ROUTINE_BILL_ACTION.search(a.text or "")]
        if not weekly:
            continue
        action=weekly[0]
        category=_bill_topic(bill)
        source_url=action.source_url
        if not source_url:
            version=db.scalar(
                select(BillVersion)
                .where(BillVersion.bill_id==bill.id)
                .order_by(BillVersion.id.desc())
            )
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
