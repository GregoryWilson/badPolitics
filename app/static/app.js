const state={bills:[],selected:null,selectedCivic:null,report:null,watches:[],events:[],queue:[],queueSummary:null,discovery:[],civic:[],weeklySources:[],weekly:null,selectedWeeklySource:"sachse"};

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

let weeklyRequestSequence=0;
let weeklyController=null;

async function loadWeeklyDashboard(sourceId=state.selectedWeeklySource){
  state.selectedWeeklySource=sourceId||"sachse";
  const source=state.selectedWeeklySource;
  const request=++weeklyRequestSequence;
  weeklyController?.abort();
  const controller=new AbortController();
  weeklyController=controller;
  state.weekly=null;
  state.weeklyLoading=true;
  state.weeklyError="";
  renderWeeklyDashboard();
  try{
    if(!state.weeklySources.length)state.weeklySources=await api("/dashboard/sources");
    if(request!==weeklyRequestSequence)return;
    renderWeeklyDashboard();
    const result=await api("/dashboard/weekly/"+encodeURIComponent(source)+"?limit=50",{signal:controller.signal});
    if(request!==weeklyRequestSequence)return;
    state.weekly=result;
    state.weeklyLoading=false;
    renderWeeklyDashboard();
  }catch(e){
    if(request!==weeklyRequestSequence||e.name==="AbortError")return;
    state.weeklyLoading=false;
    state.weeklyError=e.message;
    renderWeeklyDashboard();
  }
}
function showWeeklyDashboard(){
  state.selected=null;
  state.selectedCivic=null;
  renderBillList();
  renderDiscovery();
  $("weeklyView").hidden=false;
  $("emptyState").hidden=true;
  $("civicView").hidden=true;
  $("billView").hidden=true;
  loadWeeklyDashboard(state.selectedWeeklySource);
}
function renderWeeklyDashboard(){
  const result=state.weekly||{source:{label:""},window:{},categories:[]};
  const selected=state.weeklySources.find(source=>source.id===state.selectedWeeklySource);
  $("weeklyView").hidden=false;
  $("weeklyTitle").textContent="What's happening this week in "+(selected?.label||result.source?.label||state.selectedWeeklySource);
  $("weeklyWindow").textContent=(result.window?.start||"")+" through "+(result.window?.end||"");
  $("weeklySources").innerHTML=state.weeklySources.map(source=>
    '<button class="weekly-source '+(source.id===state.selectedWeeklySource?'active':'')+'" aria-pressed="'+(source.id===state.selectedWeeklySource)+'" data-weekly-source="'+esc(source.id)+'">'+esc(source.label)+'</button>'
  ).join("");
  document.querySelectorAll(".weekly-source[data-weekly-source]").forEach(button=>{
    button.onclick=()=>loadWeeklyDashboard(button.dataset.weeklySource);
  });
  $("weeklyMetrics").innerHTML=state.weeklyLoading||state.weeklyError?"": [
    ["Items this week",result.item_count||0],
    ["Categories",result.category_count||0],
    ["Institution",result.source?.label||""],
  ].map(([label,value])=>'<div class="metric"><div class="label">'+esc(label)+'</div><div class="value">'+esc(value)+'</div></div>').join("");
  $("weeklyCategories").innerHTML=state.weeklyLoading?'<div class="notice">Loading '+esc(selected?.label||state.selectedWeeklySource)+' activity…</div>':
    state.weeklyError?'<div class="notice">Unable to load weekly source summary: '+esc(state.weeklyError)+'</div>':
    (result.categories||[]).length?(result.categories||[]).map(category=>
    '<section class="weekly-category">'+
      '<div class="weekly-category-header"><h3>'+esc(category.label)+'</h3><span class="badge">'+esc(category.count)+'</span></div>'+
      groupWeeklyItems(category.items).map(group=>
        (group.section?'<h4 class="weekly-section-header">'+esc(group.section)+'</h4>':'')+
        group.items.map(item=>
        '<article class="weekly-item" data-weekly-kind="'+esc(item.kind)+'" data-weekly-id="'+esc(item.record_id)+'" data-weekly-agenda-id="'+esc(item.agenda_item_id??'')+'">'+
          '<div class="weekly-item-top"><strong>'+esc(item.title)+'</strong><span class="weekly-date">'+esc(item.date)+'</span></div>'+
          '<div class="meta"><span class="badge">'+esc(item.status)+'</span>'+
            (item.governing_body?'<span>'+esc(item.governing_body)+'</span>':'')+
            (item.session?'<span>Session '+esc(item.session)+'</span>':'')+
          '</div>'+
          '<div class="weekly-synopsis">'+esc(item.synopsis||"")+'</div>'+
          '<div class="weekly-item-actions"><button class="weekly-open">Open record</button>'+
            (safeUrl(item.source_url)?'<a class="source-link" target="_blank" rel="noreferrer" href="'+esc(safeUrl(item.source_url))+'">Official source</a>':'')+
          '</div>'+
        '</article>'
        ).join("")
      ).join("")+
    '</section>'
  ).join(""):'<div class="notice">'+(result.coverage?.record_count?
    'No dated, substantive activity for this institution was captured this week. '+
    esc(result.coverage.record_count)+' source records are available.'+
    (result.coverage.latest_dated_record?' Latest dated record: '+esc(result.coverage.latest_dated_record)+'.':''):
    'No source records have been captured for this institution yet. Check discovery status.')+'</div>';
  document.querySelectorAll(".weekly-item").forEach(card=>{
    card.querySelector(".weekly-open").onclick=()=>openWeeklyItem(card.dataset.weeklyKind,Number(card.dataset.weeklyId),card.dataset.weeklyAgendaId);
  });
}
function groupWeeklyItems(items){
  const groups=[];
  for(const item of items){
    const section=item.agenda_section||"";
    const key=item.date+"|"+section;
    let group=groups.find(row=>row.key===key);
    if(!group){group={key,section,items:[]};groups.push(group)}
    group.items.push(item);
  }
  return groups;
}
async function openWeeklyItem(kind,id,agendaId=""){
  if(kind==="bill"){
    await selectBill(id);
    return;
  }
  const item=(state.weekly?.categories||[]).flatMap(c=>c.items||[]).find(x=>
    x.kind===kind&&Number(x.record_id)===id&&String(x.agenda_item_id??"")===agendaId);
  if(!item)return;
  state.selected=null;
  state.selectedCivic={id:item.record_id,title:item.title,governing_body:item.governing_body||item.institution,document_type:item.status||"civic record",meeting_date:item.date,source_key:item.source_key,source_url:item.source_url};
  renderBillList();
  renderDiscovery();
  $("weeklyView").hidden=true;
  $("emptyState").hidden=true;
  $("billView").hidden=true;
  $("civicView").hidden=false;
  $("civicEyebrow").textContent=(item.governing_body||item.institution)+" · "+(item.category_label||"Civic activity");
  $("civicTitle").textContent=item.title;
  $("civicMeta").textContent=item.date+" · "+item.source_key;
  const source=safeUrl(item.source_url);
  $("civicSourceLink").hidden=!source;
  if(source)$("civicSourceLink").href=source;
  status("Loading civic analysis…");
  try{
    const analysis=await api("/civic-documents/"+id+"/analysis");
    renderCivicAnalysis(analysis);
    status("");
  }catch(e){
    $("civicFindings").innerHTML='<div class="notice">Civic analysis is unavailable: '+esc(e.message)+'</div>';
    $("civicFacts").innerHTML="";
    $("civicAgendaItems").innerHTML="";
    $("civicEntities").innerHTML="";
    status("");
  }
}

