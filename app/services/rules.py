import re
from app.services.parser import MONEY_RE, STATUTE_RE

RULES = [
    ("retroactivity", 0.80, re.compile(r"retroactive|shall apply to (?:any|all).*before|before the date of enactment", re.I), "Potential retroactive effect"),
    ("grandfather", 0.75, re.compile(r"grandfather|existing agreement|in effect on the date|entered into before", re.I), "Existing arrangement may receive special treatment"),
    ("enforcement_limit", 0.85, re.compile(r"no private right of action|may only be enforced by|exclusive authority|shall not bring an action", re.I), "Enforcement authority may be limited"),
    ("unspecified_spending", 0.65, re.compile(r"such sums as may be necessary", re.I), "Open-ended authorization language"),
    ("named_geography", 0.55, re.compile(r"\b(?:County|Parish|Borough|District|Municipality|City of|Town of)\b", re.I), "Provision contains narrow geographic language"),
    ("exemption", 0.65, re.compile(r"exempt(?:ion|ed)? from|shall not apply to|notwithstanding any other provision", re.I), "Potential exemption or override"),
]

def analyze_section(section:dict):
    text=section["text"]
    findings=[]
    for kind,severity,pat,label in RULES:
        m=pat.search(text)
        if m:
            findings.append({"kind":kind,"severity":severity,"label":label,"evidence":text[max(0,m.start()-180):m.end()+260]})
    for m in MONEY_RE.finditer(text):
        findings.append({"kind":"money","severity":0.50,"label":"Explicit monetary amount","evidence":text[max(0,m.start()-140):m.end()+180],"metadata":{"amount_text":m.group(0)}})
    refs=list(dict.fromkeys(x.group(0) for x in STATUTE_RE.finditer(text)))
    if len(refs)>=2:
        findings.append({"kind":"cross_reference_density","severity":0.45,"label":"Multiple external statutory references","evidence":"; ".join(refs[:12]),"metadata":{"references":refs[:25]}})
    return findings
