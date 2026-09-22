const state={bills:[],selected:null,report:null};

const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const safeUrl=v=>{
  try{
    const u=new URL(String(v||""),window.location.origin);
    return (u.protocol==="http:"||u.protocol==="https:")?u.href:"";
  }catch{return ""}
};
const fmtMoney=n=>{
  const v=Number(n||0);
  if(v>=1e9)return "$"+(v/1e9).toFixed(2)+"B";
  if(v>=1e6)return "$"+(v/1e6).toFixed(2)+"M";
  if(v>=1e3)return "$"+(v/1e3).toFixed(1)+"K";
  return "$"+v.toLocaleString();
};
const api=async(url,opts={})=>{
  const r=await fetch(url,{headers:{"Content-Type":"application/json"},...opts});
  if(!r.ok){
    let detail=r.statusText;
    try{const j=await r.json();detail=j.detail||detail}catch{}
    throw new Error(detail);
  }
  return r.json();
};
const status=(msg,cls="")=>{$("statusLine").className="status-line "+cls;$("statusLine").textContent=msg||""};

async function loadBills(){
  status("Loading bills…");
  try{
    state.bills=await api("/bills");
    renderBillList();
    status("");
  }catch(e){status("Unable to load bills: "+e.message,"error")}
}
function renderBillList(){
  const q=$("billSearch").value.trim().toLowerCase();
  const rows=state.bills.filter(b=>!q||[b.title,b.bill_type,b.bill_number,b.latest_action].join(" ").toLowerCase().includes(q));
  $("billList").innerHTML=rows.map(b=>`
    <div class="bill-item ${state.selected?.id===b.id?"selected":""}" data-id="${b.id}">
      <div class="bill-number">${esc(b.bill_type.toUpperCase())} ${esc(b.bill_number)} · Congress ${esc(b.congress)}</div>
      <div class="bill-item-title">${esc(b.title||"Untitled bill")}</div>
      <div class="bill-item-action">${esc(b.latest_action||"No latest action recorded")}</div>
    </div>`).join("")||'<div class="notice">No bills match this filter.</div>';
  document.querySelectorAll(".bill-item").forEach(el=>el.onclick=()=>selectBill(Number(el.dataset.id)));
}