async function loadDiscoveryData(){
  try{
    const result=await Promise.all([
      api("/discovery/status"),
      api("/civic-documents?limit=25")
    ]);
    state.discovery=result[0];
    state.civic=result[1];
    renderDiscovery();
  }catch(e){
    if($("discoveryStatus"))$("discoveryStatus").innerHTML='<div class="notice">Unable to load discovery status.</div>';
  }
}
function renderDiscovery(){
  if(!$("discoveryStatus"))return;
  $("discoveryStatus").innerHTML=state.discovery.length?state.discovery.map(row=>{
    const last=(row.cursor||{}).last_result||{};
    const cls=row.status==="error"?" error":(row.status==="running"?" running":"");
    const progress=last.source_total?((last.offset||0)+(last.source_count||0))+"/"+last.source_total:
      (last.reported_total?((last.offset||0)+(last.source_count||0))+"/"+last.reported_total:"cycle "+esc(row.cycle));
    const civicBits=[];
    if(last.document_count!==undefined)civicBits.push(last.document_count+" docs");
    if(last.records_enumerated!==undefined)civicBits.push(last.records_enumerated+" enumerated");
    if(last.analysis_completed_count!==undefined)civicBits.push(last.analysis_completed_count+" analyzed");
    if(last.error_count)civicBits.push(last.error_count+" fetch error(s)");
    if(last.failed_count)civicBits.push(last.failed_count+" ingest failure(s)");
    return '<div class="discovery-source'+cls+'">'+
      '<div class="discovery-title">'+esc(row.source_key)+'</div>'+
      '<div class="discovery-detail">'+esc(row.status)+' · '+esc(progress)+(civicBits.length?' · '+esc(civicBits.join(" · ")):'')+(row.last_error?' · '+esc(row.last_error):'')+'</div>'+
      '</div>';
  }).join(""):'<div class="notice">Discovery has not run yet.</div>';
  $("civicList").innerHTML=state.civic.length?state.civic.slice(0,20).map(row=>
    '<div class="civic-item '+(state.selectedCivic?.id===row.id?'selected':'')+'" data-civic-id="'+esc(row.id)+'">'+
      '<div class="civic-title">'+esc(row.title)+'</div>'+
      '<div class="civic-detail">'+esc(row.governing_body)+' · '+esc(row.document_type)+(row.meeting_date?' · '+esc(row.meeting_date):'')+'</div>'+
      '</div>'
  ).join(""):'<div class="notice">No civic records captured yet.</div>';
  document.querySelectorAll(".civic-item[data-civic-id]").forEach(el=>el.onclick=()=>selectCivicDocument(Number(el.dataset.civicId)));
}
let discoveryPollTimer=null;
async function pollDiscoveryUntilIdle(){
  if(discoveryPollTimer)clearInterval(discoveryPollTimer);
  const tick=async()=>{
    try{
      const runtime=await api("/discovery/runtime");
      await Promise.all([loadDiscoveryData(),loadBills()]);
      if(runtime.running){
        status("Discovery is running… progress updates every 2 seconds.");
        $("runDiscovery").disabled=true;
      }else{
        if(discoveryPollTimer)clearInterval(discoveryPollTimer);
        discoveryPollTimer=null;
        $("runDiscovery").disabled=false;
        status("Discovery batch completed.","success");
      }
    }catch(e){
      if(discoveryPollTimer)clearInterval(discoveryPollTimer);
      discoveryPollTimer=null;
      $("runDiscovery").disabled=false;
      status("Unable to poll discovery status: "+e.message,"error");
    }
  };
  await tick();
  if(!discoveryPollTimer){
    const runtime=await api("/discovery/runtime").catch(()=>({running:false}));
    if(runtime.running)discoveryPollTimer=setInterval(tick,2000);
  }
}
async function runDiscovery(){
  $("runDiscovery").disabled=true;
  status("Starting discovery…");
  try{
    const result=await api("/discovery/run",{method:"POST"});
    if(result.status==="already_running"){
      status("Discovery is already running. Showing live progress.");
    }else{
      status("Discovery started. Showing live progress.");
    }
    await pollDiscoveryUntilIdle();
  }catch(e){
    status("Discovery failed to start: "+e.message,"error");
    $("runDiscovery").disabled=false;
  }
}

