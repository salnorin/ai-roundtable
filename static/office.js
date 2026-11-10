/* Office mode UI: 3D floor, avatars, packets, permissions, approvals. Loaded after the main app script. */
(function(){
  const TIER={free:['رایگان','free'],cheap:['ارزان','cheap'],freemium:['رایگان / ارزان','freemium']};
  function tierb(t){if(!t)return '';const l=TIER[t]||[t,'cheap'];return `<span class="tier ${l[1]}">${l[0]}</span>`}
  const _keyb = window.keyb;
  window.tierb = tierb;
  window.keyb = function(h,mock,signup){
    if(mock) return '<span class="b grey">آزمایشی</span>';
    if(h) return '<span class="b ok">دارد</span>';
    const a=signup?` <a class=klink href="${esc(signup)}" target=_blank rel=noopener>دریافت کلید</a>`:'';
    return `<span class="b grey">کلید لازمه</span>${a}`;
  };

  window.hashName=function(s){let h=0;for(const c of String(s||''))h=(h*33+c.charCodeAt(0))>>>0;return h};
  window.personSVG=function(p,present,cls){
    const role=p.role||'', title=p.role_title||'';
    if(!present){return `<svg class="avt empty ${cls||''}" viewBox="0 0 80 100"><g fill="none" stroke="#9aa0b0" stroke-width="1.6"><rect x="18" y="58" width="44" height="8" rx="1" fill="#5a5c66" stroke="none"/><path d="M26 58v18M54 58v18M22 76h36"/><path d="M30 38c0-8 4-14 10-14s10 6 10 14v20H30z" fill="#4a4c55"/></g></svg>`}
    const h=hashName(p.name||title||role);
    const skin=['#f6e0c8','#f3d0b5','#e0b48a','#c48a62','#8d5a3c'][h%5];
    const hair=['#1c1410','#3a2314','#6b3a1f','#111217','#d1b07a'][h%5];
    const cloth={boss:'#2a2450',secretary:'#245a52',lawyer:'#1e2a4a',medical:'#e8eef4',psychologist:'#3d4a6a',philosopher:'#3a2f4a',physicist:'#243a5a',math:'#2a3a4a',devil:'#3a1520',skeptic:'#2a3340',software:'#1d2a28',economist:'#2a2f38',historian:'#4a3828',engineer:'#3a3a30',humanities:'#4a2f3a'}[role]||['#3d4a8a','#2c6e5a','#7a3d4a','#3a3f4b','#5b4b8c'][h%5];
    const shirt=role==='medical'?'#f4f7fb':cloth, haircut=h%3;
    const hairP=haircut===0?`<path d="M22 32c2-14 36-16 38 0 0 8-4 12-8 12H30c-4 0-8-4-8-12z" fill="${hair}"/>`:haircut===1?`<path d="M20 34c4-16 38-16 42 0v4c-8-6-34-6-42-2z" fill="${hair}"/>`:`<path d="M22 36c2-14 14-20 22-12 8-10 24-6 22 12 2 6-8 10-12 8-6 6-18 6-24 0-6 2-10-2-8-8z" fill="${hair}"/>`;
    const acc=(role==='lawyer')?`<path d="M28 78h24M40 64v14" stroke="#d4b45a" stroke-width="1.6"/>`:role==='medical'?`<rect x="46" y="58" width="10" height="10" rx="1" fill="#c23"/>`: (role==='boss'||title==='مدیر')?`<rect x="24" y="78" width="32" height="4" rx="1" fill="#d4b45a"/>`:(role==='secretary'||title==='منشی')?`<rect x="50" y="62" width="14" height="10" rx="1" fill="#f4efe4" stroke="#333" stroke-width=".8"/>`:role==='devil'?`<path d="M24 28l-6-10 10 4M56 28l6-10-10 4" fill="${hair}"/>`:role==='software'||role==='engineer'?`<rect x="48" y="60" width="16" height="10" rx="1" fill="#111" opacity=".5"/>`:'';
    return `<svg class="avt ${cls||''}" viewBox="0 0 80 100"><ellipse cx="40" cy="94" rx="18" ry="5" fill="rgba(0,0,0,.25)"/><path d="M24 70c0-8 6-14 16-14s16 6 16 14v22H24z" fill="${shirt}"/><path d="M28 90h24v6H28z" fill="#2a2c36"/><circle cx="40" cy="40" r="16" fill="${skin}"/>${hairP}<circle cx="34" cy="41" r="1.6" fill="#221"/><circle cx="46" cy="41" r="1.6" fill="#221"/><path d="M35 49c3 3 7 3 10 0" stroke="#a36" stroke-width="1.2" fill="none" stroke-linecap="round"/>${acc}</svg>`;
  };
  function deskEl(d, thinking){
    const seat=d.seat||'employee', present=!!d.present;
    const label=(seat==='boss'?'مدیر · ':'')+(seat==='secretary'?'منشی · ':'')+(d.role_title||d.name)+(present?'':(d.reason?` · غایب (${d.reason})`:' · غایب'));
    return `<div class="desk ${seat}${present?'':' empty'}${thinking?' thinking':''}" data-name="${esc(d.name)}" title="${esc(label)}"><div class="plate">${esc(label)}</div><div class="avt-wrap">${personSVG(d,present)}</div><div class="body"></div></div>`;
  }
  function layoutDesks(desks){
    const boss=desks.filter(d=>d.seat==='boss'), sec=desks.filter(d=>d.seat==='secretary'), emp=desks.filter(d=>d.seat==='employee');
    const pos=[];
    if(boss[0])pos.push([boss[0],420,530]);
    if(sec[0])pos.push([sec[0],600,530]);
    const cols=Math.min(6, Math.max(3, Math.ceil(Math.sqrt(emp.length||1)+1)));
    emp.forEach((d,i)=>{const r=Math.floor(i/cols),c=i%cols;pos.push([d, 70+c*150, 40+r*130]);});
    return pos;
  }
  let lastPkt=0;
  function flyPacket(fromName,toName){
    const a=document.querySelector('.desk[data-name="'+CSS.escape(fromName)+'"]');
    const b=document.querySelector('.desk[data-name="'+CSS.escape(toName||'')+'"]')||document.querySelector('.desk.boss');
    if(!a||!b)return;
    const ra=a.getBoundingClientRect(), rb=b.getBoundingClientRect();
    const el=document.createElement('div');el.className='pkt';el.textContent='{}';
    document.body.appendChild(el);
    const x0=ra.left+ra.width/2,y0=ra.top,x1=rb.left+rb.width/2,y1=rb.top,t0=performance.now();
    (function step(now){const t=Math.min(1,(now-t0)/900);const e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
      el.style.left=(x0+(x1-x0)*e)+'px';el.style.top=(y0+(y1-y0)*e-Math.sin(t*Math.PI)*80)+'px';
      if(t<1)requestAnimationFrame(step);else el.remove();})(t0);
  }
  window.renderOffice=function(s){
    const box=document.getElementById('office'); if(!box)return;
    const desks=s.desks||[];
    const officeOn=!s.mode||s.mode.office!==false;
    if(!officeOn && !desks.length){box.style.display='none';return;}
    box.style.display='block';
    const think=s.thinking&&s.thinking.name;
    const pos=layoutDesks(desks.length?desks:(s.participants||[]).map(p=>Object.assign({},p,{present:true,seat:'employee'})));
    box.innerHTML=`<div class="office-stage"><div class="office-room">${pos.map(([d,x,y])=>`<div style="left:${x}px;top:${y}px">${deskEl(d,think===d.name)}</div>`).join('')}</div></div>`;
    const w=document.getElementById('wires');
    if(w){w.innerHTML=(s.messages||[]).filter(m=>m.kind==='internal').slice(-12).map(m=>`<div>${esc((m.t||'')+'  '+(m.from||m.speaker)+' → '+(m.to||'boss')+'  '+(m.text||''))}</div>`).join('')||'<div>هنوز پیام رمزی نیست</div>';}
    const internals=(s.messages||[]).filter(m=>m.kind==='internal');
    if(internals.length>lastPkt){for(let i=lastPkt;i<internals.length;i++){const m=internals[i];flyPacket(m.from||m.speaker, m.to==='staff'?'':'');}}
    lastPkt=internals.length;
    renderApprovalBanner(s);
  };
  function compactBox(c){if(!c)return '';return `<div class="cbox">${c.claim?`<div><b>ادعا</b> ${esc(c.claim)}</div>`:''}${c.target?`<div><b>هدف</b> ${esc(c.target)}</div>`:''}${c.objection?`<div><b>اعتراض</b> ${esc(c.objection)}</div>`:''}${c.evidence?`<div><b>شاهد</b> ${esc(c.evidence)}</div>`:''}${c.confidence!=null?`<div><b>اطمینان</b> ${esc(c.confidence)}</div>`:''}</div>`;}
  function tokLbl(u){if(!u)return '';const n=u.total||((u.prompt||0)+(u.completion||0));return n?`<span class="pill">${n} tok${u.estimated?'~':''}</span>`:'';}

  const _msgHTML = window.msgHTML;
  window.msgHTML = function(m, office){
    if(m.kind==='internal' && office && !(document.getElementById('q-wires')||{}).checked) return '';
    if(m.kind==='secretary') return `<div class="seccard"><div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">${personSVG({name:m.speaker,role:'secretary',role_title:'منشی'},true)}<div><div class="t">گزارش کار</div><small>${esc(m.speaker)} · <span dir="ltr">${esc(m.model||'')}</span> · ${esc(m.t)}</small></div></div><div class="md" dir="auto">${mdlite(m.text)}</div></div>`;
    if(m.kind==='boss') return `<div class="msg" style="--c:#a99cff">${personSVG({name:m.speaker,role:'boss',role_title:'مدیر'},true,'lg')}<div class="bub bosscard" style="max-width:min(760px,82%)"><div class="meta"><b>${esc(m.speaker)}</b><span class="jbadge">مدیر</span>${m.model?`<span class="pill">${esc(m.model)}</span>`:''}${tokLbl(m.usage)}<span>${esc(m.t)}</span></div><div class="txt" dir="auto">${esc(m.text).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')}</div></div></div>`;
    if(m.kind==='system' || m.kind==='judge') return _msgHTML(m);
    const u=m.kind==='user';
    const prov=u?'user':(m.provider||'mock'), model=u?'':(m.model||'');
    const body=m.compact?compactBox(m.compact):`<div class="txt" dir="auto">${esc(m.text).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')}</div>`;
    const av=u?avatar('user','','lg'):personSVG({name:m.speaker,role:m.role,role_title:m.role_title},true,'lg');
    return `<div class="msg ${u?'user':''}" style="--c:${colorOf(prov,model)}">${av}<div class="bub"><div class="meta"><b>${esc(u?'سالار':m.speaker)}</b>${u?'':rbadge(m.role,m.role_title)}${m.kind==='mention'?'<span class="jbadge">پاسخ مستقیم</span>':''}${m.kind==='internal'?'<span class="pill">CODE</span>':''}${model?`<span class="pill">${esc(model)}</span>`:''}${tokLbl(m.usage)}<span>${esc(m.t)}</span></div>${body}</div></div>`;
  };

  const _poll = window.poll;
  window.poll = async function(){
    let s; try{s=await (await fetch('/api/state')).json()}catch(e){document.getElementById('status').textContent='سرور در دسترس نیست';return;}
    const st=document.getElementById('status');
    st.innerHTML=s.thinking?`<span class=spin></span> ${esc(s.thinking.name||'مدیر')} در حال نوشتن…`:s.status=='replying'?`<span class=spin></span> در حال پاسخ…`:s.running?`<span class=spin></span> دور ${s.round||1} از ${s.rounds||'?'}`:(s.status=='finished'?'✓ تمام شد':s.status=='stopped'?'■ متوقف شد':'');
    document.getElementById('ctitle').textContent=s.topic||((s.mode&&s.mode.office)?'دفتر هوش مصنوعی':'میزگرد هوش مصنوعی');
    const tu=s.usage||{}, tEl=document.getElementById('tok');
    if(tEl) tEl.textContent=tu.total?('tokens '+tu.total+'  in '+(tu.prompt||0)+'  out '+(tu.completion||0)+'  · '+(tu.calls||0)+' calls'):'';
    document.getElementById('stack').innerHTML=(s.participants||[]).slice(0,10).map(p=>avatar(p.provider,p.model)).join('');
    renderOffice(s);
    const th=s.thinking?JSON.stringify(s.thinking):'';
    if(s.messages.length===last&&th===lastThink)return;
    last=s.messages.length; lastThink=th;
    const c=document.getElementById('chat'); const first=!window._rendered; window._rendered=1;
    const atEnd=first||c.scrollHeight-c.scrollTop-c.clientHeight<120;
    if(!s.messages.length){c.innerHTML='<div class="empty"><img src="/static/icon.svg" alt=""><div style="font-size:17px;color:var(--txt);font-weight:700">با مدیر حرف بزن یا موضوع بنویس و «شروع کار دفتر» را بزن</div><div>مدیر با تو حرف می‌زند، کارکنان پشت صحنه با کد کار می‌کنند، منشی گزارش کار را می‌نویسد.</div></div>';return;}
    const office=!!(s.mode&&s.mode.office);
    let h=s.messages.map(m=>msgHTML(m,office)).join('');
    if(s.thinking){const t=s.thinking; const label=t.boss?'در حال تصمیم و حرف زدن با تو…':t.secretary?'در حال نوشتن گزارش کار…':t.mention?'در حال پاسخ مستقیم…':t.judge?'در حال نوشتن حکم نهایی…':(office?'در حال نوشتن گزارش رمزی…':'در حال نوشتن…');
      h+=`<div class="msg typing" style="--c:${colorOf(t.provider,t.model)}">${personSVG({name:t.name,role:t.boss?'boss':t.secretary?'secretary':'',role_title:t.boss?'مدیر':t.secretary?'منشی':''},true,'lg')}<div class="bub"><div class="meta"><b>${esc(t.name)}</b>${t.boss||t.secretary||t.judge?`<span class="jbadge">${t.boss?'مدیر':t.secretary?'منشی':'داور'}</span>`:''}<span>${label}</span></div><div class="dots"><i></i><i></i><i></i></div></div></div>`;}
    c.innerHTML=h; if(atEnd){if(first)c.style.scrollBehavior='auto';c.scrollTop=c.scrollHeight;if(first)setTimeout(()=>c.style.scrollBehavior='',50);}
  };

  window.toggleWires=function(){const w=document.getElementById('wires'); if(w)w.style.display=document.getElementById('q-wires').checked?'block':'none';};

  function fillSel(id, opts, val){const e=document.getElementById(id);if(!e)return;e.innerHTML=opts;if(val)e.value=val;}
  const _renderCfg = window.renderCfg;
  window.renderCfg=function(){
    const c=A.config||{}; const okp=(A.participants||[]).filter(p=>p.has_key);
    const jopts=okp.map(p=>`<option value="${esc(p.name)}" ${p.name==c.judge?'selected':''}>${esc(p.name)}${p.test&&p.test.status=='ok'?' ✓':''}</option>`).join('');
    const mopts=okp.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}${p.test&&p.test.status=='ok'?' ✓':''}</option>`).join('');
    fillSel('c-judgesel',jopts,c.judge); fillSel('q-judgesel',jopts,c.judge);
    fillSel('c-boss',mopts,c.manager); fillSel('q-boss',mopts,c.manager);
    fillSel('c-sec',mopts,c.secretary); fillSel('q-sec',mopts,c.secretary);
    const set=(id,fn)=>{const e=document.getElementById(id); if(e)fn(e);};
    set('c-rounds',e=>e.value=c.rounds||2);
    set('c-timeout',e=>e.value=c.timeout||60);
    set('c-roles',e=>e.checked=!!c.roles_enabled);
    set('c-judge',e=>e.checked=!!c.judge_enabled);
    set('c-office',e=>e.checked=c.office_enabled!==false);
    set('q-roles',e=>e.checked=!!c.roles_enabled);
    set('q-judge',e=>e.checked=!!c.judge_enabled);
    set('q-office',e=>e.checked=c.office_enabled!==false);
    set('q-judgesel',e=>e.disabled=!c.judge_enabled);
    const go=document.getElementById('bstart');
    if(go){const t=(c.office_enabled!==false)?'شروع کار دفتر':'شروع بحث'; const nodes=[...go.childNodes].filter(n=>n.nodeType===3); if(nodes.length)nodes[nodes.length-1].textContent=t; else go.appendChild(document.createTextNode(t));}
    if(!window._rset){const r=document.getElementById('rounds'); if(r)r.value=c.rounds||2; window._rset=1;}
  };

  const _saveCfgAdmin = window.saveCfgAdmin;
  window.saveCfgAdmin=async function(){
    await saveCfg({
      rounds:+document.getElementById('c-rounds').value,
      timeout:+(document.getElementById('c-timeout')||{}).value||60,
      roles_enabled:document.getElementById('c-roles').checked,
      office_enabled:!!(document.getElementById('c-office')||{}).checked,
      judge_enabled:document.getElementById('c-judge').checked,
      judge:document.getElementById('c-judgesel').value,
      manager:(document.getElementById('c-boss')||{}).value,
      secretary:(document.getElementById('c-sec')||{}).value
    });
    await savePerms();
    toast('تنظیمات ذخیره شد ✓');
  };

  const _start = window.start;
  window.start=async function(){
    const sel=[...document.querySelectorAll('.cpc:checked')].map(c=>c.value);
    const b=document.getElementById('bstart'); b.disabled=true;
    document.getElementById('status').innerHTML='<span class=spin></span> تست مدل‌ها…';
    const j=await post('/api/start',{
      topic:document.getElementById('topic').value, rounds:+document.getElementById('rounds').value,
      participants:sel, continue:document.getElementById('cont').checked,
      office_enabled:!!(document.getElementById('q-office')||{checked:true}).checked,
      judge_enabled:!!(document.getElementById('q-judge')||{}).checked,
      roles_enabled:!!(document.getElementById('q-roles')||{checked:true}).checked,
      manager:(document.getElementById('q-boss')||{}).value,
      secretary:(document.getElementById('q-sec')||{}).value,
      judge:(document.getElementById('q-judgesel')||{}).value
    });
    b.disabled=false; if(j.ok) toast((j.office?'دفتر با ':'')+(j.participants||[]).length+' کارمند حاضر'); loadAdmin();
  };

  const _renderAdmin = window.renderAdmin;
  window.renderAdmin=function(){
    _renderAdmin();
    // patch provider key cells if old "ندارد" still shown — renderAdmin in index uses keyb() which we wrapped
    const sug=document.getElementById('sug');
    if(sug) sug.innerHTML=(A.suggested||(A.providers||[]).filter(p=>p.signup&&!p.mock)).map(p=>{
      const need=typeof t==='function'?t('needKey'):'کلید لازمه';
      const has=typeof t==='function'?t('hasKey'):'کلید دارد';
      return `<a href="${esc(p.signup)}" target=_blank rel=noopener>${typeof avatar==='function'?avatar(p.id,''):''}<b>${esc(p.label)}</b> ${tierb(p.tier)}${p.has_key?'<span class="b ok">'+has+'</span>':'<span class="b grey">'+need+'</span>'}<small>${esc(p.signup)}</small></a>`;
    }).join('');
    renderPerms();
    renderScorecard();
    renderInspector();
  };

  const LOCKED=new Set(['wallet','payments']);
  window.renderPerms=function(){
    const box=document.getElementById('perm-body'); if(!box)return;
    const tools=A.tools||{}; const roles=Object.assign({}, (A.permissions&&A.permissions.roles)||{});
    const order=['boss','secretary'].concat(Object.keys(A.roles||{}).filter(k=>k!=='judge'));
    const toolIds=Object.keys(tools);
    const head='<tr><th>نقش</th>'+toolIds.map(t=>`<th title="${esc(tools[t]||t)}">${esc(t)}${LOCKED.has(t)?'<div class=lock>تأیید کاربر</div>':''}</th>`).join('')+'</tr>';
    const rows=order.map(role=>{
      const have=new Set(roles[role]||[]);
      return `<tr><td class=role>${esc(role==='boss'?'مدیر (boss)':role==='secretary'?'منشی (secretary)':((A.roles[role]||{}).title||role))}</td>`+
        toolIds.map(t=>{
          if(LOCKED.has(t)) return `<td><span class="lock" title="پرداخت و کیف پول همیشه نیاز به تأیید تو دارد">قفل</span></td>`;
          return `<td><input type=checkbox class="sw pchk" data-role="${esc(role)}" data-tool="${esc(t)}" ${have.has(t)?'checked':''}></td>`;
        }).join('')+'</tr>';
    }).join('');
    const mode=(A.config&&A.config.access_mode)||'ask';
    const askL=typeof t==='function'?t('accessAsk'):'پرسش (پیش‌فرض)';
    const autoL=typeof t==='function'?t('accessAuto'):'خودمختاری کامل';
    const hint=typeof t==='function'?t('accessHint'):'کیف‌پول و پرداخت همیشه نیاز به تأیید دارند.';
    const toggle=`<div class="row" style="gap:10px;flex-wrap:wrap;margin:8px 0 12px;align-items:center">
      <b>حالت دسترسی</b>
      <label class="toggle"><input type="radio" name="access-mode" value="ask" ${mode==='ask'?'checked':''} onchange="saveAccessMode('ask')"> ${askL}</label>
      <label class="toggle"><input type="radio" name="access-mode" value="autonomy" ${mode==='autonomy'?'checked':''} onchange="saveAccessMode('autonomy')"> ${autoL}</label>
    </div><p class="hint">${hint}</p>`;
    box.innerHTML=toggle+'<div class="perm" style="overflow:auto"><table><thead>'+head+'</thead><tbody>'+rows+'</tbody></table></div>';
  };
  window.saveAccessMode=async function(mode){
    const j=await post('/api/config',{access_mode:mode});
    if(j.ok){ if(A.config) A.config.access_mode=mode; toast(mode==='autonomy'?'خودمختاری کامل — پرداخت همچنان نیاز به تأیید دارد':'حالت پرسش'); }
  };
  window.savePerms=async function(){
    const roles={};
    document.querySelectorAll('.pchk').forEach(c=>{
      const r=c.dataset.role; roles[r]=roles[r]||[]; if(c.checked && !LOCKED.has(c.dataset.tool)) roles[r].push(c.dataset.tool);
    });
    const j=await post('/api/permissions',{roles}); if(j.ok){A.permissions=j.permissions; toast('مجوزها ذخیره شد');}
  };
  window.renderScorecard=async function(){
    const box=document.getElementById('score-body'); if(!box)return;
    try{
      const sc=await (await fetch('/api/scorecard')).json();
      const emps=sc.employees||{};
      const writes=sc.writeups||[];
      const names=Object.keys(emps);
      if(!names.length && !writes.length){ box.innerHTML='<p class="hint">هنوز کارنامه‌ای نیست. بعد از یک دور کار اینجا پر می‌شود.</p>'; return; }
      const rows=names.map(n=>{
        const e=emps[n];
        return `<tr><td>${esc(n)}</td><td>${esc(e.role_title||e.role||e.seat||'')}</td>
          <td>${e.calls||e.session_calls||0}</td><td>${e.tokens||e.session_tokens||0}</td>
          <td>${(e.avg_latency||e.last_latency||0)}</td>
          <td>${e.usefulness||0}</td><td>${e.fatigue||0}</td><td>${e.harm||0}</td>
          <td dir="auto">${esc((e.writeup||'').slice(0,180))}</td></tr>`;
      }).join('');
      const extra=writes.map(w=>`<li><b>${esc(w.name)}</b> — ${esc(w.text||'')}</li>`).join('');
      box.innerHTML=`<div style="overflow:auto"><table class="perm"><thead><tr><th>نام</th><th>نقش</th><th>فراخوان</th><th>توکن</th><th>latency</th><th>سودمندی</th><th>خستگی</th><th>آسیب</th><th>نوشتار</th></tr></thead><tbody>${rows}</tbody></table></div>`
        +(extra?`<ul class="hint" style="margin-top:8px">${extra}</ul>`:'')
        +`<p class="hint">به‌روزرسانی: ${esc(sc.updated||'')}</p>`;
    }catch(e){ box.innerHTML='<p class="hint">خواندن کارنامه ممکن نشد.</p>'; }
  };
  window.renderInspector=async function(){
    const box=document.getElementById('insp-body'); if(!box)return;
    try{
      const data=await (await fetch('/api/proposals')).json();
      const list=(data.proposals||[]).slice().reverse();
      if(!list.length){ box.innerHTML='<p class="hint">پیشنهادی در صف نیست. بعد از یک دور کار، بازرس پیشنهادها را می‌نویسد.</p>'; return; }
      box.innerHTML=list.map(p=>{
        const pending=p.status==='pending';
        const applyL=typeof t==='function'?t('apply'):'اعمال';
        const disL=typeof t==='function'?t('dismiss'):'رد';
        return `<div class="card" style="margin:8px 0;padding:10px;border:1px solid var(--line);border-radius:12px">
          <div class="row" style="justify-content:space-between;gap:8px;flex-wrap:wrap">
            <b>${esc(p.action||'')} → ${esc(p.target||'')}${p.value?' ('+esc(String(p.value))+')':''}</b>
            <span class="hint">${esc(p.status)} · ${esc((p.created_at||'').replace('T',' ').slice(0,19))} (Europe/Berlin)</span>
          </div>
          <p dir="auto" style="margin:6px 0">${esc(p.reason||'')}</p>
          ${pending?`<div class="row" style="gap:8px"><button class="btn pri sm" onclick="applyProposal('${p.id}')">${applyL}</button>
            <button class="btn sm" onclick="dismissProposal('${p.id}')">${disL}</button></div>`:''}
        </div>`;
      }).join('');
    }catch(e){ box.innerHTML='<p class="hint">خواندن پیشنهادها ممکن نشد.</p>'; }
  };
  window.applyProposal=async function(id){
    const j=await post('/api/proposals/apply',{id});
    if(j.ok){ toast('پیشنهاد اعمال شد'); if(j.config) A.config=j.config; renderInspector(); renderCfg(); }
  };
  window.dismissProposal=async function(id){
    const j=await post('/api/proposals',{id,dismiss:true});
    if(j.ok){ toast('رد شد'); renderInspector(); }
  };
  window.renderApprovalBanner=function(s){
    const bar=document.getElementById('appr-banner'); if(!bar)return;
    const pending=(s.approvals||[]).filter(a=>a.status==='pending');
    if(!pending.length){bar.style.display='none';bar.innerHTML='';return;}
    bar.style.display='block';
    bar.innerHTML=pending.map(a=>`<div class="appr"><b>نیاز به تأیید تو</b><span>${esc(a.actor)} درخواست ${esc(a.tool)}</span><span class="hint" dir="ltr">${esc(JSON.stringify(a.args||{}).slice(0,120))}</span><button class="btn sm go" onclick="decideAppr('${a.id}',true)">تأیید</button><button class="btn sm stop" onclick="decideAppr('${a.id}',false)">رد</button><span class="hint">پرداخت هرگز خودکار اجرا نمی‌شود</span></div>`).join('');
  };
  window.decideAppr=async function(id,ok){const j=await post('/api/approvals',{id,approve:ok}); if(j.ok) toast(ok?'تأیید شد (بدون اجرای خودکار پرداخت)':'رد شد');};

  // extra provider palettes if missing
  if(window.BR){
    Object.assign(BR,{
      huggingface:{c:'#ffd21e',bg:['#ffd21e','#e8a400'],g:'<circle cx="14" cy="16" r="5" fill="#fff"/><circle cx="26" cy="16" r="5" fill="#fff"/><circle cx="20" cy="24" r="8" fill="#fff"/>'},
      together:{c:'#0e8f7e',bg:['#12b39c','#0a6b5e'],g:'<circle cx="14" cy="20" r="5" fill="#fff"/><circle cx="26" cy="20" r="5" fill="#fff"/>'},
      fireworks:{c:'#ff6b3d',bg:['#ff8a4d','#c43a16'],g:'<path d="M20 8l3 8 8 1-6 5 2 8-7-4-7 4 2-8-6-5 8-1z" fill="#fff"/>'},
      novita:{c:'#6ea8ff',bg:['#3d6dff','#1e3fa8'],g:'<rect x="10" y="12" width="20" height="16" rx="4" fill="#fff"/>'},
      nvidia:{c:'#76b900',bg:['#86c81a','#3d6a00'],g:'<path d="M10 22c6-8 14-10 22-6-6 8-14 10-22 6z" fill="#fff"/>'},
      dashscope:{c:'#ff6a00',bg:['#ff8a1a','#c44a00'],g:'<rect x="10" y="12" width="20" height="16" rx="3" fill="#fff"/>'},
      zai:{c:'#4f7cff',bg:['#4f7cff','#1e3a8a'],g:'<circle cx="20" cy="20" r="8" fill="#fff"/>'},
      zhipu:{c:'#3b6cff',bg:['#3b6cff','#1a2f70'],g:'<circle cx="20" cy="20" r="8" fill="#fff"/>'},
      chutes:{c:'#c084fc',bg:['#a855f7','#6b21a8'],g:'<path d="M10 28c8-16 22-16 22 0" stroke="#fff" stroke-width="3" fill="none"/>'},
      cloudflare:{c:'#f78100',bg:['#f78100','#c45a00'],g:'<path d="M8 24h24l-6-10H16z" fill="#fff"/>'},
      deepinfra:{c:'#22c55e',bg:['#22c55e','#166534'],g:'<circle cx="20" cy="20" r="8" fill="#fff"/>'},
      siliconflow:{c:'#38bdf8',bg:['#38bdf8','#075985'],g:'<rect x="12" y="12" width="16" height="16" rx="4" fill="#fff"/>'},
      hyperbolic:{c:'#f43f5e',bg:['#fb7185','#9f1239'],g:'<path d="M10 28L20 8l10 20z" fill="#fff"/>'},
      nebius:{c:'#a3e635',bg:['#a3e635','#3f6212'],g:'<circle cx="20" cy="20" r="8" stroke="#fff" stroke-width="3" fill="none"/>'}
    });
  }
})();
