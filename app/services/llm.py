import httpx
from app.core.config import settings

SYSTEM = """You are an evidence-first legislative analyst. Never infer corrupt intent. Distinguish facts, inferences, and unknowns. Every substantive claim must cite an evidence ID supplied in the prompt. Focus on beneficiary concentration, unusual exemptions, retroactivity, enforcement limitations, scope mismatch, financial transfers, and conflicts supported by records."""

def deep_dive(title:str, section_text:str, findings:list[dict]):
    evidence = "\n".join(f"[F{i+1}] {f['kind']}: {f['evidence']}" for i,f in enumerate(findings))
    prompt=f"""Bill: {title}\n\nSection text [S1]:\n{section_text[:24000]}\n\nDeterministic findings:\n{evidence}\n\nProduce: 1) what it does, 2) who plausibly benefits, 3) why it merits review, 4) benign explanations, 5) evidence still needed. Cite [S1]/[F#]."""
    r=httpx.post(settings.llm_base_url.rstrip("/")+"/chat/completions", headers={"Authorization":f"Bearer {settings.llm_api_key}"}, json={"model":settings.llm_model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"temperature":0.1}, timeout=120)
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]


PACKET_SYSTEM = """You are an evidence-first legislative synthesis assistant. Use only the evidence entries supplied in the packet. Do not infer corrupt intent, quid pro quo, improper motive, authorship, causation, or conflict unless an evidence entry explicitly establishes that fact. Every factual or relational claim must cite one or more evidence IDs exactly as provided, such as [S1] or [C2]. Clearly distinguish facts, plausible interpretations, benign explanations, and unknowns."""

def synthesize_evidence_packet(packet:dict):
    lines=[]
    for item in packet.get("evidence",[]):
        evidence=(item.get("evidence") or "")[:5000]
        lines.append(
            f'[{item["evidence_id"]}] {item["kind"]}: {item["summary"]}\n'
            f'Evidence: {evidence}\n'
            f'Metadata: {item.get("metadata") or {}}'
        )
    evidence_text="\n\n".join(lines)
    section=packet.get("section") or {}
    bill=packet.get("bill") or {}
    prompt=f"""Bill: {bill.get("bill_type","").upper()} {bill.get("bill_number","")} — {bill.get("title","")}
Section: {section.get("number")} {section.get("heading") or ""}

Evidence packet:
{evidence_text[:60000]}

Write a concise synthesis with these headings:
1. What the provision does
2. Why it surfaced for review
3. Version/amendment context
4. Beneficiaries and external-record context
5. Fiscal/document context
6. Benign explanations
7. Evidence still needed

Rules:
- Cite every factual or relational sentence with evidence IDs.
- Do not call anything corrupt, hidden, improper, a conflict, or a rider as a conclusion.
- Candidate amendment associations are not proven authorship.
- External correlations are record links, not proof of influence.
- Bill-level fiscal context must not be attributed specifically to this section unless the evidence entry says it is section-specific.
- If evidence is absent for a heading, say that the packet does not establish it."""
    r=httpx.post(
        settings.llm_base_url.rstrip("/")+"/chat/completions",
        headers={"Authorization":f"Bearer {settings.llm_api_key}"},
        json={
            "model":settings.llm_model,
            "messages":[
                {"role":"system","content":PACKET_SYSTEM},
                {"role":"user","content":prompt},
            ],
            "temperature":0.05,
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
