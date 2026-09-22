from app.jurisdictions import get_adapter, list_adapters
from app.jurisdictions.texas import TexasTLOAdapter

TEXAS_XML=b"""<?xml version="1.0"?>
<bill bill="89R HB 9">
  <caption>Relating to a test tax exemption.</caption>
  <authors>Smith | Jones</authors>
  <coauthors>Garcia</coauthors>
  <sponsors>Brown</sponsors>
  <cosponsors>White</cosponsors>
  <subjects><subject>Taxation</subject></subjects>
  <billtext>
    <docTypes>
      <bill>
        <versions>
          <version>
            <versionDescription>Introduced</versionDescription>
            <WebHTMLURL>http://capitol.texas.gov/tlodocs/89R/billtext/html/HB00009I.HTM</WebHTMLURL>
          </version>
        </versions>
      </bill>
    </docTypes>
  </billtext>
  <actions>
    <action>
      <date>01/02/2025</date>
      <actionNumber>H001</actionNumber>
      <description>Filed</description>
    </action>
  </actions>
</bill>
"""

def test_builtin_registry_contains_federal_and_texas():
    codes={x["code"] for x in list_adapters()}
    assert {"US","TX"}.issubset(codes)
    assert get_adapter("tx").code=="TX"

def test_texas_history_path():
    adapter=TexasTLOAdapter()
    assert adapter._history_path("89R","HB","9")==(
        "/bills/89R/billhistory/house_bills/HB00001_HB00099/HB00009.xml"
    )
    assert adapter._history_path("89R","SB","1109")==(
        "/bills/89R/billhistory/senate_bills/SB01100_SB01199/SB01109.xml"
    )

def test_texas_xml_normalization(monkeypatch):
    adapter=TexasTLOAdapter()
    monkeypatch.setattr(adapter,"_ftp_bytes",lambda path:TEXAS_XML)
    monkeypatch.setattr(
        adapter,
        "_download_text",
        lambda url:(
            "<html><body>SECTION 1. This Act applies.</body></html>",
            url.replace("http://","https://"),
        ),
    )
    bill=adapter.fetch_bill("89R","HB","9")
    assert bill.jurisdiction=="TX"
    assert bill.session=="89R"
    assert bill.session_number==89
    assert bill.bill_type=="hb"
    assert bill.bill_number=="9"
    assert bill.title=="Relating to a test tax exemption."
    assert bill.latest_action=="Filed"
    assert bill.versions[0].code=="I"
    assert bill.actions[0].date=="2025-01-02"
    assert {s.name for s in bill.sponsors}=={"Smith","Jones","Garcia","Brown","White"}
    assert bill.metadata["subjects"]==["Taxation"]
