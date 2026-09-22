import httpx
from app.core.config import settings

SYSTEM = """You are an evidence-first legislative analyst. Never infer corrupt intent. Distinguish facts, inferences, and unknowns. Every substantive claim must cite an evidence ID supplied in the prompt. Focus on beneficiary concentration, unusual exemptions, retroactivity, enforcement limitations, scope mismatch, financial transfers, and conflicts supported by records."""

def deep_dive(title:str, section_text:str, findings:list[dict]):
    evidence = "\n".join(f"[F{i+1}] {f['kind']}: {f['evidence']}" for i,f in enumerate(findings))
    prompt=f"""Bill: {title}\n\nSection text [S1]:\n{section_text[:24000]}\n\nDeterministic findings:\n{evidence}\n\nProduce: 1) what it does, 2) who plausibly benefits, 3) why it merits review, 4) benign explanations, 5) evidence still needed. Cite [S1]/[F#]."""
    r=httpx.post(settings.llm_base_url.rstrip("/")+"/chat/completions", headers={"Authorization":f"Bearer {settings.llm_api_key}"}, json={"model":settings.llm_model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"temperature":0.1}, timeout=120)
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]