async function selectCivicDocument(id){
  const doc=state.civic.find(row=>row.id===id);
  if(!doc)return;
  state.selectedCivic=doc;
  state.selected=null;
  renderDiscovery();
  renderBillList();
  $("emptyState").hidden=true;
  $("billView").hidden=true;
  $("civicView").hidden=false;
  $("civicEyebrow").textContent=doc.governing_body+" · "+doc.document_type.replaceAll("_"," ");
  $("civicTitle").textContent=doc.title;
  $("civicMeta").textContent=(doc.meeting_date||"Undated")+" · "+doc.source_key;
  const source=safeUrl(doc.source_url);
  $("civicSourceLink").hidden=!source;
  if(source)$("civicSourceLink").href=source;
  status("Loading civic analysis…");
  try{
    let analysis;
    try{
      analysis=await api("/civic-documents/"+id+"/analysis");
    }catch{
      analysis=await api("/civic-documents/"+id+"/analyze",{method:"POST"});
    }
    renderCivicAnalysis(analysis);
    status("");
  }catch(e){
    $("civicFindings").innerHTML='<div class="notice">Civic analysis is unavailable: '+esc(e.message)+'</div>';
    $("civicFacts").innerHTML="";
    $("civicAgendaItems").innerHTML="";
    $("civicEntities").innerHTML="";
    status("");
  }
}
function renderCivicAnalysis(result){
  const findings=result.findings||[];
  const facts=result.structured_facts||[];
  const items=result.agenda_items||[];
  const entities=result.entities||[];
  const money=findings.find(f=>f.category==="explicit_money_mentions");
  const revisions=findings.filter(f=>f.category==="document_revision_change").length;
  const categories=new Set(findings.map(f=>f.category));
  $("civicMetrics").innerHTML=[
    ["Source facts",facts.length],
    ["Agenda/action items",items.length],
    ["Review signals",findings.length],
    ["Signal categories",categories.size],
    ["Named organizations",entities.length],
    ["Money mentions",money?.metadata?.mention_count||0],
    ["Revision changes",revisions],
  ].map(([label,value])=>'<div class="metric"><div class="label">'+esc(label)+'</div><div class="value">'+esc(value)+'</div></div>').join("");
  $("civicFacts").innerHTML=facts.length?facts.map(fact=>
    '<div class="card"><strong>'+esc(fact.label)+'</strong><div class="evidence">'+esc(fact.value)+'</div></div>'
  ).join(""):'<div class="notice">No structured source facts are attached to this record.</div>';
  $("civicFindings").innerHTML=findings.length?findings.map(f=>
    '<article class="card"><h3>'+esc(f.category.replaceAll("_"," "))+'</h3>'+
    '<div class="meta"><span class="badge">'+esc(f.category)+'</span><span>Confidence '+esc(Number(f.confidence).toFixed(2))+'</span></div>'+
    '<div>'+esc(f.statement)+'</div><div class="evidence">'+esc(f.evidence)+'</div></article>'
  ).join(""):'<div class="notice">No deterministic civic review signals found in this revision.</div>';
  $("civicAgendaItems").innerHTML=items.length?items.map(item=>
    '<article class="card"><h3>'+esc((item.item_number?item.item_number+" · ":"")+(item.heading||"Agenda item"))+'</h3>'+
    '<div class="evidence">'+esc(item.text)+'</div></article>'
  ).join(""):'<div class="notice">No agenda/action item structure was detected in this document.</div>';
  $("civicEntities").innerHTML=entities.length?entities.map(entity=>
    '<div class="card"><strong>'+esc(entity.name)+'</strong><div class="meta"><span class="badge">'+esc(entity.entity_type)+'</span><span>'+esc(entity.link_type.replaceAll("_"," "))+'</span></div><div class="evidence">'+esc(entity.evidence)+'</div></div>'
  ).join(""):'<div class="notice">No organization names matched the deterministic entity pattern.</div>';
}
async function reanalyzeSelectedCivic(){
  if(!state.selectedCivic)return;
  $("reanalyzeCivic").disabled=true;
  status("Reanalyzing civic record…");
  try{
    const result=await api("/civic-documents/"+state.selectedCivic.id+"/analyze",{method:"POST"});
    renderCivicAnalysis(result);
    status("Civic analysis refreshed.","success");
  }catch(e){status("Civic analysis failed: "+e.message,"error")}
  finally{$("reanalyzeCivic").disabled=false}
}

