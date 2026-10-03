"""The dashboard page. One self-contained HTML document, no external files or libraries."""

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robotics QA Dashboard</title>
<style>
:root{
 --bg:#f6f7f9;--card:#fff;--ink:#16191d;--ink2:#4a5360;--muted:#6b7480;--line:#e3e6ea;
 --series:#2563eb;--good:#1a7f37;--goodbg:#e8f5ec;--warn:#9a6700;--warnbg:#fff4d6;
 --bad:#b42318;--badbg:#fde8e6;--idle:#4a5360;--idlebg:#eceff3;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
 --bg:#12151a;--card:#1a1f26;--ink:#eef1f4;--ink2:#b4bcc6;--muted:#8d97a3;--line:#2a313a;
 --series:#6ea0ff;--good:#56d17a;--goodbg:#14301f;--warn:#f0b840;--warnbg:#3a2e0e;
 --bad:#ff8a80;--badbg:#3a1a17;--idle:#b4bcc6;--idlebg:#222831;}}
*{box-sizing:border-box}
body{font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:16px;color:var(--ink);
 background:var(--bg)}
main{max-width:1000px;margin:0 auto}
h1{font-size:20px;margin:0}h2{font-size:16px;margin:0 0 4px}
.top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;margin-bottom:12px}
.sub{color:var(--muted);font-size:13px}
select,input,button{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
 background:var(--card);color:var(--ink)}
button{cursor:pointer}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.banner{display:flex;gap:14px;align-items:center;border-radius:12px;padding:18px 20px;margin-bottom:12px;
 border:1px solid var(--line)}
.banner .icon{font-size:34px;line-height:1;font-weight:700}
.banner .head{font-size:24px;font-weight:700;line-height:1.2}
.banner.green{background:var(--goodbg);color:var(--good)}
.banner.amber{background:var(--warnbg);color:var(--warn)}
.banner.red{background:var(--badbg);color:var(--bad)}
.banner.idle{background:var(--idlebg);color:var(--idle)}
.banner .advice{color:var(--ink);font-size:15px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi .n{font-size:28px;font-weight:700;line-height:1.1}
.kpi .l{font-weight:600}.kpi .c{color:var(--muted);font-size:12.5px;margin-top:2px}
.item{border-left:5px solid var(--line);padding:8px 12px;margin:10px 0;background:var(--bg);border-radius:6px}
.item.critical{border-color:var(--bad)}.item.warning{border-color:var(--warn)}
.item .t{font-weight:700}.item .d{color:var(--ink2);margin:2px 0}
.item .w{margin-top:4px}.item .w b{color:var(--ink)}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:99px;margin-right:6px}
.tag.critical{background:var(--badbg);color:var(--bad)}.tag.warning{background:var(--warnbg);color:var(--warn)}
.clear{color:var(--good);font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin:4px 0 6px}
svg{width:100%;height:auto;display:block}
.axis text{fill:var(--muted);font-size:11px}.axis line,.grid line{stroke:var(--line)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);padding:5px 9px;border-radius:6px;
 font-size:12.5px;display:none;z-index:5;white-space:nowrap}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-size:12.5px;font-weight:600}
tbody tr{cursor:pointer}tbody tr:hover{background:var(--bg)}
.res{font-weight:600;white-space:nowrap}
.res.ok{color:var(--good)}.res.bad{color:var(--bad)}.res.warn{color:var(--warn)}.res.info{color:var(--ink2)}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
dialog{border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);
 max-width:520px;width:calc(100% - 32px)}
dialog::backdrop{background:rgba(0,0,0,.4)}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:10px 0}dt{color:var(--muted)}dd{margin:0}
pre{background:var(--bg);padding:8px;border-radius:6px;overflow:auto;font-size:12px}
details summary{cursor:pointer;color:var(--ink2)}
@media (max-width:600px){.banner .head{font-size:20px}th:nth-child(4),td:nth-child(4){display:none}}
</style></head><body><main>

