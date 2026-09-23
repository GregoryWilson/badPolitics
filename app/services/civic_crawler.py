import hashlib
import io
import json
import re
from datetime import datetime,date,timedelta
from urllib.parse import urljoin,urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from libmuni.civicclerk import CivicClerkClient
from sqlalchemy import select

from app.models.entities import CivicDocument,CivicDocumentRevision
from app.services.civic_sources import CIVIC_SOURCES

DATE_PATTERNS=[
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b"),
]

def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8","ignore")).hexdigest()

def _clean_text(html):
    soup=BeautifulSoup(html,"lxml")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())

def _extract_date(text):
    for pattern in DATE_PATTERNS:
        match=pattern.search(text or "")
        if not match:
            continue
        a,b,c=match.groups()
        if len(a)==4:
            y,m,d=int(a),int(b),int(c)
        else:
            m,d,y=int(a),int(b),int(c)
        try:
            return datetime(y,m,d).date().isoformat()
        except ValueError:
            pass
    month_match=re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b",
        text or "",re.I,
    )
    if month_match:
        try:
            return datetime.strptime(month_match.group(0),"%B %d, %Y").date().isoformat()
        except ValueError:
            return None
    return None

def _doc_type(title,url):
    value=(title+" "+url).casefold()
    for token,label in (
        ("minutes","minutes"),("agenda","agenda"),("packet","meeting_packet"),
        ("ordinance","ordinance"),("public hearing","public_hearing"),
        ("bond","bond"),("policy","policy"),("zoning","zoning"),
        ("consolidation","consolidation"),("budget","budget"),
    ):
        if token in value:
            return label
    return "web_record"

def _relevant(text,url,source):
    value=(text+" "+url).casefold()
    return any(keyword.casefold() in value for keyword in source.get("keywords",[]))

def _allowed(url,source):
    host=(urlparse(url).hostname or "").casefold()
    return any(host==allowed.casefold() or host.endswith("."+allowed.casefold()) for allowed in source.get("allow_domains",[]))

def _fetch_text(client,url):
    response=client.get(url,timeout=45,follow_redirects=True)
    response.raise_for_status()
    ctype=(response.headers.get("content-type") or "").casefold()
    if "pdf" in ctype or urlparse(str(response.url)).path.casefold().endswith(".pdf"):
        reader=PdfReader(io.BytesIO(response.content))
        text="\n".join((page.extract_text() or "") for page in reader.pages[:250])
        return text[:1_500_000],str(response.url),"pdf"
    return _clean_text(response.text)[:1_500_000],str(response.url),"html"


def _candidate_title(soup,fallback):
    h1=soup.find("h1")
    if h1:
        value=h1.get_text(" ",strip=True)
        if value:
            return value
    if soup.title:
        value=soup.title.get_text(" ",strip=True)
        if value:
            return value
    return fallback

def _scan_seeded_pages(db,source,seeds,limit=50,follow_selector=None):
    client=httpx.Client(
        headers={
            "User-Agent":"LegisWatch/2.0 civic records monitor (+source-preserving research)",
            "Accept":"text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        },
        timeout=45,follow_redirects=True,
    )
    queue=list(seeds)
    seen=set()
    documents=[]
    changed_ids=[]
    errors=[]
    enumerated=0
    while queue and len(documents)<limit:
        url,label,depth=queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            text,final_url,fmt=_fetch_text(client,url)
            title=label or final_url
            soup=None
            if fmt=="html":
                response=client.get(final_url,timeout=45,follow_redirects=True)
                response.raise_for_status()
                soup=BeautifulSoup(response.text,"lxml")
                title=_candidate_title(soup,title)
            row,changed=_upsert(
                db,source,title,final_url,text,
                metadata={
                    "format":fmt,
                    "crawl_depth":depth,
                    "root_url":source["root_url"],
                    "source_kind":source["kind"],
                },
            )
            documents.append(row.id)
            if changed:
                changed_ids.append(row.id)
            if soup is not None and follow_selector:
                candidates=follow_selector(soup,final_url,depth)
                enumerated+=len(candidates)
                for item in candidates:
                    if item[0] not in seen and len(queue)+len(documents)<limit*4:
                        queue.append(item)
        except Exception as exc:
            errors.append({"url":url,"error":str(exc)})
    db.commit()
    client.close()
    return {
        "source_key":source["source_key"],
        "root_reached":bool(documents),
        "records_enumerated":enumerated,
        "document_count":len(documents),
        "changed_document_ids":changed_ids,
        "error_count":len(errors),
        "errors":errors[:20],
    }

def scan_boardbook_source(db,source,limit=50):
    org=str(source["organization_id"])
    def follow(soup,base,depth):
        if depth>=2:
            return []
        rows=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(base,a["href"])
            path=urlparse(href).path.casefold()
            text=a.get_text(" ",strip=True)
            if (
                f"/public/agenda/{org}" in path
                or f"/public/minutes/{org}" in path
                or f"/public/notice/{org}" in path
            ):
                rows.append((href,text or "BoardBook record",depth+1))
            elif depth>0 and (
                "attachment" in path
                or "/public/itemdownload" in path
                or "/public/download" in path
            ):
                rows.append((href,text or "BoardBook attachment",depth+1))
        # Preserve source ordering but deduplicate URLs.
        out=[]; seen=set()
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0]); out.append(row)
        return out[:max(limit*3,100)]
    return _scan_seeded_pages(
        db,source,[(source["root_url"],source["governing_body"],0)],
        limit=max(limit,75),follow_selector=follow,
    )