async function loadQueueData(){
  try{
    const filter=$("queueStatusFilter")?.value||"";
    const query=filter?"?status="+encodeURIComponent(filter)+"&limit=100":"?limit=100";
    const result=await Promise.all([api("/investigation-queue"+query),api("/investigation-queue/summary")]);
    state.queue=result[0]; state.queueSummary=result[1];
    renderQueue();
  }catch(e){
    if($("queueList"))$("queueList").innerHTML="<div class=\"notice\">Unable to load investigation queue.</div>";
  }
}
function renderQueue(){
  if(!$("queueList"))return;
  const rows=state.queue||[];
  const summary=state.queueSummary||{by_status:{}};
  const statusBits=Object.entries(summary.by_status||{}).filter(([,count])=>count).map(([name,count])=>esc(name.replaceAll("_"," "))+": "+esc(count)).join(" · ");
  $("queueSummary").innerHTML=statusBits||"No queue items yet.";
  $("queueList").innerHTML=rows.length?rows.map(item=>
    "<div class=\"queue-item\" data-queue-bill-id=\""+esc(item.bill?.id||"")+"\">"+
    "<div class=\"queue-item-title\">"+esc(item.bill?.bill_type?.toUpperCase()||"")+" "+esc(item.bill?.bill_number||"")+" · §"+esc(item.section?.number||"")+"</div>"+
    "<div class=\"meta\"><span class=\"badge\">"+esc(item.status.replaceAll("_"," "))+"</span><span>"+esc(item.bill?.jurisdiction||"")+"</span></div>"+
    "<div class=\"queue-tags\">"+(item.trigger_types||[]).slice(0,4).map(t=>"<span class=\"badge\">"+esc(t.replaceAll("_"," "))+"</span>").join("")+"</div>"+
    ((item.unresolved_gaps||[]).length?"<div class=\"queue-gap\">"+esc(item.unresolved_gaps.length)+" evidence gap(s)</div>":"")+
    "</div>"
  ).join(""):"<div class=\"notice\">No queue items match this filter.</div>";
  document.querySelectorAll(".queue-item[data-queue-bill-id]").forEach(el=>{
    const billId=Number(el.dataset.queueBillId);
    if(billId)el.onclick=async()=>{await selectBill(billId);activateTab("triage")};
  });
}
async function loadBillQueue(){
  if(!state.selected)return;
  try{
    const rows=await api("/investigation-queue?bill_id="+state.selected.id+"&limit=100");
    renderBillQueue(rows);
  }catch(e){$("triage").innerHTML="<div class=\"notice\">Unable to load triage workflow.</div>";}
}
function renderBillQueue(rows){
  const options=["new","reviewing","needs_evidence","completed","archived"];
  $("triage").innerHTML="<div class=\"notice\">Triage status and notes are analyst workflow metadata. They do not change the evidence packet or imply a political judgment.</div>"+
    (rows.length?rows.map(item=>{
      const disabled=item.status==="superseded"?" disabled":"";
      const opts=options.map(s=>"<option value=\""+s+"\" "+(item.status===s?"selected":"")+">"+esc(s.replaceAll("_"," "))+"</option>").join("");
      const tags=(item.trigger_types||[]).map(t=>"<span class=\"badge\">"+esc(t.replaceAll("_"," "))+"</span>").join("");
      const gaps=(item.unresolved_gaps||[]).length?"<div class=\"notice\">Evidence gaps: "+esc(item.unresolved_gaps.join(", ").replaceAll("_"," "))+"</div>":"";
      return "<article class=\"card\"><h3>Section "+esc(item.section?.number||"")+" · "+esc(item.status.replaceAll("_"," "))+"</h3>"+
        "<div class=\"meta\"><span>Packet "+esc(item.packet?.id||"")+"</span><span>"+esc((item.trigger_types||[]).length)+" trigger type(s)</span><span>"+esc((item.unresolved_gaps||[]).length)+" evidence gap(s)</span><span>Next: "+esc((item.suggested_next_step||"").replaceAll("_"," "))+"</span></div>"+
        "<div class=\"queue-tags\">"+tags+"</div>"+gaps+
        "<div class=\"triage-controls\"><select class=\"triage-status\" data-queue-id=\""+esc(item.id)+"\""+disabled+">"+opts+"</select>"+
        "<textarea class=\"triage-notes\" data-queue-id=\""+esc(item.id)+"\" placeholder=\"Analyst notes\""+disabled+">"+esc(item.analyst_notes||"")+"</textarea>"+
        "<button class=\"triage-save\" data-queue-id=\""+esc(item.id)+"\""+disabled+">Save</button></div></article>";
    }).join(""):"<div class=\"notice\">No investigation queue items exist for this bill yet.</div>");
  document.querySelectorAll(".triage-save").forEach(button=>{
    button.onclick=async()=>{
      const id=Number(button.dataset.queueId);
      const statusEl=document.querySelector(".triage-status[data-queue-id=\""+id+"\"]");
      const notesEl=document.querySelector(".triage-notes[data-queue-id=\""+id+"\"]");
      button.disabled=true;
      try{
        await api("/investigation-queue/"+id,{method:"PATCH",body:JSON.stringify({status:statusEl.value,analyst_notes:notesEl.value})});
        await Promise.all([loadBillQueue(),loadQueueData()]);
        status("Triage item updated.","success");
      }catch(e){status("Unable to update triage item: "+e.message,"error")}
      finally{button.disabled=false}
    };
  });
}
async function loadWatchData(){
  try{
    const [watches,events]=await Promise.all([api("/watches"),api("/watch-events?limit=30")]);
    state.watches=watches;
    state.events=events;
    renderChangeFeed();
    updateWatchButton();
  }catch(e){
    $("changeFeed").innerHTML='<div class="notice">Unable to load change feed.</div>';
  }
}
function renderChangeFeed(){
  $("changeFeed").innerHTML=state.events.length?state.events.map(e=>`
    <div class="change-item" data-bill-id="${e.bill_id??""}">
      <div class="change-type">${esc(e.event_type.replaceAll("_"," "))}</div>
      <div>${esc(e.title)}</div>
      <div class="bill-item-action">${esc(e.created_at||"")}</div>
    </div>`).join(""):'<div class="notice">No watch changes recorded yet.</div>';
  document.querySelectorAll(".change-item[data-bill-id]").forEach(el=>{
    const id=Number(el.dataset.billId);
    if(id)el.onclick=()=>selectBill(id);
  });
}
function updateWatchButton(){
  if(!state.selected)return;
  const watched=state.watches.some(w=>w.active&&w.target_type==="bill"&&w.jurisdiction===state.selected.jurisdiction&&w.congress===state.selected.congress&&w.bill_type===state.selected.bill_type&&String(w.bill_number)===String(state.selected.bill_number));
  $("watchBill").textContent=watched?"Watching":"Watch Bill";
  $("watchBill").disabled=watched;
  const sessionButton=$("watchSession");
  const canWatchSession=state.selected.jurisdiction!=="US";
  sessionButton.hidden=!canWatchSession;
  if(canWatchSession){
    const sessionWatched=state.watches.some(w=>w.active&&w.target_type==="session"&&w.jurisdiction===state.selected.jurisdiction&&(w.metadata||{}).session===state.selected.session);
    sessionButton.textContent=sessionWatched?"Session Watched":"Watch Session";
    sessionButton.disabled=sessionWatched;
  }
}
async function watchSelectedBill(){
  if(!state.selected)return;
  try{
    const payload={
      name:`${state.selected.bill_type.toUpperCase()} ${state.selected.bill_number}`,
      target_type:"bill",
      jurisdiction:state.selected.jurisdiction,
      congress:state.selected.congress,
      bill_type:state.selected.bill_type,
      bill_number:String(state.selected.bill_number),
      metadata:{session:state.selected.session},
      auto_research:false,
      auto_report:false
    };
    await api("/watches",{method:"POST",body:JSON.stringify(payload)});
    await loadWatchData();
    status("Bill added to watchlist.","success");
  }catch(e){status("Unable to create watch: "+e.message,"error")}
}
async function watchSelectedSession(){
  if(!state.selected||state.selected.jurisdiction==="US")return;
  try{
    const payload={
      name:`${state.selected.jurisdiction} ${state.selected.session}`,
      target_type:"session",
      jurisdiction:state.selected.jurisdiction,
      congress:state.selected.congress,
      metadata:{session:state.selected.session,limit:100},
      auto_research:false,
      auto_report:false
    };
    await api("/watches",{method:"POST",body:JSON.stringify(payload)});
    await loadWatchData();
    status("Legislative session added to watchlist.","success");
  }catch(e){status("Unable to create session watch: "+e.message,"error")}
}

