"""Render analyzed reports into a self-contained HTML site.

Produces one file with two views driven by real analysis data:
- Investment Report: a selectable list of analyzed options + the per-investment
  report (verified-data snapshot with clickable 5yr+ ratio charts, four analyst
  cards, Chair synthesis).
- Compare: a ranked scorecard with council verdicts, key financial ratios,
  recommendation, and the analysis date.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import SITE_DIR

_CSS = """
:root{--bg:#0b0f19;--card:rgba(17,24,39,.72);--border:rgba(255,255,255,.07);--muted:#94a3b8;--txt:#e5e7eb;--blue:#3b82f6;--emerald:#10b981;--amber:#f59e0b;--rose:#f43f5e;--slate:#64748b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:'Inter',system-ui,Arial,sans-serif;background-image:radial-gradient(at 8% 10%,rgba(59,130,246,.10) 0,transparent 45%),radial-gradient(at 92% 85%,rgba(16,185,129,.08) 0,transparent 45%);background-attachment:fixed}
.wrap{max-width:1240px;margin:0 auto;padding:24px 20px 60px}
h1{font-size:22px;margin:0;font-weight:700}.sub{color:var(--muted);font-size:13px;margin-top:4px}
.badge{padding:3px 9px;border-radius:999px;font-size:11px;font-weight:700;display:inline-block}
.b-accum{background:rgba(16,185,129,.14);color:#34d399;border:1px solid rgba(16,185,129,.28)}
.b-wait{background:rgba(245,158,11,.14);color:#fbbf24;border:1px solid rgba(245,158,11,.3)}
.b-pass{background:rgba(100,116,139,.16);color:#cbd5e1;border:1px solid rgba(100,116,139,.3)}
.b-caution{background:rgba(244,63,94,.14);color:#fb7185;border:1px solid rgba(244,63,94,.3)}
.glass{background:var(--card);border:1px solid var(--border);border-radius:16px}
.tabs{display:flex;gap:6px;margin:22px 0;flex-wrap:wrap}
.tab{padding:9px 16px;border-radius:10px;border:1px solid var(--border);background:#0e1422;color:var(--muted);cursor:pointer;font-size:13px;font-weight:600}
.tab.active{background:var(--blue);color:#fff;border-color:transparent}
.screen{display:none}.screen.active{display:block}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.rep-grid{display:grid;grid-template-columns:248px 1fr;gap:16px}
.pick{padding:12px}
.pick .li{padding:10px 11px;border-radius:10px;border:1px solid var(--border);background:#0c1322;cursor:pointer;margin-bottom:8px}
.pick .li.active{background:rgba(59,130,246,.12);border-color:var(--blue)}
.pick .li .nm{font-weight:700;font-size:13px}.pick .li .tk{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted)}
.pick .li .row2{display:flex;justify-content:space-between;align-items:center;margin-top:6px}
.rep-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;padding:20px}
.price{font-size:28px;font-weight:700}
.flagbar{margin:0 20px 12px;padding:8px 12px;border-radius:10px;background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.25);color:#fcd34d;font-size:11px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;padding:0 20px 18px}
.fact{background:#0a101e;border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.fact.clickable{cursor:pointer}.fact.clickable:hover{border-color:rgba(59,130,246,.5);background:#0c1426}
.fact .v{font-size:15px;font-weight:600;font-family:'JetBrains Mono',monospace}
.fact a{color:#60a5fa;font-size:10px;text-decoration:none}.chico{font-size:10px;opacity:.8}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;padding:4px 20px 18px}
.card{background:#0c1322;border:1px solid var(--border);border-radius:14px;padding:16px}
.card .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.card .who{font-weight:700;font-size:13px}.card .lens{font-size:10px;color:var(--muted)}
.bar{height:7px;border-radius:7px;background:#1e293b;overflow:hidden;margin:8px 0 4px}.bar>span{display:block;height:100%;border-radius:7px}
.conv-hi{background:var(--emerald)}.conv-mid{background:var(--amber)}.conv-lo{background:var(--rose)}
.card .thesis{font-size:12px;color:#cbd5e1;line-height:1.5;margin:8px 0}.card .risk{font-size:11px;color:#fb9aa8;margin-top:6px}.card .src{font-size:10px;color:#64748b;margin-top:8px}
.chair{margin:4px 20px 18px;padding:16px;border-radius:14px;background:linear-gradient(135deg,rgba(59,130,246,.10),rgba(16,185,129,.06));border:1px solid rgba(59,130,246,.2)}
.chair h3{margin:0 0 8px;font-size:14px}
.strip{display:flex;gap:20px;flex-wrap:wrap;padding:14px 20px;border-top:1px solid var(--border);font-size:12px}.strip b{font-family:'JetBrains Mono',monospace}
.disc{padding:14px 20px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);line-height:1.6}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:9px 9px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
th{color:var(--muted);font-size:10px;text-transform:uppercase}th.sortable{cursor:pointer}th.sortable:hover{color:#fff}
thead tr.grp th{color:#7dd3fc;text-align:center;background:#0c1322}
td.inv{font-weight:700;color:#fff}td .tk{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted)}
td.num{font-family:'JetBrains Mono',monospace}tr.row:hover{background:rgba(59,130,246,.06)}
.mini{font-size:10px;padding:2px 6px;border-radius:5px;font-weight:700}
.anote{white-space:normal;min-width:220px;max-width:280px;color:#cbd5e1;font-size:11px;line-height:1.45}
.vsep{border-left:2px solid rgba(59,130,246,.18)}
.modal{display:none;position:fixed;inset:0;background:rgba(2,6,18,.72);z-index:50;align-items:center;justify-content:center;padding:20px}
.modal-card{background:#0c1322;border:1px solid var(--border);border-radius:16px;padding:18px 20px;max-width:600px;width:100%}
.btn{padding:8px 14px;border-radius:9px;border:none;font-weight:700;font-size:12px;cursor:pointer}
.btn-run{background:var(--emerald);color:#04231a}
.btn-ghost{background:#0e1422;color:var(--muted);border:1px solid var(--border)}
.cand-link{color:#7dd3fc;cursor:pointer;text-decoration:underline}
.cand-link:hover{color:#fff}
.tag{font-size:9px;background:rgba(59,130,246,.15);color:#93c5fd;border:1px solid rgba(59,130,246,.3);padding:1px 5px;border-radius:5px;margin-left:6px}
"""

_JS = r"""
const stanceCls=s=>({Buy:'b-accum',Accumulate:'b-accum',Wait:'b-wait',Caution:'b-caution',Pass:'b-pass','n/a':'b-pass',Unscored:'b-pass'}[s]||'b-pass');
const fmtv=v=>v===null||v===undefined?'n/a':(Number.isInteger(v)?v:Number(v).toFixed(2));
const convCls=c=>c>=70?'conv-hi':c>=45?'conv-mid':'conv-lo';
const convColor=c=>c>=70?'#34d399':c>=45?'#fbbf24':'#fb7185';
const fmt=(v,u)=>v===null||v===undefined?'n/a':(typeof v==='number'?(Number.isInteger(v)?v:v.toFixed(2)):v)+(u?(' '+u):'');
const ORDER=Object.keys(REPORTS).sort((a,b)=>REPORTS[b].chair.blended_conviction-REPORTS[a].chair.blended_conviction);

function renderPick(sel){
  document.getElementById('pickList').innerHTML=ORDER.map(k=>{const r=REPORTS[k],c=r.chair;
    return `<div class="li ${k===sel?'active':''}" onclick="renderReport('${k}')">
      <div class="nm">${r.investment.name} <span class="tk">${r.investment.ticker}</span></div>
      <div class="row2"><span class="badge ${stanceCls(c.overall_stance)}">${c.overall_label.split(' — ')[0].split(' (')[0]}</span>
      <span style="font-family:monospace;font-weight:700;color:${convColor(c.blended_conviction)}">${c.blended_conviction}</span></div></div>`;}).join('');
}
function renderReport(k){
  const r=REPORTS[k],inv=r.investment,c=r.chair;renderPick(k);
  const facts=Object.entries(inv.facts).map(([m,f])=>{const hist=f.history&&f.history.length;
    return `<div class="fact ${hist?'clickable':''}" ${hist?`onclick="openChart('${k}','${m.replace(/'/g,"")}')"`:''}>
      <div class="label">${m} ${hist?'<span class=chico>📈</span>':''}</div>
      <div class="v">${fmt(f.value,f.unit)}</div>
      ${f.source_name?`<a href="${f.source_url||'#'}" onclick="event.stopPropagation()">${f.source_name} ↗</a>`:''}</div>`;}).join('');
  const cards=r.verdicts.map(v=>{const na=v.engine!=='llm';
    return `<div class="card"><div class="top"><div><div class="who">${v.analyst}</div><div class="lens">${v.lens}</div></div><span class="badge ${stanceCls(v.stance)}">${v.stance}</span></div>
      ${na?`<div class="bar"><span style="width:0"></span></div><div class="label">n/a · outside lens</div>`:`<div class="bar"><span class="${convCls(v.conviction)}" style="width:${v.conviction}%"></span></div><div class="label">conviction ${v.conviction} · confidence ${v.confidence}</div>`}
      <div class="thesis">${v.thesis}</div>${v.key_risk?`<div class="risk">⚠ ${v.key_risk}</div>`:''}${v.sources&&v.sources.length?`<div class="src">sources: ${v.sources.join(', ')}</div>`:''}</div>`;}).join('');
  const flags=(inv.flags&&inv.flags.length)?`<div class="flagbar">⚠ QC flags: ${inv.flags.join(' · ')}</div>`:'';
  const fee=(r.tools&&r.tools.fees&&r.tools.fees.display)||'n/a';
  const fx=(inv.facts['FX risk']&&inv.facts['FX risk'].value)||'n/a';
  const dy=inv.facts['Dividend yield']?fmt(inv.facts['Dividend yield'].value,'%'):'n/a';
  const repat=(r.tools&&r.tools.repatriation)||{};
  const repatTxt=(repat.total_drag_pct!=null)?(repat.total_drag_pct+'%/yr'):'n/a';
  document.getElementById('reportPanel').innerHTML=`
    <div class="rep-head">
      <div><div class="label">${inv.asset_class} · medium-term (3m–2y) lens</div>
        <div style="font-size:20px;font-weight:700;margin-top:2px">${inv.name} <span style="color:var(--muted);font-family:monospace;font-size:14px">${inv.ticker}</span></div>
        <div class="sub">as of ${inv.as_of} · ${inv.currency} · analyzed ${(r.created_at||'').slice(0,10)} · ${r.llm_used?'LLM-written':'heuristic'} verdicts</div></div>
      <div style="text-align:right"><div class="price">${inv.price_display||fmt(inv.price)}</div>${inv.change_pct!=null?`<div style="color:${inv.change_pct>=0?'var(--emerald)':'var(--rose)'};font-size:13px">${inv.change_pct>=0?'▲':'▼'} ${inv.change_pct}%</div>`:''}</div>
      <div style="text-align:right"><div class="label">Council verdict</div><div style="margin-top:6px"><span class="badge ${stanceCls(c.overall_stance)}">${c.overall_label}</span></div>
        <div style="font-family:monospace;font-weight:700;margin-top:6px;color:${convColor(c.blended_conviction)}">Blended conviction ${c.blended_conviction} / 100</div></div>
    </div>
    ${flags}
    <div class="label" style="padding:0 20px 6px">Verified data snapshot</div><div class="facts">${facts}</div>
    ${buildAdvice(r)}${buildPeers(r)}
    <div class="label" style="padding:0 20px 6px">Council — four field specialists</div><div class="cards">${cards}</div>
    <div class="chair"><h3>🪑 Council Chair — synthesis</h3><div style="font-size:12.5px;line-height:1.6;color:#dbeafe">
      <b>Agreement:</b> ${c.agreement} <b>Disagreement:</b> ${c.disagreement}<br><b>Net:</b> ${c.net} <b>What would flip it:</b> ${c.flip}</div></div>
    <div class="strip"><div>Est. cost: <b>${fee}</b></div><div>FX risk: <b>${fx}</b></div><div>Div yield: <b>${dy}</b></div><div>Repat drag: <b>${repatTxt}</b></div></div>
    ${repat.notes?`<div style="padding:8px 20px 0;font-size:11px;color:#94a3b8">🇹🇭 Repatriation (${repat.origin||''}): ${repat.notes} ${repat.suggestion?('<b style="color:#fbbf24">'+repat.suggestion+'</b>'):''} <i>${repat.disclaimer||''}</i></div>`:''}
    <div class="disc">The council informs; <b>you decide</b> — no auto-trading. การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนการตัดสินใจลงทุน</div>`;
}
function num(inv,m){const f=inv.facts[m];return f&&typeof f.value==='number'?f.value:null;}
function disp(inv,m,u){const f=inv.facts[m];if(!f)return['n/a',-1];if(f.value===null||f.value===undefined)return[f.note||'n/a',-1];return[(typeof f.value==='number'?(Number.isInteger(f.value)?f.value:f.value.toFixed(1)):f.value)+(u||''),typeof f.value==='number'?f.value:-1];}
function miniFor(r,key){const v=r.verdicts.find(x=>x.analyst.toLowerCase().includes(key));return v?`<span class="mini ${stanceCls(v.stance)}">${v.stance}</span>`:'<span class="mini b-pass">–</span>';}
function renderScore(){
  document.getElementById('scoreBody').innerHTML=ORDER.map(k=>{const r=REPORTS[k],inv=r.investment,c=r.chair;
    const mc=inv.facts['Market cap'];const mcDisp=mc?(mc.note||mc.value):'—';const mcN=mc&&typeof mc.value==='number'?mc.value:0;
    const pe=disp(inv,'P/E','×'),roe=disp(inv,'ROE','%'),de=disp(inv,'Debt/Equity',''),dyl=disp(inv,'Dividend yield','%'),fcf=disp(inv,'FCF yield','%');
    const fee=(r.tools&&r.tools.fees)||{};const fx=inv.facts['FX risk']?inv.facts['FX risk'].value:'n/a';
    const rep=(r.tools&&r.tools.repatriation)||{};
    const repN=rep.total_drag_pct!=null?rep.total_drag_pct:-1;
    const repD=rep.total_drag_pct!=null?(rep.total_drag_pct+'%'):'n/a';
    const unsc=c.overall_stance==='Unscored';
    const adv=(r.peer_advice&&r.peer_advice.available&&(r.peer_advice.better_overall||[]).length)?` · 🏅 Consider: ${r.peer_advice.better_overall.map(x=>x.ticker).join(', ')}`:'';
    const cands=(r.candidates&&r.candidates.length)?r.candidates.map(x=>`<span class="cand-link" onclick="openCandidate('${x.ticker}')">${x.ticker}</span>`).join(', '):'—';
    return `<tr class="row">
      <td class="inv">${inv.name}${r.discovered_idea?`<span class="tag" style="background:rgba(16,185,129,.15);color:#6ee7b7;border-color:rgba(16,185,129,.3)" title="${(r.idea_reason||'').replace(/"/g,'')}">💡 ${r.idea_theme||'new idea'}</span>`:(r.discovered?'<span class="tag">alt</span>':'')}<div class="tk">${inv.ticker}</div></td>
      <td>${inv.asset_class}</td>
      <td><span class="badge ${stanceCls(c.overall_stance)}">${c.overall_label.split(' — ')[0].split(' (')[0]}</span></td>
      <td class="num" data-n="${unsc?-1:c.blended_conviction}" style="font-weight:700;color:${unsc?'#64748b':convColor(c.blended_conviction)}">${unsc?'—':c.blended_conviction}</td>
      <td>${miniFor(r,'value')}</td><td>${miniFor(r,'macro')}</td><td>${miniFor(r,'cross')}</td><td>${miniFor(r,'risk')}</td>
      <td class="num vsep" data-n="${mcN}">${mcDisp}</td>
      <td class="num" data-n="${pe[1]}">${pe[0]}</td>
      <td class="num" data-n="${roe[1]}">${roe[0]}</td>
      <td class="num" data-n="${de[1]}">${de[0]}</td>
      <td class="num" data-n="${dyl[1]}">${dyl[0]}</td>
      <td class="num" data-n="${fcf[1]}">${fcf[0]}</td>
      <td class="num vsep" data-n="${fee.annual_pct!=null?fee.annual_pct:-1}">${fee.display||'n/a'}</td>
      <td>${fx}</td>
      <td class="num" data-n="${repN}">${repD}</td>
      <td class="anote vsep">${c.net}${adv}</td>
      <td class="num">${(r.created_at||'').slice(0,10)}</td>
      <td>${cands}</td></tr>`;}).join('');
}
function buildPeers(r){
  if(!r.peers||!r.peers.table) return '';
  const tbl=r.peers.table, peers=r.peers.peers||[]; const tk=r.investment.ticker;
  if(!peers.length) return '';
  const order=[tk,...peers];
  const metrics=['P/E','ROE','Dividend yield','FCF yield','Revenue growth','Debt/Equity'].filter(m=>order.some(t=>tbl[t]&&tbl[t][m]!=null));
  if(!metrics.length) return '';
  const head=`<tr><th style="text-align:left">Metric</th>`+order.map(t=>`<th class="num"${t===tk?' style="color:#60a5fa"':''}>${t}</th>`).join('')+`</tr>`;
  const rows=metrics.map(m=>`<tr><td class="label" style="padding:6px 9px">${m}</td>`+order.map(t=>{const v=tbl[t]&&tbl[t][m];return `<td class="num"${t===tk?' style="color:#60a5fa;font-weight:700"':''}>${v==null?'–':fmtv(v)}</td>`;}).join('')+`</tr>`).join('');
  return `<div class="label" style="padding:0 20px 6px">Peer comparison (same industry)</div><div style="padding:0 20px 16px;overflow-x:auto"><table style="font-size:11px">${head}${rows}</table></div>`;
}
function buildAdvice(r){
  const a=r.peer_advice; if(!a||!a.available) return ''; const tk=r.investment.ticker;
  const better=(a.better_overall||[]);
  const fields=(a.field_beats||[]).map(f=>`On <b>${f.metric}</b>: ${f.winner} (${fmtv(f.winner_value)}) beats ${tk} (${fmtv(f.target_value)})`);
  if(!better.length && !fields.length){
    return `<div class="chair" style="background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.25)"><h3>🏅 Peer advisory</h3><div style="font-size:12.5px;color:#bbf7d0">${tk} ranks #${a.target_rank}/${a.total} — best in its peer group on the metrics compared.</div></div>`;
  }
  const head=better.length?`<b>${better.map(x=>x.ticker+' ('+x.score+')').join(', ')}</b> rank higher overall than ${tk} (${a.scores[tk]}/100). Consider them.`:`${tk} ranks #${a.target_rank}/${a.total} overall, but trails on some fields:`;
  return `<div class="chair" style="background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.25)"><h3>🏅 Peer advisory — a competitor may be better</h3><div style="font-size:12.5px;color:#fde68a">${head}</div>${fields.length?`<div style="margin-top:6px;font-size:11px;color:#cbd5e1">${fields.join(' · ')}</div>`:''}</div>`;
}
function openCandidate(t){
  const r=REPORTS[t]; if(!r){alert('No analysis available for '+t);return;}
  const inv=r.investment,c=r.chair;
  const stances=r.verdicts.map(v=>`<span class="mini ${stanceCls(v.stance)}">${v.analyst.split(' ')[0]}: ${v.stance}${v.engine==='llm'?(' '+v.conviction):''}</span>`).join(' ');
  document.getElementById('candTitle').innerHTML=`${inv.name} <span style="color:#64748b;font-family:monospace;font-size:12px">${inv.ticker}</span>`;
  document.getElementById('candBody').innerHTML=`
    <div style="margin:8px 0"><span class="badge ${stanceCls(c.overall_stance)}">${c.overall_label}</span>
      <b style="font-family:monospace;margin-left:8px;color:${c.overall_stance==='Unscored'?'#64748b':convColor(c.blended_conviction)}">conv ${c.overall_stance==='Unscored'?'—':c.blended_conviction}/100</b></div>
    <div style="font-size:12px;color:#cbd5e1;line-height:1.5;margin:8px 0">${c.net}</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0">${stances}</div>
    <div style="font-size:11px;color:#94a3b8">${inv.asset_class} · ${inv.price_display||''} · analyzed ${(r.created_at||'').slice(0,10)}</div>`;
  document.getElementById('candActions').innerHTML=`
    <button class="btn btn-ghost" onclick="switchToReport('${t}')">Open full report</button>
    <button class="btn btn-run" onclick="addWatch('${t}')">＋ Add to watchlist</button>`;
  document.getElementById('candModal').style.display='flex';
}
function switchToReport(t){closeCand();const tab=document.querySelector(".tab[data-s='b']");if(tab)tab.click();renderReport(t);window.scrollTo(0,0);}
function closeCand(){document.getElementById('candModal').style.display='none';}
async function addWatch(t){
  try{ if(location.protocol.indexOf('http')===0){
    const res=await fetch('/api/watchlist/add/'+encodeURIComponent(t),{method:'POST'});
    if(res.ok){alert(t+' added to your watchlist.');return;} } }catch(e){}
  try{ let w=JSON.parse(localStorage.getItem('guru_watchlist')||'[]'); if(!w.includes(t))w.push(t);
    localStorage.setItem('guru_watchlist',JSON.stringify(w)); }catch(e){}
  alert(t+' saved locally. To track it, run:\n  python3 -m guru_council.cli analyze '+t);
}
function buildChart(pts,unit){
  const w=540,h=250,pad=44;const ys=pts.map(p=>p[1]);const mn=Math.min(...ys),mx=Math.max(...ys);const sp=(mx-mn)||1,lo=mn-sp*0.15,hi=mx+sp*0.15;
  const x=i=>pad+(w-pad-14)*(i/(pts.length-1)),y=v=>h-pad-(h-pad-18)*((v-lo)/(hi-lo));
  const line=pts.map((p,i)=>`${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
  const area=`${pad},${(h-pad).toFixed(1)} ${line} ${x(pts.length-1).toFixed(1)},${(h-pad).toFixed(1)}`;
  let grid='',yl='';for(let g=0;g<=4;g++){const gv=lo+(hi-lo)*g/4,gy=y(gv);grid+=`<line x1="${pad}" y1="${gy.toFixed(1)}" x2="${w-14}" y2="${gy.toFixed(1)}" stroke="rgba(255,255,255,.06)"/>`;yl+=`<text x="${pad-6}" y="${(gy+3).toFixed(1)}" text-anchor="end" fill="#64748b" font-size="9">${gv.toFixed(gv<10?1:0)}${unit||''}</text>`;}
  const xl=pts.map((p,i)=>`<text x="${x(i).toFixed(1)}" y="${h-pad+16}" text-anchor="middle" fill="#64748b" font-size="9">${p[0]}</text>`).join('');
  const dots=pts.map((p,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="${i===pts.length-1?4:2.5}" fill="${i===pts.length-1?'#34d399':'#3b82f6'}"/>`).join('');
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%">${grid}<polygon points="${area}" fill="rgba(59,130,246,.12)"/><polyline points="${line}" fill="none" stroke="#3b82f6" stroke-width="2"/>${dots}${yl}${xl}</svg>`;
}
function openChart(k,metric){const f=REPORTS[k].investment.facts[metric];if(!f||!f.history)return;const r=REPORTS[k],last=f.history[f.history.length-1];
  document.getElementById('chartTitle').innerHTML=`${r.investment.name} <span style="color:#64748b;font-family:monospace;font-size:12px">${r.investment.ticker}</span> — ${metric}`;
  document.getElementById('chartSub').textContent=`${f.history.length}-year history · latest ${last[1]}${f.unit||''} (${last[0]}) · source: ${f.source_name||'n/a'}`;
  document.getElementById('chartBox').innerHTML=buildChart(f.history,f.unit);document.getElementById('chartModal').style.display='flex';}
function closeChart(){document.getElementById('chartModal').style.display='none';}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeChart();});
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.screen').forEach(x=>x.classList.remove('active'));t.classList.add('active');document.getElementById(t.dataset.s).classList.add('active');});
let sortDir={};
function sortT(col,type){const tb=document.getElementById('scoreBody');const rows=[...tb.querySelectorAll('tr')];sortDir[col]=!sortDir[col];
  rows.sort((a,b)=>{let av,bv;if(type==='n'){av=parseFloat(a.children[col].dataset.n);bv=parseFloat(b.children[col].dataset.n);}else{av=a.children[col].innerText.toLowerCase();bv=b.children[col].innerText.toLowerCase();}if(av<bv)return sortDir[col]?-1:1;if(av>bv)return sortDir[col]?1:-1;return 0;});
  rows.forEach(r=>tb.appendChild(r));}
if(ORDER.length){renderReport(ORDER[0]);renderScore();}
"""

_SCORE_HEAD = """
<table id="scorecard"><thead>
<tr class="grp"><th colspan="2"></th><th colspan="6">Council</th><th colspan="6" class="vsep">Key financials</th><th colspan="3" class="vsep">Cost &amp; risk</th><th colspan="3" class="vsep">Analysis</th></tr>
<tr><th class="sortable" onclick="sortT(0,'s')">Investment</th><th class="sortable" onclick="sortT(1,'s')">Class</th>
<th>Verdict</th><th class="sortable" onclick="sortT(3,'n')">Conv ▼</th><th>Value</th><th>Macro</th><th>Cross</th><th>Risk</th>
<th class="sortable vsep num" onclick="sortT(8,'n')">Mkt cap</th><th class="sortable num" onclick="sortT(9,'n')">P/E</th><th class="sortable num" onclick="sortT(10,'n')">ROE</th><th class="sortable num" onclick="sortT(11,'n')">D/E</th><th class="sortable num" onclick="sortT(12,'n')">Div yld</th><th class="sortable num" onclick="sortT(13,'n')">FCF yld</th>
<th class="sortable vsep num" onclick="sortT(14,'n')">Fee p.a.</th><th>FX</th><th class="sortable num" onclick="sortT(16,'n')">Repat drag</th>
<th class="vsep">Recommendation</th><th class="sortable" onclick="sortT(18,'s')">Analyzed</th><th>Candidates (better/equal)</th></tr></thead><tbody id="scoreBody"></tbody></table>
"""


def render_site(reports: list[dict[str, Any]]) -> str:
    data = {r["investment"]["ticker"]: r for r in reports}
    body = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>Investment Guru Council</title><style>" + _CSS + "</style></head><body>"
        "<div class='wrap'><h1>Investment Guru Council</h1>"
        "<div class='sub'>Field-specialist council · analyzed results &amp; comparison</div>"
        "<div class='tabs'><div class='tab active' data-s='b'>Investment Report</div>"
        "<div class='tab' data-s='c'>Compare (Scorecard)</div></div>"
        "<div class='screen active' id='b'><div class='rep-grid'>"
        "<div class='glass pick'><div class='label' style='padding:4px 4px 8px'>Interesting options · pick to view</div>"
        "<div id='pickList'></div></div><div class='glass' id='reportPanel'></div></div></div>"
        "<div class='screen' id='c'><div class='glass' style='overflow:hidden'>"
        "<div style='padding:18px 20px 4px'><div style='font-size:15px;font-weight:700'>Compare investments — ranked scorecard</div>"
        "<div class='sub'>Council verdict + conviction, key financial ratios, recommendation, and the analysis date. Click a header to sort.</div></div>"
        "<div style='overflow-x:auto;padding:12px 8px 18px'>" + _SCORE_HEAD + "</div></div></div>"
        "</div>"
        "<div id='chartModal' class='modal' onclick=\"if(event.target===this)closeChart()\"><div class='modal-card'>"
        "<div style='display:flex;justify-content:space-between;align-items:flex-start;gap:10px'>"
        "<div><div id='chartTitle' style='font-weight:700;font-size:15px'></div><div id='chartSub' class='sub'></div></div>"
        "<span onclick='closeChart()' style='cursor:pointer;color:#94a3b8;font-size:22px'>×</span></div>"
        "<div id='chartBox' style='margin-top:12px'></div></div></div>"
        "<div id='candModal' class='modal' onclick=\"if(event.target===this)closeCand()\"><div class='modal-card'>"
        "<div style='display:flex;justify-content:space-between;align-items:flex-start;gap:10px'>"
        "<div><div class='label'>Candidate analysis</div><div id='candTitle' style='font-weight:700;font-size:16px'></div></div>"
        "<span onclick='closeCand()' style='cursor:pointer;color:#94a3b8;font-size:22px'>×</span></div>"
        "<div id='candBody' style='margin-top:8px'></div>"
        "<div id='candActions' style='display:flex;gap:8px;margin-top:14px'></div></div></div>"
        "<script>const REPORTS=" + json.dumps(data, ensure_ascii=False) + ";\n" + _JS + "</script>"
        "</body></html>"
    )
    return body


def write_site(reports: list[dict[str, Any]], filename: str = "council_site.html") -> str:
    html = render_site(reports)
    out = SITE_DIR / filename
    out.write_text(html, encoding="utf-8")
    return str(out)
