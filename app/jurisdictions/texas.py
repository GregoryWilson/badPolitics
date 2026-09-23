import ftplib
import io
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
import httpx

from app.core.config import settings
from app.jurisdictions.base import (
    NormalizedBill, NormalizedVersion, NormalizedAction, NormalizedSponsor,
    NormalizedDocument,
)

BILL_TYPES={
    "HB":("house_bills","HB"),
    "HCR":("house_concurrent_resolutions","HC"),
    "HJR":("house_joint_resolutions","HJ"),
    "HR":("house_resolutions","HR"),
    "SB":("senate_bills","SB"),
    "SCR":("senate_concurrent_resolutions","SC"),
    "SJR":("senate_joint_resolutions","SJ"),
    "SR":("senate_resolutions","SR"),
}
VERSION_CODES={
    "Introduced":"I",
    "Engrossed":"E",
    "Senate Committee Report":"S",
    "House Committee Report":"H",
    "Enrolled":"F",
}

class TexasTLOAdapter:
    code="TX"
    name="Texas Legislature"
    source_system="texas_tlo"

    def __init__(self):
        self.ftp_host=settings.texas_ftp_host
        self.http=httpx.Client(timeout=45,follow_redirects=True)

    def source_info(self):
        return {
            "publisher":"Texas Legislature Online / Texas Legislative Council",
            "bulk_host":self.ftp_host,
            "method":"anonymous FTP bill-history XML + official bill-text HTML",
            "official_download_help":"https://capitol.texas.gov/billlookup/filedownloads.aspx",
            "note":"Bulk data is subject to revision and is not a substitute for official versions.",
        }

    def _session(self,session:str):
        value=session.upper().strip()
        if re.fullmatch(r"\d{2}",value):
            return value+"R",int(value),value+"R"
        regular=re.fullmatch(r"(\d{2})R",value)
        if regular:
            return value,int(regular.group(1)),value
        special_label=re.fullmatch(r"(\d{2})S(\d+)",value)
        if special_label:
            legislature,special=special_label.groups()
            return legislature+special,int(legislature),value
        compact_special=re.fullmatch(r"(\d{2})(\d+)",value)
        if compact_special:
            legislature,special=compact_special.groups()
            return value,int(legislature),f"{legislature}S{special}"
        raise ValueError("Texas session must look like 89R, 892, or 89S2.")

    def _bill_parts(self,bill_type:str,number:str):
        kind=bill_type.upper().replace(" ","")
        if kind not in BILL_TYPES:
            raise ValueError(f"Unsupported Texas bill type: {bill_type}")
        n=int(number)
        if n<1:
            raise ValueError("Bill number must be positive")
        folder,prefix=BILL_TYPES[kind]
        low=(n//100)*100
        if low==0:
            low=1
            high=99
        else:
            high=low+99
        group=f"{prefix}{low:05d}_{prefix}{high:05d}"
        filename=f"{prefix}{n:05d}.xml"
        return kind,str(n),folder,prefix,group,filename

    def _history_path(self,session,bill_type,number):
        session_code,_,_=self._session(session)
        _,_,folder,_,group,filename=self._bill_parts(bill_type,number)
        return f"/bills/{session_code}/billhistory/{folder}/{group}/{filename}"

    def _ftp_bytes(self,path:str):
        last=None
        for attempt in range(3):
            try:
                ftp=ftplib.FTP(self.ftp_host,timeout=30)
                ftp.login()
                buf=io.BytesIO()
                ftp.retrbinary(f"RETR {path}",buf.write)
                ftp.quit()
                return buf.getvalue()
            except Exception as exc:
                last=exc
                time.sleep(2**attempt)
        raise RuntimeError(f"Texas FTP retrieval failed for {path}: {last}")

    def _download_text(self,url:str):
        safe=url.replace("http://capitol.texas.gov/","https://capitol.texas.gov/")
        response=self.http.get(safe)
        response.raise_for_status()
        return response.text,safe

    @staticmethod
    def _iso_date(value):
        if not value:
            return None
        value=value.strip()
        for fmt in ("%m/%d/%Y","%Y-%m-%d"):
            try:
                return datetime.strptime(value,fmt).date().isoformat()
            except ValueError:
                pass
        return value

    @staticmethod
    def _split_people(value):
        return [x.strip() for x in (value or "").split(" | ") if x.strip()]

    @staticmethod
    def _bill_from_history_filename(value:str):
        name=value.replace("\\","/").split("/")[-1].upper()
        match=re.search(r"^(HB|HR|HC|HJ|SB|SR|SC|SJ)(\d{5})\.XML$",name)
        if not match:
            return None
        prefix,number=match.groups()
        kind={
            "HB":"HB","HR":"HR","HC":"HCR","HJ":"HJR",
            "SB":"SB","SR":"SR","SC":"SCR","SJ":"SJR",
        }[prefix]
        return {"bill_type":kind,"number":str(int(number)),"filename":name}

    def parse_history_index(self,raw:bytes,limit:int=10000):
        text=raw.decode("utf-8","ignore")
        found=[]
        seen=set()
        for match in re.finditer(r"(?:[A-Za-z0-9_./\\-]*)(?:HB|HR|HC|HJ|SB|SR|SC|SJ)\d{5}\.xml",text,re.I):
            parsed=self._bill_from_history_filename(match.group(0))
            if not parsed:
                continue
            key=(parsed["bill_type"],parsed["number"])
            if key in seen:
                continue
            seen.add(key)
            found.append(parsed)
            if len(found)>=limit:
                return found
        for match in re.finditer(r"\b(HB|HCR|HJR|HR|SB|SCR|SJR|SR)\s*0*(\d{1,5})\b",text,re.I):
            kind,number=match.groups()
            key=(kind.upper(),str(int(number)))
            if key in seen:
                continue
            seen.add(key)
            found.append({"bill_type":key[0],"number":key[1],"filename":None})
            if len(found)>=limit:
                break
        return found

    def discover_bills(self,session:str,limit:int=100,offset:int=0):
        session_code,session_number,session_label=self._session(session)
        raw=self._ftp_bytes(f"/bills/{session_code}/billhistory/history.xml")
        all_bills=self.parse_history_index(raw,limit=100000)
        offset=max(0,int(offset))
        limit=max(1,min(limit,500))
        bills=all_bills[offset:offset+limit]
        return {
            "jurisdiction":"TX",
            "session":session_label,
            "session_number":session_number,
            "source_url":f"ftp://{self.ftp_host}/bills/{session_code}/billhistory/history.xml",
            "bills":bills,
            "offset":offset,
            "total":len(all_bills),
            "next_offset":offset+len(bills) if offset+len(bills)<len(all_bills) else None,
        }

    def _documents(self,root):
        documents=[]
        for path,document_type in (
            ("billtext/docTypes/analysis/versions/version","bill_analysis"),
            ("billtext/docTypes/fiscalNote/versions/version","fiscal_note"),
        ):
            for version in root.iterfind(path):
                desc=(version.findtext("versionDescription") or "").strip() or None
                html_url=(version.findtext("WebHTMLURL") or "").strip()
                pdf_url=(version.findtext("WebPDFURL") or "").strip()
                if not html_url and not pdf_url:
                    continue
                text=None
                if html_url:
                    try:
                        text,source_url=self._download_text(html_url)
                    except Exception:
                        source_url=html_url.replace("http://capitol.texas.gov/","https://capitol.texas.gov/")
                    fmt="html"
                else:
                    source_url=pdf_url.replace("http://capitol.texas.gov/","https://capitol.texas.gov/")
                    fmt="pdf"
                documents.append(NormalizedDocument(
                    document_type=document_type,
                    description=desc,
                    source_url=source_url,
                    text=text,
                    format=fmt,
                    metadata={"texas_version_description":desc},
                ))
        return documents

    def fetch_bill(self,session:str,bill_type:str,number:str):
        session_code,session_number,session_label=self._session(session)
        kind,number,_,_,_,_=self._bill_parts(bill_type,number)
        history_path=self._history_path(session_code,kind,number)
        raw=self._ftp_bytes(history_path)
        root=ET.fromstring(raw)

        caption=root.findtext("caption")
        if not caption or b"Bill does not exist" in raw:
            raise ValueError(f"Texas bill not found: {session_code} {kind} {number}")

        official_page=(
            "https://capitol.texas.gov/BillLookup/History.aspx?"
            f"LegSess={session_code}&Bill={kind}{number}"
        )
        versions=[]
        for version in root.iterfind("billtext/docTypes/bill/versions/version"):
            desc=(version.findtext("versionDescription") or "").strip() or None
            url=(version.findtext("WebHTMLURL") or "").strip()
            if not url:
                continue
            try:
                text,source_url=self._download_text(url)
            except Exception:
                text=None
                source_url=url.replace("http://capitol.texas.gov/","https://capitol.texas.gov/")
            match=re.search(r"([ISEHF])\.(?:HTM|HTML)$",source_url,re.I)
            code=(match.group(1).upper() if match else VERSION_CODES.get(desc or "",desc or "unknown"))
            versions.append(NormalizedVersion(
                code=code,
                name=desc,
                source_url=source_url,
                text=text,
                format="html",
            ))

        actions=[]
        latest_action=None
        latest_date=""
        for action in root.findall("actions/action"):
            date=self._iso_date(action.findtext("date"))
            description=(action.findtext("description") or "").strip()
            code=(action.findtext("actionNumber") or "").strip() or None
            if not description:
                continue
            actions.append(NormalizedAction(
                date=date,
                text=description,
                code=code,
                source_url=official_page,
                raw={"actor_code":code[:1] if code else None},
            ))
            if (date or "")>=latest_date:
                latest_date=date or latest_date
                latest_action=description

        sponsors=[]
        seen=set()
        for tag,role in (
            ("authors","sponsor"),
            ("coauthors","cosponsor"),
            ("sponsors","sponsor"),
            ("cosponsors","cosponsor"),
        ):
            for name in self._split_people(root.findtext(tag)):
                key=(name.casefold(),role)
                if key in seen:
                    continue
                seen.add(key)
                sponsors.append(NormalizedSponsor(
                    name=name,
                    role=role,
                    raw={"texas_role_source":tag},
                ))

        subjects=[
            (subject.text or "").strip()
            for subject in root.iterfind("subjects/subject")
            if (subject.text or "").strip()
        ]
        metadata={
            "session":session_code,
            "identifier":f"{kind} {number}",
            "history_ftp_url":f"ftp://{self.ftp_host}{history_path}",
            "subjects":subjects,
            "source_notice":"Texas bulk legislative data is subject to revision.",
        }
        return NormalizedBill(
            jurisdiction=self.code,
            session=session_label,
            session_number=session_number,
            bill_type=kind.lower(),
            bill_number=number,
            title=caption.strip(),
            latest_action=latest_action,
            source_url=official_page,
            source_system=self.source_system,
            metadata=metadata,
            versions=versions,
            actions=actions,
            sponsors=sponsors,
            documents=self._documents(root),
        )