async function scanWatches(){
  $("scanWatches").disabled=true;
  status("Scanning active watches…");
  try{
    const result=await api("/watches/run-all",{method:"POST"});
    const failed=(result.results||[]).filter(r=>r.status==="failed").length;
    await Promise.all([loadBills(),loadWatchData()]);
    status(failed?`Watch scan completed with ${failed} failure(s).`:"Watch scan completed.","success");
  }catch(e){status("Watch scan failed: "+e.message,"error")}
  finally{$("scanWatches").disabled=false}
}

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
      <div class="bill-number">${esc(b.bill_type.toUpperCase())} ${esc(b.bill_number)} · ${esc(b.jurisdiction)} · ${esc(b.session)}</div>
      <div class="bill-item-title">${esc(b.title||"Untitled bill")}</div>
      <div class="bill-item-action">${esc(b.latest_action||"No latest action recorded")}</div>
    </div>`).join("")||'<div class="notice">No bills match this filter.</div>';
  document.querySelectorAll(".bill-item").forEach(el=>el.onclick=()=>selectBill(Number(el.dataset.id)));
}

async function selectBill(id){
  const bill=state.bills.find(b=>b.id===id); if(!bill)return;
  state.selected=bill; state.selectedCivic=null; state.report=null; renderBillList(); renderDiscovery(); updateWatchButton();
  $("weeklyView").hidden=true;$("emptyState").hidden=true;$("civicView").hidden=true;$("billView").hidden=false;
  $("billIdLine").textContent=`${bill.bill_type.toUpperCase()} ${bill.bill_number} · ${bill.jurisdiction} · ${bill.session}`;
  $("billTitle").textContent=bill.title||"Untitled bill";
  $("latestAction").textContent=bill.latest_action||"No latest action recorded.";
  $("report").innerHTML='<div class="notice">Build an investigation report to populate this tab.</div>';
  status("Loading bill details…");
  await Promise.allSettled([loadMetrics(),loadFindings(),loadTimeline(),loadDocuments(),loadFiscal(),loadDiff(),loadLineage(),loadScope(),loadPackets(),loadGraph()]);
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
async function loadDocuments(){
  const rows=await api(`/bills/${state.selected.id}/documents`);
  $("documents").innerHTML=rows.length?rows.map(d=>`
    <article class="card">
      <h3>${esc((d.document_type||"document").replaceAll("_"," "))}</h3>
      <div class="meta"><span class="badge">${esc(d.format||"unknown")}</span><span>${esc(d.description||"")}</span><span>${d.has_text?"Text captured":"Source link only"}</span></div>
      ${safeUrl(d.source_url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(d.source_url))}">Official source</a>`:""}
    </article>`).join(""):'<div class="notice">No supporting documents stored for this bill.</div>';
}

async function loadFiscal(){
  let result;
  try{
    result=await api(`/bills/${state.selected.id}/fiscal-analysis`,{method:"POST"});
  }catch(e){
    $("fiscal").innerHTML='<div class="notice">Fiscal comparison analysis is unavailable.</div>';
    return;
  }
  $("fiscal").innerHTML=`
    <div class="notice">${esc(result.interpretation_note)}</div>
    ${result.findings.length?result.findings.map(f=>`
      <article class="card">
        <h3>${esc(f.statement)}</h3>
        <div class="meta"><span class="badge">${esc(f.category)}</span><span>Confidence ${esc(Number(f.confidence).toFixed(2))}</span><span>${esc((f.source_kind||"").replaceAll("_"," "))}</span></div>
        <div class="evidence">${esc(f.evidence)}</div>
        ${safeUrl(f.source_url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(f.source_url))}">Source</a>`:""}
      </article>`).join(""):'<div class="notice">No deterministic fiscal comparison signals found.</div>'}
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
async function loadLineage(){
  let result;
  try{
    result=await api(`/bills/${state.selected.id}/lineage`,{method:"POST"});
  }catch(e){
    $("lineage").innerHTML='<div class="notice">Provision lineage is unavailable.</div>';
    return;
  }
  const later=result.events.filter(e=>e.from_version?.id&&["introduced","modified","removed"].includes(e.event_type));
  $("lineage").innerHTML=`
    <div class="notice">${esc(result.interpretation_note)}</div>
    ${later.length?later.map(e=>`
      <article class="card">
        <h3>Section ${esc(e.section_number)} · ${esc(e.event_type)}</h3>
        <div class="meta">
          <span>${esc(e.from_version.code||"initial")} → ${esc(e.to_version.code)}</span>
          ${e.similarity!==null&&e.similarity!==undefined?`<span>Similarity ${esc(e.similarity)}</span>`:""}
        </div>
        ${e.candidate_amendments?.length?`
          <div class="section-title">Candidate amendment associations</div>
          ${e.candidate_amendments.map(a=>`
            <div class="card">
              <strong>${esc((a.amendment_type||"").toUpperCase())} ${esc(a.amendment_number)}</strong>
              <div class="meta"><span>Confidence ${esc(Number(a.confidence).toFixed(2))}</span><span>${esc((a.metadata?.basis||"").replaceAll("_"," "))}</span></div>
              <div>${esc(a.description||a.latest_action||"")}</div>
              <div class="notice">${esc(a.evidence)}</div>
              ${safeUrl(a.source_url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(a.source_url))}">Amendment source</a>`:""}
            </div>`).join("")}
        `:""}
        ${e.diff?`<pre>${esc(e.diff)}</pre>`:""}
      </article>`).join(""):'<div class="notice">No later provision changes detected across stored versions.</div>'}
  `;
}

async function loadScope(){
  let result;
  try{
    result=await api(`/bills/${state.selected.id}/scope-analysis`,{method:"POST"});
  }catch(e){
    $("scope").innerHTML='<div class="notice">Scope analysis is unavailable.</div>';
    return;
  }
  $("scope").innerHTML=`
    <div class="notice">${esc(result.interpretation_note)}</div>
    ${result.findings.length?result.findings.map(f=>`
      <article class="card">
        <h3>Section ${esc(f.section_number)} · ${esc(f.category.replaceAll("_"," "))}</h3>
        <div class="meta">
          <span>Confidence ${esc(Number(f.confidence).toFixed(2))}</span>
          <span>Anchor similarity ${esc(f.anchor_similarity===null?"n/a":f.anchor_similarity)}</span>
          <span>Peer similarity ${esc(f.peer_similarity)}</span>
        </div>
        <div>${esc(f.statement)}</div>
        <div class="evidence">${esc(f.evidence)}</div>
      </article>`).join(""):'<div class="notice">No strong semantic scope outliers found.</div>'}
  `;
}

function renderPacketCard(p){
  const packet=p.packet||{};
  const section=packet.section||{};
  const evidence=packet.evidence||[];
  return `
    <article class="card">
      <h3>Section ${esc(section.number||p.section_id)} ${section.heading?`· ${esc(section.heading)}`:""}</h3>
      <div class="meta"><span>${esc(evidence.length)} evidence entries</span><span>Packet ${esc(p.packet_id)}</span><span>${esc(p.llm_model||"No synthesis")}</span></div>
      <div class="notice">${esc(packet.interpretation_note||"")}</div>
      ${p.narrative?`<pre>${esc(p.narrative)}</pre>`:`<button class="synthesize-packet" data-section-id="${esc(p.section_id)}">Generate Local Synthesis</button>`}
      <details>
        <summary>Evidence entries</summary>
        ${evidence.map(e=>`
          <div class="card">
            <strong>[${esc(e.evidence_id)}] ${esc((e.kind||"").replaceAll("_"," "))}</strong>
            <div>${esc(e.summary||"")}</div>
            <div class="evidence">${esc(e.evidence||"")}</div>
            ${safeUrl(e.source_url)?`<a class="source-link" target="_blank" rel="noreferrer" href="${esc(safeUrl(e.source_url))}">Source</a>`:""}
          </div>`).join("")}
      </details>
    </article>`;
}
function wirePacketButtons(){
  document.querySelectorAll(".synthesize-packet").forEach(button=>{
    button.onclick=async()=>{
      const sectionId=Number(button.dataset.sectionId);
      button.disabled=true;
      status("Generating evidence-constrained local synthesis…");
      try{
        await api(`/sections/${sectionId}/evidence-packet?generate_narrative=true`,{method:"POST"});
        await loadPackets();
        status("Local synthesis generated.","success");
      }catch(e){status("Synthesis failed: "+e.message,"error")}
      finally{button.disabled=false}
    };
  });
}
async function loadPackets(){
  try{
    const result=await api(`/bills/${state.selected.id}/evidence-packets?generate_narrative=false&limit=25`,{method:"POST"});
    $("packets").innerHTML=`
      <div class="notice">${esc(result.interpretation_note)}</div>
      ${result.packets.length?result.packets.map(renderPacketCard).join(""):'<div class="notice">No provision evidence packets were generated for this bill.</div>'}
    `;
    wirePacketButtons();
    try{
      await api(`/bills/${state.selected.id}/queue/sync?limit=50&prepare=false`,{method:"POST"});
      await Promise.all([loadBillQueue(),loadQueueData()]);
    }catch(queueError){
      $("triage").innerHTML='<div class="notice">Evidence packets are available, but queue synchronization failed.</div>';
    }
  }catch(e){
    $("packets").innerHTML='<div class="notice">Evidence packet generation is unavailable.</div>';
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
    <div class="card"><strong>Report ${esc(r.report_id)}</strong><div class="meta"><span>${esc(r.finding_summary.total)} findings</span><span>${esc((r.supporting_documents||[]).length)} supporting documents</span><span>Version ${esc(r.version.code||"n/a")}</span><span>${esc(r.research?.status||"No research run")}</span></div></div>
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
$("refreshBills").onclick=async()=>{await Promise.all([loadBills(),loadWatchData(),loadQueueData(),loadDiscoveryData()])};
$("showWeekly").onclick=showWeeklyDashboard;
$("runDiscovery").onclick=runDiscovery;
$("scanWatches").onclick=scanWatches;
$("watchBill").onclick=watchSelectedBill;
$("watchSession").onclick=watchSelectedSession;
$("runResearch").onclick=runResearch;
$("buildReport").onclick=buildReport;
$("queueStatusFilter").onchange=loadQueueData;
$("reanalyzeCivic").onclick=reanalyzeSelectedCivic;
Promise.all([loadBills(),loadWatchData(),loadQueueData(),loadDiscoveryData(),loadWeeklyDashboard("sachse")]);