<div class="top">
 <div><h1>Robot cell status</h1><div class="sub" id="updated">Loading...</div></div>
 <label>Show the last
  <select id="hours" onchange="refreshAll()">
   <option value="1">hour</option><option value="24" selected>24 hours</option><option value="168">7 days</option>
  </select></label>
</div>

<div id="banner" class="banner idle" role="status"><div class="icon">...</div>
 <div><div class="head">Loading</div><div class="advice"></div></div></div>

<div class="kpis" id="kpis"></div>

<div class="card"><h2>What needs your attention</h2>
 <div class="sub">Only things a person should act on are listed here. Everything else stays out of your way.</div>
 <div id="attention"></div></div>

<div class="card"><h2>How long each part takes (in seconds)</h2>
 <div class="sub">One dot per part, oldest on the left. A steady line is healthy. A line that climbs means the
  robot is slowing down and may need maintenance.</div>
 <div class="legend" id="legend"></div>
 <div id="chart"></div></div>

<div class="card"><h2>Everything the robot did</h2>
 <div class="sub">Click any row to see the details of that event.</div>
 <div class="bar">
  <select id="show" onchange="loadTable(true)">
   <option value="">Show everything</option><option value="problems">Show problems only</option></select>
  <input id="q" placeholder="Search, e.g. red_1" oninput="debounceLoad()">
 </div>
 <table><thead><tr><th>When</th><th>What</th><th>Result</th><th>Detail</th></tr></thead>
  <tbody id="rows"></tbody></table>
 <div class="bar"><button id="more" onclick="loadTable(false)" hidden>Show older</button></div>
</div>

<details class="card"><summary><b>How to read this page</b></summary>
 <p><b>Good part</b>: the robot sorted it into the good bin.</p>
 <p><b>Defect - rejected</b>: the robot found a bad part and put it in the reject bin. This is the robot doing
  its job, not a robot fault.</p>
 <p><b>Could not move</b>: the robot tried and failed to pick the part. Someone should look.</p>
 <p><b>Status banner</b>: green means nothing to do, amber means something is drifting and should be checked
  soon, red means act now.</p>
 <p>Every robot reports to this page the same way, so a new robot only needs a small adapter to appear here.</p>
</details>

<dialog id="dlg"><div id="dlgbody"></div>
 <div class="bar"><button onclick="document.getElementById('dlg').close()">Close</button></div></dialog>
<div id="tip"></div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ICON={green:'✓',amber:'!',red:'✕',idle:'…'};
let cursor=null,loadedMore=false,timer=null;

function ago(iso){
  const s=(Date.now()-new Date(iso).getTime())/1000;
  if(!isFinite(s))return '';
  if(s<60)return 'just now';if(s<3600)return Math.round(s/60)+' min ago';
  if(s<86400)return Math.round(s/3600)+' h ago';return Math.round(s/86400)+' days ago';
}
const clock=iso=>new Date(iso).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});

function describe(r){            // plain-language label for any run
  const isPart=r.project==='cobot_qa'&&r.name.startsWith('part:');
  if(isPart){
    const nm=r.name.slice(5);
    if(r.status==='pass')return {what:'Sorted '+nm,label:'✓ Good part',cls:'ok'};
    if(r.status==='fail')return {what:'Sorted '+nm,label:'◆ Defect - rejected',cls:'info'};
    return {what:'Tried to sort '+nm,label:'! Could not move',cls:'warn'};
  }
  if(r.status==='pass')return {what:r.name,label:'✓ OK',cls:'ok'};
  if(r.status==='fail')return {what:r.name,label:'✕ Problem',cls:'bad'};
  return {what:r.name,label:'! Warning',cls:'warn'};
}

