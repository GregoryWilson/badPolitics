import re
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import datetime,timedelta,date,timezone
from sqlalchemy import select,func

from app.models.entities import Bill,BillAction,BillVersion,CivicDocument,CivicDocumentRevision,CivicFinding,CivicAgendaItem,DiscoveryCursor
from app.services.civic_analysis import ACTION_RE,ITEM_RE,COMPILED_SIGNALS,agenda_section_label
from app.services.civic_sources import CIVIC_SOURCES

SOURCE_GROUPS=[
    {"id":"sachse","label":"Sachse","kind":"civic","prefixes":["sachse_"]},
    {"id":"wylie","label":"Wylie","kind":"civic","prefixes":["wylie_city_"],"source_keys":["wylie_development_projects"]},
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
    r"\b(?:ordinance|contract|agreement|resolution|budget|tax|zoning|bond|development|grant|"
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
    minutes=bool(re.search(r"\b(?:approve|approval of)\b.{0,110}\bminutes\b",subject))
    return bool((ROUTINE_AGENDA.match(subject) or minutes) and
                not SUBSTANTIVE_HINT.search(subject))

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

def _civic_category(doc,findings,item_text=None):
    priority=[
        "zoning_development","procurement_contract","budget_finance","bond_tax_debt",
        "school_facility_boundary","property_land","policy_rule","election_governance",
        "public_hearing","vote_action",
    ]
    found={f.category for f in findings}
    if item_text:
        found.update(category for category,patterns in COMPILED_SIGNALS
                     if any(pattern.search(item_text) for pattern in patterns))
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

ARCGIS_EVENT_FIELDS=("PZDate","CouncilDate","CityCouncilDate","CCDate",
                     "SubmissionDate","SubmittalDate","ApprovalDate")

def _arcgis_event_date(doc,start,end):
    attrs=(doc.metadata_json or {}).get("attributes") or {}
    dated=[]
    for field in ARCGIS_EVENT_FIELDS:
        value=attrs.get(field)
        if isinstance(value,(int,float)):
            try:
                day=datetime.fromtimestamp(value/1000 if value>10**11 else value,
                                           timezone.utc).date()
            except (OverflowError,OSError,ValueError):
                continue
        else:
            day=_parse_date(value)
        if day and start<=day<=end:
            dated.append((day,field))
    return max(dated) if dated else None

def _arcgis_synopsis(doc):
    attrs=(doc.metadata_json or {}).get("attributes") or {}
    parts=[]
    for field,label in (("ProjectDescription",None),("Description",None),
                        ("Explanation",None),("ProjectType","Type"),
                        ("DevelopmentType","Development"),("Status","Status"),
                        ("PZStatus","P&Z"),("CouncilStatus","Council")):
        value=attrs.get(field)
        if value not in (None,"","Null","null"):
            parts.append(f"{label}: {value}" if label else str(value))
    return _compact(" · ".join(parts),500)

def _source_coverage(db,group,start,end):
    if group["kind"]=="civic":
        keys=_civic_keys(group)
        count,last_seen,last_dated=db.execute(select(
            func.count(CivicDocument.id),func.max(CivicDocument.last_seen_at),
            func.max(CivicDocument.meeting_date),
        ).where(CivicDocument.source_key.in_(keys))).one()
        cursors=db.scalars(select(DiscoveryCursor).where(
            DiscoveryCursor.source_key.in_([f"civic:{key}" for key in keys]))).all()
    else:
        count,last_seen=db.execute(select(func.count(Bill.id),func.max(Bill.updated_at))
            .where(Bill.jurisdiction==group["jurisdiction"])).one()
        last_dated=db.scalar(select(func.max(BillAction.action_date)).join(Bill)
            .where(Bill.jurisdiction==group["jurisdiction"]))
        cursors=db.scalars(select(DiscoveryCursor).where(
            DiscoveryCursor.source_key.like(f"legis:{group['jurisdiction']}:%"))).all()
    discovery=[{
        "source_key":row.source_key,"status":row.status,
        "last_completed_at":row.last_completed_at.isoformat() if row.last_completed_at else None,
        "error_count":sum(int((row.cursor_json or {}).get("last_result",{}).get(name,0) or 0)
                          for name in ("error_count","failed_count","analysis_failed_count")),
    } for row in cursors]
    return {"record_count":count,"last_captured_at":last_seen.isoformat() if last_seen else None,
            "latest_dated_record":str(last_dated)[:10] if last_dated else None,
            "discovery":discovery}

def _civic_week(db,group,start,end,limit):
    keys=_civic_keys(group)
    if not keys:
        return []
    feature_keys=[key for key in keys if key=="wylie_development_projects"]
    dated_keys=[key for key in keys if key not in feature_keys]
    rows=[]
    if dated_keys:
        rows.extend(db.scalars(select(CivicDocument).where(
            CivicDocument.source_key.in_(dated_keys),
            CivicDocument.meeting_date>=start.isoformat(),
            CivicDocument.meeting_date<(end+timedelta(days=1)).isoformat(),
        ).order_by(CivicDocument.meeting_date.desc(),CivicDocument.id.desc())
          .limit(max(limit*10,500))).all())
    if feature_keys:
        rows.extend(db.scalars(select(CivicDocument)
            .where(CivicDocument.source_key.in_(feature_keys))
            .order_by(CivicDocument.id.desc()).limit(2000)).all())
    dated=[]
    for doc in rows:
        if (doc.metadata_json or {}).get("crawl_depth")==0:
            continue
        if doc.source_key in feature_keys:
            source_event=_arcgis_event_date(doc,start,end)
            if source_event:
                dated.append((doc,source_event[0],"source_event_date",source_event[1]))
        else:
            meeting=_parse_date(doc.meeting_date)
            if meeting and start<=meeting<=end:
                dated.append((doc,meeting,"meeting_date",None))
    if not dated:
        return []
    ids=[doc.id for doc,_,_,_ in dated]
    revisions={}
    for rev in db.scalars(select(CivicDocumentRevision)
            .where(CivicDocumentRevision.civic_document_id.in_(ids))
            .order_by(CivicDocumentRevision.civic_document_id,
                      CivicDocumentRevision.observed_at.desc(),CivicDocumentRevision.id.desc())):
        revisions.setdefault(rev.civic_document_id,rev)
    revision_ids=[rev.id for rev in revisions.values()]
    findings_by_doc=defaultdict(list)
    agenda_by_doc=defaultdict(list)
    if revision_ids:
        for finding in db.scalars(select(CivicFinding).where(
                CivicFinding.revision_id.in_(revision_ids)).order_by(CivicFinding.id)):
            findings_by_doc[finding.civic_document_id].append(finding)
        for agenda_item in db.scalars(select(CivicAgendaItem).where(
                CivicAgendaItem.revision_id.in_(revision_ids))
                .order_by(CivicAgendaItem.civic_document_id,CivicAgendaItem.ordinal)):
            agenda_by_doc[agenda_item.civic_document_id].append(agenda_item)
    items=[]
    for doc,event_date,date_basis,event_field in dated:
        revision=revisions.get(doc.id)
        findings=findings_by_doc[doc.id]
        agenda=agenda_by_doc[doc.id][:100]

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
                category=_civic_category(doc,linked,agenda_item.text)
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
            if event_field and category=="other_civic":
                category="zoning_development"
            # An unparsed packet/agenda is a container, not a second issue.
            if (category not in SUBSTANTIVE_CATEGORIES or
                _routine_agenda(doc.title) or _contact_heading(doc.title,doc.text or "") or
                (doc.document_type in {"agenda","minutes","meeting_packet"} and
                 len(_normal(doc.title))<45)):
                continue
            matched=[f for f in findings if f.category==category]
            action_findings=[f for f in findings if f.category=="vote_action"]
            hearing=any(f.category=="public_hearing" for f in findings)
            synopsis=(_arcgis_synopsis(doc) if event_field else
                      _compact(matched[0].evidence,500) if matched else _compact(doc.text,500))
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
                "status":(event_field.replace("Date"," date") if event_field else
                           ("official action recorded" if doc.document_type=="minutes" else "proposed action")
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
    rows=db.execute(select(BillAction,Bill).join(Bill,BillAction.bill_id==Bill.id)
        .where(Bill.jurisdiction==group["jurisdiction"],
               BillAction.action_date>=start.isoformat(),
               BillAction.action_date<(end+timedelta(days=1)).isoformat())
        .order_by(BillAction.action_date.desc(),BillAction.id.desc())
        .limit(max(limit*20,3000))).all()
    weekly=defaultdict(list)
    bills={}
    for action,bill in rows:
        if not ROUTINE_BILL_ACTION.search(action.text or ""):
            weekly[bill.id].append(action)
            bills[bill.id]=bill
    selected=list(weekly)[:limit]
    versions={}
    if selected:
        for version in db.scalars(select(BillVersion).where(BillVersion.bill_id.in_(selected))
                .order_by(BillVersion.id.desc())):
            versions.setdefault(version.bill_id,version)
    items=[]
    for bill_id in selected:
        bill=bills[bill_id]
        action=weekly[bill_id][0]
        category=_bill_topic(bill)
        version=versions.get(bill_id)
        source_url=action.source_url or (version.source_url if version else None)
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
            "action_count_this_week":len(weekly[bill_id]),
        })
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
    coverage=_source_coverage(db,group,start,end)
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
        "coverage":coverage,
        "categories":category_rows,
        "interpretation_note":"This dashboard is a source-backed activity synopsis. Categories describe documented subject matter or process; they do not rate political importance, desirability, motive, or wrongdoing.",
    }