def scan_civicengage_archive(db,source,limit=50):
    def follow(soup,base,depth):
        if depth>=2:
            return []
        rows=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(base,a["href"])
            label=a.get_text(" ",strip=True)
            path=urlparse(href).path.casefold()
            query=urlparse(href).query.casefold()
            if (
                "/archivecenter/viewfile/item/" in path
                or "/documentcenter/view/" in path
                or path.endswith(".pdf")
                or ("archive.aspx" in path and ("amid=" in query or "aid=" in query))
            ):
                rows.append((href,label or "Sachse archive record",depth+1))
        out=[]; seen=set()
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0]); out.append(row)
        return out[:max(limit*3,100)]
    return _scan_seeded_pages(
        db,source,[(source["root_url"],source["governing_body"],0)],
        limit=max(limit,75),follow_selector=follow,
    )

def scan_dallas_notices(db,source,limit=50):
    def follow(soup,base,depth):
        if depth>=2:
            return []
        rows=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(base,a["href"])
            label=a.get_text(" ",strip=True)
            nearby=(a.parent.get_text(" ",strip=True) if a.parent else label)
            value=(label+" "+nearby+" "+href).casefold()
            if "commissioners court" in value and (
                urlparse(href).path.casefold().endswith(".pdf")
                or "assets/uploads/docs" in href.casefold()
                or "agenda" in value
            ):
                rows.append((href,label or nearby or "Dallas County Commissioners Court record",depth+1))
        out=[]; seen=set()
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0]); out.append(row)
        return out[:max(limit*3,100)]
    return _scan_seeded_pages(
        db,source,[(source["root_url"],source["governing_body"],0)],
        limit=max(limit,75),follow_selector=follow,
    )

def _arcgis_text(attrs):
    preferred=[
        "PlanZoningCase","ProjectName","NAME","Name","ProjectType","DevelopmentType",
        "Address","Location","Description","ProjectDescription",
        "ExistingZoning","CurrentZoning","RequestedZoning","ProposedZoning",
        "Status","ApprovalStatus","PZDate","PZStatus","PZResult",
        "CouncilDate","CityCouncilDate","CouncilStatus","CouncilResult",
        "Ordinance","OrdinanceNumber","CaseNumber","ZoningCase",
    ]
    technical={"objectid","globalid","created_user","created_date","last_edited_user","last_edited_date","shape","shape_length","shape_area"}
    lines=[]
    used=set()
    def label(key):
        return re.sub(r"(?<!^)(?=[A-Z])"," ",str(key)).replace("_"," ").strip()
    for key in preferred:
        if key in attrs and attrs.get(key) not in (None,"","Null","null"):
            lines.append(f"{label(key)}: {attrs[key]}")
            used.add(key)
    for key,value in attrs.items():
        if key in used or key.casefold() in technical or value in (None,"","Null","null"):
            continue
        lines.append(f"{label(key)}: {value}")
    return "\n".join(lines)