async function loadSummary(){
  const h=$('hours').value;
  const s=await (await fetch('/summary?hours='+h)).json();
  const b=$('banner');b.className='banner '+s.status;
  b.innerHTML=`<div class="icon" aria-hidden="true">${ICON[s.status]}</div>
   <div><div class="head">${esc(s.headline)}</div><div class="advice">${esc(s.advice)}</div></div>`;
  const t=s.totals;
  const kp=(n,l,c)=>`<div class="kpi"><div class="n">${n}</div><div class="l">${l}</div><div class="c">${c}</div></div>`;
  $('kpis').innerHTML=
    kp(t.parts,'Parts handled','Everything the arm picked up')+
    kp(t.good,'Good parts','Sorted into the good bin')+
    kp(t.defects,'Defects caught','Bad parts the robot rejected. This is normal.')+
    kp(t.stuck,'Could not move','Parts the arm failed to pick')+
    kp(t.avg_cycle_s==null?'-':t.avg_cycle_s+' s','Average time per part','How long one pick-and-place takes')+
    (t.goals?kp(t.goals_reached+' of '+t.goals,'Mobile robot goals reached','Places the mobile robot was sent to'):'');
  $('attention').innerHTML=s.attention.length?s.attention.map(i=>`
    <div class="item ${i.severity}">
     <div class="t"><span class="tag ${i.severity}">${i.severity==='critical'?'ACT NOW':'CHECK SOON'}</span>${esc(i.title)}</div>
     <div class="d">${esc(i.detail)}</div>
     <div class="w"><b>What to do:</b> ${esc(i.what_to_do)}</div></div>`).join('')
    :'<p class="clear">✓ Nothing needs attention right now.</p>';
  drawChart(s.recent_parts);
  $('updated').textContent='Updated '+new Date().toLocaleTimeString()+' - refreshes by itself every 10 seconds';
}

