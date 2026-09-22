import re
from bs4 import BeautifulSoup

SEC_RE = re.compile(r"(?im)^\s*(?:SEC\.|SECTION)\s+(\d+[A-Z]?(?:[-.]\d+)*)[.\s—-]*(.*)$")
MONEY_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.\d+)?)\s*(million|billion|thousand)?", re.I)
STATUTE_RE = re.compile(r"\b(?:title\s+\d+|\d+\s+U\.S\.C\.|Public Law\s+\d+[–-]\d+|section\s+\d+[A-Za-z0-9()\-]*)", re.I)

def normalize_text(raw:str) -> str:
    if "<" in raw and ">" in raw:
        soup = BeautifulSoup(raw, "lxml")
        return "\n".join(x.strip() for x in soup.stripped_strings)
    return raw.replace("\r\n","\n")

def split_sections(text:str):
    matches = list(SEC_RE.finditer(text))
    if not matches: return [{"number":"ROOT","heading":None,"text":text,"ordinal":0}]
    out=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        out.append({"number":m.group(1),"heading":m.group(2).strip() or None,"text":text[m.start():end].strip(),"ordinal":i})
    return out