def _upsert(db,source,title,url,text,metadata=None,external_id=None):
    now=datetime.utcnow()
    external_id=external_id or hashlib.sha256(url.encode()).hexdigest()
    row=db.scalar(select(CivicDocument).where(
        CivicDocument.source_key==source["source_key"],
        CivicDocument.external_id==external_id,
    ))
    digest=_sha(text)
    changed=False
    if not row:
        row=CivicDocument(
            source_key=source["source_key"],
            jurisdiction=source["jurisdiction"],
            governing_body=source["governing_body"],
            document_type=_doc_type(title,url),
            title=title or url,
            meeting_date=_extract_date((title or "")+"\n"+(text or "")[:5000]),
            source_url=url,
            external_id=external_id,
            text=text,
            sha256=digest,
            metadata_json=metadata or {},
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row); db.flush()
        changed=True
    else:
        row.last_seen_at=now
        row.title=title or row.title
        row.meeting_date=row.meeting_date or _extract_date((title or "")+"\n"+(text or "")[:5000])
        row.document_type=_doc_type(row.title,url)
        row.metadata_json={**(row.metadata_json or {}),**(metadata or {})}
        if digest!=row.sha256:
            row.text=text
            row.sha256=digest
            changed=True
    if changed and digest:
        existing=db.scalar(select(CivicDocumentRevision).where(
            CivicDocumentRevision.civic_document_id==row.id,
            CivicDocumentRevision.sha256==digest,
        ))
        if not existing:
            db.add(CivicDocumentRevision(
                civic_document_id=row.id,
                sha256=digest,
                text=text,
                metadata_json=metadata or {},
                observed_at=now,
            ))
    db.flush()
    return row,changed

def scan_html_source(db,source,limit=50):
    client=httpx.Client(
        headers={"User-Agent":"LegisWatch civic monitor/1.0"},
        timeout=45,follow_redirects=True,
    )
    queue=[(source["root_url"],0,source["governing_body"])]
    seen=set()
    documents=[]
    changed_ids=[]
    errors=[]
    while queue and len(documents)<limit:
        url,depth,label=queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            text,final_url,fmt=_fetch_text(client,url)
            title=label
            if fmt=="html":
                response=client.get(final_url,timeout=45,follow_redirects=True)
                response.raise_for_status()
                soup=BeautifulSoup(response.text,"lxml")
                page_title=(soup.title.get_text(" ",strip=True) if soup.title else None)
                h1=soup.find("h1")
                title=(h1.get_text(" ",strip=True) if h1 else page_title) or label
                if depth<2:
                    candidates=[]
                    for a in soup.find_all("a",href=True):
                        link=urljoin(final_url,a["href"])
                        anchor=a.get_text(" ",strip=True)
                        if _allowed(link,source) and _relevant(anchor,link,source):
                            candidates.append((link,depth+1,anchor or link))
                    for item in candidates[:max(0,limit-len(documents))]:
                        if item[0] not in seen:
                            queue.append(item)
            row,changed=_upsert(
                db,source,title,final_url,text,
                metadata={"format":fmt,"crawl_depth":depth,"root_url":source["root_url"]},
            )
            documents.append(row.id)
            if changed:
                changed_ids.append(row.id)
        except Exception as exc:
            errors.append({"url":url,"error":str(exc)})
    db.commit()
    client.close()
    return {
        "source_key":source["source_key"],
        "root_reached":bool(documents),
        "records_enumerated":max(0,len(seen)-1),
        "document_count":len(documents),
        "changed_document_ids":changed_ids,
        "error_count":len(errors),
        "errors":errors[:20],
    }


