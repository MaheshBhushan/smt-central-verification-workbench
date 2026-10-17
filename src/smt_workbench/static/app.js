/* Local operator UI. Predictions never preselect a human decision. */
let state = {boards: [], events: []};
let selected = null;
const el = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const badge = status => `<span class="badge ${escapeHTML(status.toLowerCase())}">${escapeHTML(status.replaceAll('_', ' '))}</span>`;
const key = b => `${b.run_id}/${b.board_id}`;
async function api(url, body) {
  const response = await fetch(url, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}
function toast(message) { el('toast').textContent=message; el('toast').style.display='block'; setTimeout(()=>el('toast').style.display='none',5000); }
async function refresh() {
  try {
    state = await api('/api/state');
    const health = await api('/api/health');
    el('connection').textContent = health.model_loaded ? '● Connected · classifier loaded' : '● Connected · classifier unavailable';
    const lines = [...new Set(state.boards.map(b=>b.line_id))].sort();
    const oldLine = el('line').value;
    el('line').innerHTML='<option value="">All lines</option>'+lines.map(l=>`<option>${escapeHTML(l)}</option>`).join('');
    el('line').value=oldLine;
    if (!selected && state.boards.length) selected=key(state.boards.find(b=>b.state==='READY_FOR_REVIEW') || state.boards[0]);
    render();
  } catch(error) { toast(error.message); el('connection').textContent='● Connection interrupted'; }
}
function render() {
  const ready=state.boards.filter(b=>b.state==='READY_FOR_REVIEW').length;
  const reviewed=state.boards.filter(b=>['REVIEWED','RELEASED'].includes(b.state)).length;
  const quarantine=state.events.filter(e=>e.status==='quarantined').length;
  el('stats').innerHTML=[['Boards in view',state.boards.length,'Across '+new Set(state.boards.map(b=>b.line_id)).size+' simulated lines'],['Awaiting review',ready,'Complete inspection evidence'],['Verified boards',reviewed,'Human or labelled load-test reviews'],['Quarantined events',quarantine,'Last 200 journal entries']].map(([a,b,c])=>`<div class="stat"><div class="stat-label">${a}</div><div class="stat-number">${b}</div><div class="stat-note">${c}</div></div>`).join('');
  const boards=[...state.boards].sort((a,b)=>(a.state!=='READY_FOR_REVIEW')-(b.state!=='READY_FOR_REVIEW')).filter(b=>!el('line').value||b.line_id===el('line').value);
  el('boards').innerHTML=boards.map(b=>`<button class="board ${key(b)===selected?'selected':''}" data-board="${escapeHTML(key(b))}"><div class="board-top"><span class="board-name">${escapeHTML(b.board_id)}</span>${badge(b.state)}</div><div class="board-bottom"><span class="meta">${escapeHTML(b.line_id)} &nbsp; / &nbsp; ${escapeHTML(b.buffer_id)} · Slot ${escapeHTML(b.slot_id)}</span><span class="meta">${b.sites.length} sites →</span></div></button>`).join('')||'<div class="empty">No boards. Run the demo command to generate a queue.</div>';
  document.querySelectorAll('[data-board]').forEach(button=>button.onclick=()=>{selected=button.dataset.board;render();});
  el('events').innerHTML=state.events.slice(0,15).map(e=>`<tr><td>${escapeHTML(e.event_id)}</td><td>${badge(e.status)}</td><td>${e.attempts}</td><td>${escapeHTML(e.reason||'Correlated successfully')}</td></tr>`).join('');
  renderDetail();
}
function renderDetail() {
  const b=state.boards.find(b=>key(b)===selected); if(!b) return;
  el('detail').innerHTML=`<div class="detail-title"><div class="eyebrow">BOARD EVIDENCE</div><h2>${escapeHTML(b.board_id)}</h2><div class="meta">${escapeHTML(b.line_id)} / ${escapeHTML(b.buffer_id)} / Slot ${escapeHTML(b.slot_id)}<br>Occupancy ${escapeHTML(b.occupancy_id)} · Run ${escapeHTML(b.run_id)}</div></div><div class="evidence">${b.sites.map(s=>`<article class="site">${s.image_path?`<img src="/artifacts/${s.image_path.split('/').map(encodeURIComponent).join('/')}" alt="Synthetic AOI inspection crop for ${escapeHTML(s.site_id)}">`:'<div class="empty">AOI pending</div>'}<div class="site-body"><div class="site-heading"><span>${escapeHTML(s.site_id)}</span><span class="meta">SYNTHETIC AOI</span></div><div class="measurements"><span>HEIGHT<b>${s.measurement?s.measurement.height_mm.toFixed(3)+' mm':'Pending'}</b></span><span>VOLUME<b>${s.measurement?s.measurement.volume_mm3.toFixed(3)+' mm³':'Pending'}</b></span></div><div class="prediction">MODEL RECOMMENDATION<br><strong>${s.prediction?escapeHTML(s.prediction.label.replaceAll('_',' ')):'Awaiting evidence'}</strong> ${s.prediction?'· '+(s.prediction.confidence*100).toFixed(1)+'%':''}</div>${b.state==='READY_FOR_REVIEW'?`<label class="meta">Your decision<select data-decision="${escapeHTML(s.site_id)}" required><option value="">Select decision…</option><option value="false_call">False call</option><option value="real_defect">Real defect</option></select></label>`:''}</div></article>`).join('')}</div>${b.state==='READY_FOR_REVIEW'?'<form class="review-form" id="review"><label>REVIEWER<input name="reviewer" required maxlength="80" placeholder="Operator name"></label><label>REVIEW REASON<textarea name="reason" required maxlength="1000" placeholder="Describe your evidence-based decision"></textarea></label><button type="submit">Submit board verification →</button></form>':b.review?`<div class="review-note">Verified by <strong>${escapeHTML(b.review.operator)}</strong><br>${escapeHTML(b.review.note)}<br>${b.state==='REVIEWED'?'<button id="release">Simulate board release →</button>':'Slot released · review retained for audit'}</div>`:'<div class="review-note">Collection is in progress. Every expected site requires AOI and 3D evidence.</div>'}`;
  if(el('review')) el('review').onsubmit=async event=>{
    event.preventDefault();
    const decisions=[...document.querySelectorAll('[data-decision]')].map(s=>({site_id:s.dataset.decision,decision:s.value}));
    if(decisions.some(d=>!d.decision)) {toast('Select a decision for every site.');return;}
    const form=new FormData(event.target); const button=event.target.querySelector('button');button.disabled=true;
    try{await api(`/api/boards/${encodeURIComponent(b.run_id)}/${encodeURIComponent(b.board_id)}/review`,{request_id:crypto.randomUUID(),reviewer:form.get('reviewer'),reason:form.get('reason'),decisions});toast('Board verification saved.');await refresh();}catch(error){toast(error.message);button.disabled=false;}
  };
  if(el('release')) el('release').onclick=async()=>{try{await api('/api/events',{schema_version:'1.0',occurred_at:new Date().toISOString(),event_id:crypto.randomUUID(),event_type:'release',...Object.fromEntries(['run_id','board_id','line_id','buffer_id','slot_id','occupancy_id'].map(k=>[k,b[k]])),payload:{}});toast('Board released. Slot is available.');await refresh();}catch(error){toast(error.message);}};
}
el('refresh').onclick=refresh;el('line').onchange=render;el('replay').onclick=async()=>{try{const data=await api('/api/replay',{});toast(`Replay processed ${data.results.length} events.`);await refresh();}catch(error){toast(error.message);}};refresh();