async function selectBill(id){
  const bill=state.bills.find(b=>b.id===id); if(!bill)return;
  state.selected=bill; state.report=null; renderBillList();
  $("emptyState").hidden=true;$("billView").hidden=false;
  $("billIdLine").textContent=`${bill.bill_type.toUpperCase()} ${bill.bill_number} · Congress ${bill.congress}`;
  $("billTitle").textContent=bill.title||"Untitled bill";
  $("latestAction").textContent=bill.latest_action||"No latest action recorded.";
  $("report").innerHTML='<div class="notice">Build an investigation report to populate this tab.</div>';
  status("Loading bill details…");
  await Promise.allSettled([loadMetrics(),loadFindings(),loadTimeline(),loadDiff(),loadGraph()]);
  status("");
}
async function loadMetrics(){
  const m=await api(`/bills/${state.selected.id}/metrics`);
  const cards=[
    ["Sections",m.section_count],
    ["Words",Number(m.word_count).toLocaleString()],
    ["Explicit $ mentions",m.money.explicit_amount_mentions],
    ["Largest $ mention",fmtMoney(m.money.largest_explicit_amount)],
    ["Exemptions",m.policy_mechanics.exemption_mentions],
    ["Retroactivity",m.policy_mechanics.retroactivity_mentions],
    ["Beneficiary classes",m.specificity.beneficiary_class_links],
    ["Amendments",m.legislative_activity.amendment_count],
  ];
  $("metricCards").innerHTML=cards.map(([l,v])=>`<div class="metric"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div></div>`).join("");
}
async function loadFindings(){
  const rows=await api(`/bills/${state.selected.id}/findings`);
  $("findings").innerHTML=rows.length?rows.map(f=>`
    <article class="card">
      <h3>${esc(f.label)}</h3>
      <div class="meta"><span class="badge">${esc(f.kind)}</span><span>Section ${esc(f.section)}</span><span>Signal strength ${esc(Number(f.severity).toFixed(2))}</span><span>Version ${esc(f.version)}</span></div>
      <div class="evidence">${esc(f.evidence)}</div>
    </article>`).join(""):'<div class="notice">No deterministic findings stored for this bill.</div>';
}
async function loadTimeline(){
  const t=await api(`/bills/${state.selected.id}/timeline`);
  $("timeline").innerHTML=`
    <h3 class="section-title">Sponsors & cosponsors</h3>
    ${t.sponsors.map(s=>`<div class="card"><strong>${esc(s.name)}</strong><div class="meta"><span>${esc(s.role)}</span><span>${esc(s.party||"")}</span><span>${esc(s.state||"")}${s.district?"-"+esc(s.district):""}</span></div></div>`).join("")||'<div class="notice">No sponsor records.</div>'}
    <h3 class="section-title">Actions</h3>
    ${t.actions.map(a=>`<div class="card"><strong>${esc(a.date||"Undated")}</strong><div>${esc(a.text)}</div></div>`).join("")||'<div class="notice">No action records.</div>'}
    <h3 class="section-title">Amendments</h3>
    ${t.amendments.map(a=>`<div class="card"><strong>${esc(a.type.toUpperCase())} ${esc(a.number)}</strong><div>${esc(a.description||a.latest_action||"")}</div></div>`).join("")||'<div class="notice">No amendment records.</div>'}
  `;
}
async function loadDiff(){
  try{
    const d=await api(`/bills/${state.selected.id}/diff/latest`);
    $("diff").innerHTML=`
      <div class="card"><strong>${esc(d.old)} → ${esc(d.new)}</strong>
      <div class="meta"><span>+${esc(d.summary.added_lines)} lines</span><span>−${esc(d.summary.removed_lines)} lines</span><span>${esc(d.summary.changed_lines)} changed</span><span>Similarity ${esc(d.summary.similarity)}</span></div></div>
      <pre>${esc(d.diff)}</pre>`;
  }catch(e){
    $("diff").innerHTML='<div class="notice">No version diff is available yet.</div>';
  }
}
async function loadGraph(){
  const g=await api(`/bills/${state.selected.id}/graph?depth=2`);
  $("graph").innerHTML=`
    <h3 class="section-title">Bill-linked entities</h3>
    ${g.nodes.map(n=>`<div class="card"><strong>${esc(n.name)}</strong><div class="meta"><span class="badge">${esc(n.type)}</span></div></div>`).join("")||'<div class="notice">No graph entities yet.</div>'}
    <h3 class="section-title">Source-backed relationships</h3>
    ${g.relationships.map(r=>`<div class="card"><strong>${esc(r.source_entity.name)} → ${esc(r.relation_type)} → ${esc(r.target_entity.name)}</strong><div class="meta"><span>${esc(r.source_system)}</span><span>${esc(r.observed_on||"")}</span></div><div class="evidence">${esc(r.evidence)}</div>${safeUrl(r.source_url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(r.source_url))}">Source</a>`:""}</div>`).join("")||'<div class="notice">No external relationships imported yet.</div>'}
  `;
}
async function runResearch(){
  if(!state.selected)return;
  status("Running conservative external research…");
  $("runResearch").disabled=true;
  try{
    const result=await api(`/bills/${state.selected.id}/research`,{method:"POST",body:JSON.stringify({})});
    status(`Research run ${result.run.id}: ${result.run.status}`,"success");
    await loadGraph();
  }catch(e){status("Research failed: "+e.message,"error")}
  finally{$("runResearch").disabled=false}
}
async function buildReport(){
  if(!state.selected)return;
  status("Building investigation report…");
  $("buildReport").disabled=true;
  try{
    state.report=await api(`/bills/${state.selected.id}/reports`,{method:"POST"});
    renderReport(state.report);
    activateTab("report");
    status(`Report ${state.report.report_id} created.`,"success");
  }catch(e){status("Report failed: "+e.message,"error")}
  finally{$("buildReport").disabled=false}
}
function renderReport(r){
  $("report").innerHTML=`
    <div class="notice">${esc(r.interpretation_note)}</div>
    <div class="card"><strong>Report ${esc(r.report_id)}</strong><div class="meta"><span>${esc(r.finding_summary.total)} findings</span><span>Version ${esc(r.version.code||"n/a")}</span><span>${esc(r.research?.status||"No research run")}</span></div></div>
    ${r.findings.map(f=>`<article class="card">
      <h3>${esc(f.title)}</h3>
      <div class="meta"><span class="badge">${esc(f.category)}</span><span>Confidence ${esc(Number(f.confidence).toFixed(2))}</span>${f.section?`<span>Section ${esc(f.section)}</span>`:""}</div>
      <div>${esc(f.statement)}</div>
      <div class="evidence">${esc(f.evidence)}</div>
      <div class="meta">${f.sources.map(s=>safeUrl(s.url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(s.url))}">${esc(s.type)} #${esc(s.id)}</a>`:`<span>${esc(s.type)} #${esc(s.id)}</span>`).join("")}</div>
      <div class="notice">${esc(f.caveat)}</div>
    </article>`).join("")||'<div class="notice">No report findings.</div>'}
  `;
}
function activateTab(name){
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));
  document.querySelectorAll(".tab-panel").forEach(p=>p.hidden=p.id!==name);
}

document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));
$("billSearch").oninput=renderBillList;
$("refreshBills").onclick=loadBills;
$("runResearch").onclick=runResearch;
$("buildReport").onclick=buildReport;
loadBills();