def scan_civicclerk_source(db,source,limit=75):
    tenant=source["tenant"]
    documents=[]
    changed_ids=[]
    errors=[]
    enumerated=0
    from_date=date.today()-timedelta(days=730)
    to_date=date.today()+timedelta(days=180)
    try:
        with CivicClerkClient(tenant) as client:
            events=list(client.iter_events(from_date=from_date,to_date=to_date))
            events=sorted(
                events,
                key=lambda event:getattr(event,"starts_at",None) or datetime.min,
                reverse=True,
            )
            enumerated=len(events)
            for event in events:
                if len(documents)>=limit:
                    break
                event_name=getattr(event,"name",None) or "Sachse public meeting"
                starts=getattr(event,"starts_at",None)
                meeting_date=starts.date().isoformat() if hasattr(starts,"date") else None
                agenda_id=getattr(event,"agenda_id",None)
                if agenda_id and len(documents)<limit:
                    try:
                        agenda=client.get_agenda(agenda_id)
                        lines=[]
                        for item in agenda.walk_items():
                            name=getattr(item,"name",None)
                            if name:
                                lines.append(str(name).strip())
                        text="\n".join(x for x in lines if x)[:1_500_000]
                        if text:
                            row,changed=_upsert(
                                db,source,
                                f"{event_name} - Agenda",
                                f"https://{tenant}.portal.civicclerk.com/",
                                text,
                                metadata={
                                    "format":"structured_agenda",
                                    "source_kind":"civicclerk",
                                    "tenant":tenant,
                                    "agenda_id":agenda_id,
                                    "meeting_date":meeting_date,
                                },
                                external_id=f"agenda:{agenda_id}",
                            )
                            if meeting_date:
                                row.meeting_date=meeting_date
                            documents.append(row.id)
                            if changed:
                                changed_ids.append(row.id)
                    except Exception as exc:
                        errors.append({"event":event_name,"agenda_id":agenda_id,"error":str(exc)})
                for published in getattr(event,"published_files",[]) or []:
                    if len(documents)>=limit:
                        break
                    file_id=getattr(published,"file_id",None)
                    if file_id is None:
                        continue
                    file_name=(
                        getattr(published,"file_name",None)
                        or getattr(published,"name",None)
                        or getattr(published,"title",None)
                        or f"Published file {file_id}"
                    )
                    try:
                        text=client.get_file_text(file_id) or ""
                        file_url=(
                            f"https://{tenant}.api.civicclerk.com/v1/"
                            f"Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"
                        )
                        row,changed=_upsert(
                            db,source,
                            f"{event_name} - {file_name}",
                            file_url,
                            text,
                            metadata={
                                "format":"civicclerk_file",
                                "source_kind":"civicclerk",
                                "tenant":tenant,
                                "file_id":file_id,
                                "meeting_date":meeting_date,
                                "event_name":event_name,
                            },
                            external_id=f"file:{file_id}",
                        )
                        if meeting_date:
                            row.meeting_date=meeting_date
                        documents.append(row.id)
                        if changed:
                            changed_ids.append(row.id)
                    except Exception as exc:
                        errors.append({"event":event_name,"file_id":file_id,"error":str(exc)})
            db.commit()
    except Exception as exc:
        errors.append({"root_url":source["root_url"],"error":str(exc)})
    return {
        "source_key":source["source_key"],
        "root_reached":enumerated>0,
        "records_enumerated":enumerated,
        "document_count":len(documents),
        "changed_document_ids":changed_ids,
        "error_count":len(errors),
        "errors":errors[:20],
    }

def scan_arcgis_source(db,source,limit=500):
    response=httpx.get(
        source["root_url"],
        params={
            "where":"1=1",
            "outFields":"*",
            "returnGeometry":"false",
            "f":"json",
            "resultRecordCount":min(max(1,limit),2000),
            "orderByFields":"last_edited_date DESC",
        },
        timeout=45,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload=response.json()
    changed_ids=[]
    rows=[]
    for feature in payload.get("features",[]):
        attrs=feature.get("attributes") or {}
        external_id=str(attrs.get("GlobalID") or attrs.get("OBJECTID") or hashlib.sha256(json.dumps(attrs,sort_keys=True).encode()).hexdigest())
        title=(
            attrs.get("ProjectName") or attrs.get("NAME") or attrs.get("Name")
            or attrs.get("PlanZoningCase") or attrs.get("CaseNumber")
            or attrs.get("ProjectType") or f"Wylie development {external_id}"
        )
        text=_arcgis_text(attrs)
        row,changed=_upsert(
            db,source,str(title),source["root_url"],text,
            metadata={"attributes":attrs,"record_type":"arcgis_feature"},
            external_id=external_id,
        )
        rows.append(row.id)
        if changed:
            changed_ids.append(row.id)
    db.commit()
    return {
        "source_key":source["source_key"],
        "root_reached":True,
        "records_enumerated":len(payload.get("features",[])),
        "document_count":len(rows),
        "changed_document_ids":changed_ids,
        "error_count":0,
        "errors":[],
    }

def scan_civic_source(db,source_key,limit=50):
    source=next((s for s in CIVIC_SOURCES if s["source_key"]==source_key),None)
    if not source:
        raise ValueError(f"Unknown civic source: {source_key}")
    if source["kind"]=="arcgis":
        return scan_arcgis_source(db,source,limit=max(limit,500))
    if source["kind"]=="civicclerk":
        return scan_civicclerk_source(db,source,limit=max(limit,75))
    if source["kind"]=="boardbook":
        return scan_boardbook_source(db,source,limit=limit)
    if source["kind"]=="civicengage_archive":
        return scan_civicengage_archive(db,source,limit=limit)
    if source["kind"]=="dallas_notices":
        return scan_dallas_notices(db,source,limit=limit)
    return scan_html_source(db,source,limit=limit)

def scan_all_civic_sources(db,limit_per_source=50):
    results=[]
    for source in CIVIC_SOURCES:
        try:
            results.append(scan_civic_source(db,source["source_key"],limit_per_source))
        except Exception as exc:
            results.append({
                "source_key":source["source_key"],
                "document_count":0,
                "changed_document_ids":[],
                "error_count":1,
                "errors":[{"error":str(exc)}],
            })
    return results
