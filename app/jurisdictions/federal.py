from app.jurisdictions.base import (
    NormalizedBill, NormalizedVersion, NormalizedAction,
    NormalizedSponsor, NormalizedAmendment,
)
from app.services.congress import CongressClient

class FederalCongressAdapter:
    code="US"
    name="United States Congress"
    source_system="congress"

    def source_info(self):
        return {
            "publisher":"Congress.gov / Library of Congress",
            "method":"Congress.gov API",
            "requires_api_key":True,
        }

    def fetch_bill(self,session:str,bill_type:str,number:str):
        congress=int(session)
        kind=bill_type.lower()
        number=str(number)
        client=CongressClient()
        meta=client.bill(congress,kind,number)
        payload=meta.get("bill",meta)
        tv=client.text_versions(congress,kind,number)
        raw_versions=tv.get("textVersions") or tv.get("text",{}).get("textVersions") or []

        versions=[]
        for version in raw_versions:
            raw,url,fmt=client.download_preferred_text(version)
            versions.append(NormalizedVersion(
                code=version.get("type") or version.get("typeCode") or version.get("name") or "unknown",
                name=version.get("name"),
                source_url=url,
                issued_on=version.get("date"),
                text=raw,
                format=fmt or "unknown",
            ))

        actions=[
            NormalizedAction(
                date=a.get("actionDate"),
                text=a.get("text") or "",
                code=a.get("actionCode"),
                source_url=a.get("sourceSystem",{}).get("url") if isinstance(a.get("sourceSystem"),dict) else None,
                raw=a,
            )
            for a in client.actions(congress,kind,number).get("actions",[])
            if a.get("text")
        ]

        sponsors=[]
        for sponsor in payload.get("sponsors") or []:
            sponsors.append(NormalizedSponsor(
                name=sponsor.get("fullName") or sponsor.get("name") or sponsor.get("bioguideId") or "Unknown",
                role="sponsor",
                external_id=sponsor.get("bioguideId"),
                party=sponsor.get("party"),
                state=sponsor.get("state"),
                district=sponsor.get("district"),
                raw=sponsor,
            ))
        for sponsor in client.cosponsors(congress,kind,number).get("cosponsors",[]):
            sponsors.append(NormalizedSponsor(
                name=sponsor.get("fullName") or sponsor.get("name") or sponsor.get("bioguideId") or "Unknown",
                role="cosponsor",
                external_id=sponsor.get("bioguideId"),
                party=sponsor.get("party"),
                state=sponsor.get("state"),
                district=sponsor.get("district"),
                raw=sponsor,
            ))

        amendments=[]
        for amendment in client.amendments(congress,kind,number).get("amendments",[]):
            at=(amendment.get("type") or "unknown").lower()
            an=str(amendment.get("number") or "")
            if not an:
                continue
            amendments.append(NormalizedAmendment(
                amendment_type=at,
                amendment_number=an,
                description=amendment.get("description"),
                latest_action=(amendment.get("latestAction") or {}).get("text"),
                source_url=amendment.get("url"),
                raw=amendment,
            ))

        latest=(payload.get("latestAction") or {})
        source_url=payload.get("url") or f"https://www.congress.gov/bill/{congress}th-congress/{kind}/{number}"
        return NormalizedBill(
            jurisdiction="US",
            session=str(congress),
            session_number=congress,
            bill_type=kind,
            bill_number=number,
            title=payload.get("title"),
            latest_action=latest.get("text"),
            source_url=source_url,
            source_system=self.source_system,
            metadata=payload,
            versions=versions,
            actions=actions,
            sponsors=sponsors,
            amendments=amendments,
        )