/* ---------- chart: cycle time per part (one series, one axis) ---------- */
function drawChart(parts){
  const el=$('chart');
  const pts=parts.filter(p=>p.cycle_s!=null);
  if(pts.length<2){el.innerHTML='<p class="sub">Not enough parts yet to draw a line. At least 2 are needed.</p>';
    $('legend').innerHTML='';return;}
  const W=720,H=230,L=44,R=14,T=12,B=30;
  const maxY=Math.max(...pts.map(p=>p.cycle_s))*1.2||1;
  const x=i=>L+(W-L-R)*(pts.length===1?0:i/(pts.length-1));
  const y=v=>T+(H-T-B)*(1-v/maxY);
  const avg=pts.reduce((a,p)=>a+p.cycle_s,0)/pts.length;
  let g='';
  for(let k=0;k<=3;k++){const v=maxY*k/3;
    g+=`<g class="grid"><line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"></line></g>
        <g class="axis"><text x="${L-6}" y="${y(v)+4}" text-anchor="end">${v.toFixed(1)}</text></g>`;}
  const line=pts.map((p,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(p.cycle_s).toFixed(1)}`).join('');
  const mark=(p,i)=>{
    const cx=x(i),cy=y(p.cycle_s);
    if(p.result==='defect')return `<path d="M${cx},${cy-6}L${cx+6},${cy}L${cx},${cy+6}L${cx-6},${cy}Z"
       fill="var(--card)" stroke="var(--series)" stroke-width="2"></path>`;
    if(p.result==='stuck')return `<path d="M${cx-5},${cy-5}L${cx+5},${cy+5}M${cx+5},${cy-5}L${cx-5},${cy+5}"
       stroke="var(--bad)" stroke-width="2.5"></path>`;
    return `<circle cx="${cx}" cy="${cy}" r="4.5" fill="var(--series)" stroke="var(--card)" stroke-width="2"></circle>`;
  };
  const hits=pts.map((p,i)=>`<circle class="hit" data-i="${i}" cx="${x(i)}" cy="${y(p.cycle_s)}" r="12"
       fill="transparent"></circle>`).join('');
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img"
     aria-label="Time per part in seconds for the last ${pts.length} parts">
    ${g}
    <line x1="${L}" x2="${W-R}" y1="${y(avg)}" y2="${y(avg)}" stroke="var(--muted)" stroke-dasharray="5 4"></line>
    <g class="axis"><text x="${L}" y="${H-8}">older</text><text x="${W-R}" y="${H-8}" text-anchor="end">newer</text></g>
    <path d="${line}" fill="none" stroke="var(--series)" stroke-width="2"></path>
    ${pts.map(mark).join('')}${hits}</svg>`;
  $('legend').innerHTML=
    '<span>- - average '+avg.toFixed(1)+' s</span><span>● Good part</span><span>◇ Defect - rejected</span><span style="color:var(--bad)">✕ Could not move</span>';
  const tip=$('tip');
  el.querySelectorAll('.hit').forEach(c=>{
    c.addEventListener('pointermove',e=>{
      const p=pts[+c.dataset.i];
      tip.textContent=`${p.part} - ${({good:'Good part',defect:'Defect - rejected',stuck:'Could not move'})[p.result]} - ${p.cycle_s.toFixed(1)} s - ${clock(p.at)}`;
      tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';});
    c.addEventListener('pointerleave',()=>tip.style.display='none');
  });
}

/* ---------- activity table ---------- */
async function loadTable(reset){
  if(reset){cursor=null;loadedMore=false;$('rows').innerHTML=''} else loadedMore=true;
  const p=new URLSearchParams({limit:15});
  if($('show').value==='problems')p.set('problems','true');
  const q=$('q').value.trim();if(q)p.set('q',q);
  if(cursor)p.set('cursor',cursor);
  const r=await (await fetch('/runs?'+p)).json();
  for(const i of r.items){
    const d=describe(i);
    $('rows').insertAdjacentHTML('beforeend',
     `<tr data-id="${i.id}"><td title="${esc(i.created_at)}">${esc(clock(i.created_at))}<div class="sub">${esc(ago(i.created_at))}</div></td>
      <td>${esc(d.what)}</td><td class="res ${d.cls}">${esc(d.label)}</td><td>${esc(i.message)}</td></tr>`);
  }
  cursor=r.next_cursor;$('more').hidden=!cursor;
  if(!$('rows').children.length)$('rows').innerHTML='<tr><td colspan="4" class="sub">Nothing to show.</td></tr>';
}
$('rows').addEventListener('click',async e=>{
  const tr=e.target.closest('tr[data-id]');if(!tr)return;
  const r=await (await fetch('/runs/'+tr.dataset.id)).json();
  const d=describe(r),pl=r.payload||{};
  const row=(k,v)=>v==null||v===''?'':`<dt>${k}</dt><dd>${esc(v)}</dd>`;
  $('dlgbody').innerHTML=`<h2>${esc(d.what)}</h2><div class="res ${d.cls}">${esc(d.label)}</div>
   <dl>${row('When',new Date(r.created_at).toLocaleString())}${row('Source',r.project)}
   ${row('Went to',pl.bin&&({good:'Good bin',reject:'Reject bin',skipped:'Stayed on the table'})[pl.bin])}
   ${row('Colour',pl.colour)}${row('Time taken',pl.cycle_time_s!=null?pl.cycle_time_s+' s':'')}
   ${row('Position check',pl.layout_error_mm!=null?pl.layout_error_mm+' mm from expected':'')}
   ${row('Note',r.message)}</dl>
   <details><summary>Technical details</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`;
  $('dlg').showModal();
});
let deb=null;function debounceLoad(){clearTimeout(deb);deb=setTimeout(()=>loadTable(true),300)}

async function refreshAll(){
  try{await loadSummary();if(!loadedMore)await loadTable(true);}
  catch(e){$('updated').textContent='Cannot reach the dashboard server. Retrying...'}
}
refreshAll();setInterval(refreshAll,10000);
</script></main></body></html>
"""
