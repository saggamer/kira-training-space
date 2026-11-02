const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state, token, category='all', selected=null, toastTimer;
let selectedPlan=null;
const titles={discover:'Dataset library',inspect:'Data inspector',train:'Training studio',history:'Activity history',lessons:'Experience library',connect:'Connections'};
async function api(path, body){
  const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Kira-Token':token},body:JSON.stringify(body)});
  const value=await response.json(); if(!response.ok) throw Error(value.error || 'Request failed'); return value;
}
function toast(message){ $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,6500); }
async function busy(button, task){const previous=button?.textContent; if(button){button.disabled=true;button.textContent='Working…';}try{return await task();}catch(error){toast(error.message);}finally{if(button){button.disabled=false;button.textContent=previous;}}}
function view(name){
  if(!titles[name]) return;
  $$('.view').forEach(e=>e.hidden=e.id!==name); $$('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('#crumb').textContent=titles[name];window.scrollTo(0,0);
  if(name==='history')api('state').then(next=>{state=next;renderHistory();}).catch(e=>toast(e.message));
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b)view(b.dataset.view);});
function modal(title, eyebrow, html){$('#modal-title').textContent=title;$('#modal-eyebrow').textContent=eyebrow;$('#modal-body').innerHTML=html;$('#modal').showModal();}
$('#modal-close').onclick=()=>$('#modal').close();
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
function cat(id){return state.categories.find(c=>c.id===id);}
async function refresh(){state=await api('state');render();}
function filterCategory(id){category=id;renderCategories();renderDatasets();}
function renderCategories(){
 $('#categories').innerHTML=state.categories.map(c=>`<button class="category category-${c.id} ${category===c.id?'selected':''}" data-category="${c.id}" aria-pressed="${category===c.id}"><span class="category-icon">${c.icon}</span><strong>${c.name}</strong><small>${c.description}</small></button>`).join('');
 $('#filters').innerHTML=[{id:'all',name:'All datasets'},...state.categories.map(c=>({id:c.id,name:{agentic:'Agentic',live:'Live & voice',image:'Image editing',coding:'Coding',reasoning:'Reasoning',preference:'Preference'}[c.id]}))].map(c=>`<button class="filter ${category===c.id?'active':''}" data-category="${c.id}">${c.name}</button>`).join('');
 $$('[data-category]').forEach(b=>b.onclick=()=>filterCategory(b.dataset.category));
}
function renderDatasets(){
 const query=$('#search').value.toLowerCase(), source=$('#source-filter').value;
 const rows=state.catalog.filter(d=>(category==='all'||d.category===category)&&(source==='all'||d.kind===source)&&`${d.name} ${d.description} ${d.category}`.toLowerCase().includes(query));
 $('#dataset-count').textContent=rows.length;
 $('#dataset-grid').innerHTML=rows.map(d=>`<article class="dataset-card"><div class="card-top"><span class="dataset-icon">${cat(d.category).icon}</span><span class="source-tag">${d.kind==='starter'?'KIRA STARTER':'OPEN DATASET'}</span></div><h3>${esc(d.name)}</h3><p>${esc(d.description)}</p><div class="tags"><span class="tag">${cat(d.category).name}</span><span class="tag">${esc(d.license)}</span><span class="tag">${esc(d.format)}</span></div><div class="card-bottom"><span>${d.kind==='starter'?'6 synthetic examples · JSONL':'Source-hosted · revision-pinned'}</span><button data-dataset="${d.id}">${d.kind==='starter'?'Try dataset':'Browse files'} ↗</button></div></article>`).join('')||'<div class="empty-grid">No datasets match. Try another category or search.</div>';
 $$('[data-dataset]').forEach(b=>b.onclick=()=>openDataset(b.dataset.dataset,b));
}
async function openDataset(id,button){
 const d=state.catalog.find(d=>d.id===id);
 if(d.kind==='starter'){
  modal(d.name,'SMALL START. REAL WORKFLOW.',`<p class="muted">${esc(d.description)}</p><div class="info-box">${d.category==='image'?'This starter contains text examples about image-edit review. It does not contain source or target images.':d.category==='live'?'This is text conversation data. Speech training requires audio data and a compatible trainer.':'These examples demonstrate the schema. They are not a production corpus or a model quality claim.'}</div><div class="button-row"><a class="button" href="/api/download?id=${id}">↓ Download JSONL</a><button class="button dark" id="starter-inspect">Add & inspect ↗</button></div><pre id="starter-preview">Loading preview…</pre>`);
  fetch('/api/download?id='+id+'&preview=1').then(r=>r.text()).then(t=>{if($('#starter-preview'))$('#starter-preview').textContent=t.split('\n').slice(0,2).map(x=>JSON.stringify(JSON.parse(x),null,2)).join('\n\n');}).catch(e=>toast(e.message));
  $('#starter-inspect').onclick=e=>busy(e.target,async()=>{const item=await api('starter',{id});$('#modal').close();await refresh();view('inspect');showInspection(item);});
 } else await busy(button,async()=>{
  const result=await api('files',{id});
  modal(d.name,'DIRECT FROM THE SOURCE',`<p class="muted">${esc(d.description)}</p><div class="info-box">License: ${esc(result.license)}. Check the dataset card and underlying asset terms before use. Files can be large.</div><p class="muted">Revision <code>${esc(result.revision.slice(0,12))}</code> · ${result.files.length} files · <a href="${esc(result.source_url)}" target="_blank" rel="noopener noreferrer">Dataset card ↗</a></p><div>${result.files.map(f=>`<div class="file-item"><span>${esc(f.name)} <small class="tag">${esc(f.split_hint)}</small></span><a data-source-file="${esc(f.name)}" href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">Download ↓</a></div>`).join('')||'<p>No supported files were returned. Visit the source dataset card.</p>'}</div><div class="info-box">Keep evaluation files out of your training corpus. Split labels here are inferred from file paths; verify the official dataset split before use.</div><p class="muted">${esc(result.note)}</p>`);
  $$('[data-source-file]').forEach(a=>a.addEventListener('click',()=>{api('source-download',{id,filename:a.dataset.sourceFile}).catch(e=>toast(e.message));}));
 });
}
function importModal(){
 modal('Bring your dataset.','YOUR DATA, YOUR WORKSPACE',`<form id="import-form"><label>Dataset name<input name="name" placeholder="e.g. Customer support conversations" required maxlength="160"></label><label>Model category<select name="category">${state.categories.map(c=>`<option value="${c.id}">${c.name}</option>`).join('')}</select></label><div class="file-drop"><strong>Choose a JSON or JSONL file</strong><input type="file" id="data-file" accept=".json,.jsonl,application/json" required><p>UTF-8 · up to 20 MB · stored locally</p></div><div class="info-box">Supported rows: chat messages, instruction/output, or prompt/chosen/rejected. Image and audio binary files require their own data tooling.</div><button class="button dark" type="submit">Import & inspect ↗</button></form>`);
 $('#import-form').onsubmit=e=>{e.preventDefault();busy($('button[type=submit]',e.target),async()=>{const file=$('#data-file').files[0];if(file.size>20*1024*1024)throw Error('Choose a file under 20 MB.');const f=new FormData(e.target);const item=await api('import',{name:f.get('name'),category:f.get('category'),content:await file.text()});$('#modal').close();await refresh();view('inspect');showInspection(item);});};
}
function renderLocals(){
 $('#local-datasets').innerHTML=state.datasets.map(d=>`<div class="local-item"><button data-local="${d.id}">${esc(d.name)}<small>${cat(d.category).name} · ${d.report.rows} rows · ${d.report.schema}</small></button><span class="status ${d.report.ready?'':'warn'}">${d.report.ready?'Parsed':'Review'}</span></div>`).join('')||'<div class="empty-state"><span>▧</span><h3>Your library starts here.</h3><p>Import a dataset or add a starter from the dataset library.</p></div>';
 $$('[data-local]').forEach(b=>b.onclick=()=>showInspection(state.datasets.find(d=>d.id===b.dataset.local)));
 const previous=$('#train-dataset').value;
 const soup=$('#training-backend').value==='soup';
 const starters=state.catalog.filter(d=>d.kind==='starter'&&d.category!=='image'&&(soup||d.category!=='preference'));
 const locals=state.datasets.filter(d=>d.category!=='image'&&(soup||d.category!=='preference'));
 $('#train-dataset').innerHTML=`<optgroup label="Your imported data">${locals.map(d=>`<option value="${d.id}">${esc(d.name)} (${d.report.rows} rows)</option>`).join('')}</optgroup><optgroup label="Synthetic workflow starters">${starters.map(d=>`<option value="${d.id}">${d.name} (6 rows)</option>`).join('')}</optgroup>`;
 if([...$('#train-dataset').options].some(o=>o.value===previous))$('#train-dataset').value=previous;
}
function showInspection(d){
 selected=d.id;const r=d.report;
 $('#inspection').innerHTML=`<h3>${esc(d.name)}</h3><span class="status ${r.ready?'':'warn'}">${r.ready?'Structure checks passed · review before training':'Needs attention'}</span><div class="metric-grid"><div class="metric"><b>${r.rows}</b>rows</div><div class="metric"><b>${r.duplicates}</b>duplicates</div><div class="metric"><b>${r.leakage.length}</b>leakage groups</div></div><p class="muted">Schema: ${esc(r.schema)} · Valid rows: ${r.valid_rows} · Invalid entries: ${r.invalid_rows}</p><ul class="warning-list">${r.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}${r.errors.map(e=>`<li>Row ${e.row}: ${esc(e.message)}</li>`).join('')}${r.leakage.map(g=>`<li>Cross-split leakage: ${esc(g)}</li>`).join('')}</ul><div class="button-row"><button class="button" id="soup-inspect">Inspect with Soup ↗</button><a class="button" href="/api/download?id=${d.id}">↓ JSONL</a><button class="button dark" id="use-dataset">Use in training ↗</button></div><pre id="soup-report" hidden></pre><details><summary>Preview rows & provenance</summary><pre>${esc(JSON.stringify(r.preview,null,2))}</pre><p class="muted">SHA-256: ${esc(r.sha256)}</p></details>`;
 $('#soup-inspect').onclick=e=>busy(e.target,async()=>{const result=await api('soup',{action:'data_inspect',dataset_id:d.id});$('#soup-report').hidden=false;$('#soup-report').textContent=toolText(result);});
 $('#use-dataset').onclick=()=>{
  if(d.category==='image'){toast('Image training needs a compatible recipe and actual source/target images.');view('connect');return;}
  if(d.category==='preference'||r.schema!=='chat')$('#training-backend').value='soup';
  $('#soup-task-label select').value=r.schema==='dpo'?'dpo':'sft';
  $('#training-backend').onchange();$('#train-dataset').value=d.id;view('train');
 };
}
function toolText(r){return r.content?.map(c=>c.text||'').join('\n') || JSON.stringify(r,null,2);}
function showPlan(plan){
 if(plan.backend==='soup')return showSoupPlan(plan);
 selectedPlan=plan.id;
 $('#plan-result').innerHTML=`<span class="status">Prepared · not running</span><h3>${esc(plan.name)}</h3><p class="muted">${esc(plan.model)} · ${esc(plan.gpu)} · ${plan.report.rows} source rows</p><ul class="warning-list">${plan.checks.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><pre id="plan-command"></pre><div class="button-row"><button class="button" id="copy-command">Copy command</button><a class="button dark" href="/api/bundle?id=${plan.id}">↓ Training bundle</a></div><div class="info-box">${esc(plan.note)} The runner uses a grouped holdout and records baseline and candidate loss. Task evaluation remains required.</div><details><summary>Run on Colab</summary><p class="muted">Download the bundle. In a Colab notebook with a GPU, install requirements, upload train.py and run it. Or use the command above from your terminal with an authenticated Colab CLI.</p></details>`;
 $('#plan-command').textContent=plan.command;
 const runControls=document.createElement('div');
 if(plan.status==='prepared'){
  runControls.innerHTML='<button class="button dark" id="start-colab">Start on Colab ↗</button>';
  $('#plan-result').append(runControls);
  $('#start-colab').onclick=()=>{
   modal('Ready to use cloud compute?','REVIEW THIS TRAINING RUN',`<p class="muted">Model: ${esc(plan.model)}<br>Data: ${plan.report.rows} rows · GPU: ${esc(plan.gpu)}</p><div class="info-box">This sends only the prepared training script and its embedded dataset to Google Colab, installs the pinned trainer dependencies, and starts a ${esc(plan.gpu)} runtime using your authenticated account. Compute may be billed. The runtime stays active after training until you stop it. Review data rights and privacy before proceeding.</div><label><input type="checkbox" id="compute-consent"> I reviewed the data and authorize this cloud training run.</label><div class="button-row"><button class="button dark" id="confirm-start" disabled>Authorize & start training</button></div>`);
   $('#compute-consent').onchange=e=>$('#confirm-start').disabled=!e.target.checked;
   $('#confirm-start').onclick=e=>busy(e.target,async()=>{await api('start',{id:plan.id,confirmed:true});$('#modal').close();await refresh();showPlan(state.plans.find(p=>p.id===plan.id));toast('Submitted to Colab. Stop the runtime when you finish.');});
  };
 }else{
  $('#plan-result .status').textContent=plan.status.replaceAll('_',' ')+(plan.runtime_stopped?' · runtime stopped':' · check runtime');
  runControls.innerHTML=`<pre>${esc(plan.log||'Waiting for Colab…')}</pre><div class="button-row">${plan.status==='completed'?'<button class="button dark" id="download-adapter">↓ Download adapter</button>':''}${!plan.runtime_stopped?'<button class="button" id="stop-colab">Stop runtime</button>':''}</div>`;
  $('#plan-result').append(runControls);
  if($('#download-adapter'))$('#download-adapter').onclick=e=>busy(e.target,async()=>{const r=await fetch('/api/artifact',{method:'POST',headers:{'Content-Type':'application/json','X-Kira-Token':token},body:JSON.stringify({id:plan.id})});if(!r.ok)throw Error((await r.json()).error);const url=URL.createObjectURL(await r.blob());const link=document.createElement('a');link.href=url;link.download='kira-adapter.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);});
  if($('#stop-colab'))$('#stop-colab').onclick=()=>{
   modal('Stop this Colab runtime?','RELEASE YOUR COMPUTE',`<p class="muted">Session: ${esc(plan.session)}</p><div class="info-box">Stopping discards runtime files and interrupts any running training. Download your adapter first if you need to keep it.</div><button class="button dark" id="confirm-stop">Stop runtime & discard remote files</button>`);
   $('#confirm-stop').onclick=e=>busy(e.target,async()=>{const r=await api('stop',{id:plan.id,confirmed:true});if(!r.ok)throw Error(r.message);$('#modal').close();await refresh();showPlan(state.plans.find(p=>p.id===plan.id));toast('Colab runtime stopped.');});
  };
 }
 $('#copy-command').onclick=e=>busy(e.target,async()=>{try{await navigator.clipboard.writeText(plan.command);toast('Command copied. Review it before running.');}catch{toast('Clipboard unavailable. Select and copy the command above.');}});
}
function renderPlans(){
 $('#plans').innerHTML=state.plans.map(p=>`<button class="panel plan-card" data-plan="${p.id}"><span class="status">${esc(p.status.replaceAll('_',' '))}</span><h3>${esc(p.name)}</h3><p class="muted">${esc(p.model)} · ${esc(p.gpu)}</p><p class="muted">View plan ↗</p></button>`).join('')||'<p class="muted">Your prepared runs will appear here.</p>';
 $$('[data-plan]').forEach(b=>b.onclick=()=>{showPlan(state.plans.find(p=>p.id===b.dataset.plan));window.scrollTo(0,0);});
}
function renderLessons(){ $('#lessons-grid').innerHTML=state.lessons.map((l,i)=>`<article class="lesson"><span>0${i+1} / ◈</span><h3>${esc(l.title)}</h3><p>${esc(l.body)}</p><code>${esc(l.source)}</code></article>`).join(''); }
function renderConnections(){
 $('#connections').innerHTML=[{name:'Soup',icon:'≋',desc:'Optional complete local training: inspect, validate, train SFT or DPO, track runs and export through Soup.',status:state.connections.soup.installed?'Installed · inspect to verify':'Setup needed'},{name:'Google Colab',icon:'∞',desc:'Connect to cloud GPUs through the official CLI. Use the same sessions and authentication.',status:state.connections.colab.installed?'CLI detected · refresh to connect':'Setup needed'},{name:'Codex',icon:'⌘',desc:'Local plugin with dataset, inspection, Colab plans and optional full Soup training tools.',status:state.connections.codex?.installed?'Installed · new chat may be needed':'Plugin package available'},{name:'Kira Superapp',icon:'K',desc:'Open Training Space from Kira Settings → Plugins after enabling the bundled Kira Training Space extension.',status:state.connections.kira?.enabled?'Enabled · restart Kira to load UI':'Bundled local extension'}].map(c=>`<article class="panel connection"><span class="category-icon">${c.icon}</span><h3>${c.name}</h3><p>${c.desc}</p><span class="status">${c.status}</span></article>`).join('');
}
function renderHistory(){
 const filter=$('#history-filter').value, query=$('#history-search').value.toLowerCase();
 const events=(state.history||[]).filter(e=>(filter==='all'||e.kind===filter)&&`${e.title} ${JSON.stringify(e.details)}`.toLowerCase().includes(query));
 const icons={datasets:'▧',inspection:'⌕',training:'ϟ',downloads:'↓',notes:'◈'};
 $('#history-list').innerHTML=events.map(e=>{
  const dataset=state.datasets.some(d=>d.id===e.entity_id),plan=state.plans.some(p=>p.id===e.entity_id);
  return `<article class="history-event"><span class="history-icon">${icons[e.kind]||'◷'}</span><div class="history-content"><h3>${esc(e.title)}</h3><div class="history-meta"><span class="tag">${esc(e.kind)}</span><time datetime="${esc(e.created)}">${esc(new Date(e.created).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}))}</time></div><details><summary>Activity details</summary><pre>${esc(JSON.stringify(e.details,null,2))}</pre></details></div>${dataset||plan?`<button class="button" data-history-entity="${esc(e.entity_id)}" data-history-type="${dataset?'dataset':'plan'}">Open ↗</button>`:''}</article>`;
 }).join('')||'<div class="empty-state"><span>◷</span><h3>A fresh page in your story.</h3><p>Add a dataset or prepare a run. Your activity will appear here.</p></div>';
 $$('[data-history-entity]').forEach(b=>b.onclick=()=>{if(b.dataset.historyType==='dataset'){view('inspect');showInspection(state.datasets.find(d=>d.id===b.dataset.historyEntity));}else{view('train');showPlan(state.plans.find(p=>p.id===b.dataset.historyEntity));}});
}
function render(){renderCategories();renderDatasets();renderLocals();renderPlans();renderLessons();renderConnections();renderHistory();}
$('#import-open').onclick=importModal;$('#inspector-import').onclick=importModal;
$('#own-dataset-open').onclick=importModal;
$('#history-search').oninput=renderHistory;$('#history-filter').onchange=renderHistory;
$('#history-refresh').onclick=e=>busy(e.target,refresh);
$('#search').oninput=renderDatasets;$('#source-filter').onchange=renderDatasets;$('#all-types').onclick=()=>filterCategory('all');
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();view('discover');$('#search').focus();}});
$('#training-form').onsubmit=e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));busy($('button[type=submit]',e.target),async()=>{const p=await api(body.backend==='soup'?'soup-plan':'plan',body);await refresh();showPlan(p);toast('Plan prepared. No compute has been started.');});};
$('#colab-refresh').onclick=e=>busy(e.target,async()=>{const r=await api('colab',{action:'sessions'});$('#colab-result').textContent=r.ok?r.output:r.message;});
$('#colab-usage').onclick=e=>busy(e.target,async()=>{const r=await api('colab',{action:'usage'});$('#colab-result').textContent=r.ok?r.output:r.message;});
$('#recipe-form').onsubmit=e=>{e.preventDefault();busy($('button',e.target),async()=>{
 const result=await api('soup',{action:'recipes_search',recipe:new FormData(e.target).get('query')});
 const text=toolText(result);$('#recipe-result').textContent=text;
 try{
  const data=JSON.parse(text), recipes=Array.isArray(data)?data:data.recipes||data.results||[];
  let cards=$('#recipe-cards');if(!cards){cards=document.createElement('div');cards.id='recipe-cards';$('#recipe-result').after(cards);}
  if(recipes.length){$('#recipe-result').hidden=true;cards.innerHTML=recipes.map(r=>`<div class="local-item"><div><strong>${esc(r.name)}</strong><p class="muted">${esc(r.description||r.model||'')}</p></div><button class="button" data-recipe="${esc(r.name)}">View recipe ↗</button></div>`).join('');
   $$('[data-recipe]').forEach(b=>b.onclick=()=>busy(b,async()=>{
    const result=await api('soup',{action:'recipes_show',recipe:b.dataset.recipe});const text=toolText(result);
    let yaml=text;try{yaml=JSON.parse(text).yaml_str||text;}catch{}
    modal(b.dataset.recipe,'A SOUP TRAINING RECIPE',`<div class="info-box">Review the model, data paths, hardware and dependencies before execution. This recipe has not been run by Kira.</div><pre id="recipe-yaml"></pre><button class="button dark" id="download-recipe">↓ Download recipe YAML</button>`);
    $('#recipe-yaml').textContent=yaml;$('#download-recipe').onclick=()=>{const url=URL.createObjectURL(new Blob([yaml],{type:'text/yaml'}));const link=document.createElement('a');link.href=url;link.download='soup.yaml';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
   }));
  }else{$('#recipe-result').hidden=false;cards.innerHTML='';}
 }catch{$('#recipe-result').hidden=false;}
});};
$('#lesson-open').onclick=()=>{
 modal('Keep the lesson.','LEARN FROM THE EVIDENCE',`<form id="lesson-form"><label>Title<input name="title" required maxlength="160"></label><label>What did you learn?<textarea name="body" rows="4" required maxlength="4000"></textarea></label><label>Evidence reference<input name="evidence" placeholder="Run ID, report path or evaluation reference" required maxlength="1000"></label><div class="info-box">Record a reviewed observation with its evidence. Notes guide future decisions; they do not retrain a model.</div><button class="button dark" type="submit">Save reviewed lesson ↗</button></form>`);
 $('#lesson-form').onsubmit=e=>{e.preventDefault();busy($('button',e.target),async()=>{await api('lesson',Object.fromEntries(new FormData(e.target)));$('#modal').close();await refresh();toast('Lesson saved locally.');});};
};
(async()=>{try{token=(await api('session')).token;await refresh();}catch(e){toast('Could not load the workspace: '+e.message);}})();
setInterval(async()=>{if(state?.plans.some(p=>['starting','running'].includes(p.status))){try{state=await api('state');renderPlans();const p=state.plans.find(p=>p.id===selectedPlan);if(p&&!$('#modal').open)showPlan(p);}catch{}}},10000);

$('#training-backend').onchange=()=>{const soup=$('#training-backend').value==='soup';$('#soup-task-label').hidden=!soup;$('#colab-accelerator-label').hidden=soup;renderLocals();};
function showSoupPlan(plan){
 selectedPlan=plan.id;
 $('#plan-result').innerHTML=`<span class="status">Soup · ${esc(plan.status)}</span><h3>${esc(plan.name)}</h3><p class="muted">${esc(plan.model)} · ${esc(plan.task.toUpperCase())} · ${plan.report.rows} rows</p><div class="info-box">${esc(plan.note)}</div><ul class="warning-list">${plan.checks.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><details open><summary>Review exact Soup configuration</summary><pre>${esc(JSON.stringify(plan.config,null,2))}</pre></details><pre>${esc(plan.command)}</pre><div class="button-row"><a class="button" href="/api/bundle?id=${plan.id}">↓ Configuration & data</a>${plan.status==='prepared'?'<button class="button dark" id="soup-start">Review & train with Soup ↗</button>':'<button class="button" id="soup-status">Refresh Soup run</button>'}</div>${plan.soup_run_id?`<p class="muted">Run: ${esc(plan.soup_run_id)}</p>`:''}<pre>${esc(plan.log||'')}</pre>${plan.status==='completed'?'<label>Export format<select id="export-format"><option>gguf</option><option>onnx</option><option>awq</option><option>gptq</option></select></label><button class="button" id="soup-export">Review Soup export</button>':''}`;
 if($('#soup-start'))$('#soup-start').onclick=()=>{
  modal('Train entirely with Soup?','REVIEW LOCAL COMPUTE',`<p>${esc(plan.model)} · ${esc(plan.task)} · ${plan.report.rows} rows</p><div class="info-box">Soup will download model weights as needed and run training on this computer using its installed trainer dependencies. Review the configuration, data rights, available memory and evaluation plan. Keep the app open. The single-use confirmation expires five minutes after preparation.</div><label><input type="checkbox" id="soup-consent"> I reviewed this plan and authorize local Soup training.</label><button class="button dark" id="soup-confirm" disabled>Authorize & train</button>`);
  $('#soup-consent').onchange=e=>$('#soup-confirm').disabled=!e.target.checked;
  $('#soup-confirm').onclick=e=>busy(e.target,async()=>{const p=await api('soup-start',{id:plan.id,confirmed:true});$('#modal').close();await refresh();showSoupPlan(p);});
 };
 if($('#soup-status'))$('#soup-status').onclick=e=>busy(e.target,async()=>{const p=await api('soup-status',{id:plan.id});await refresh();showSoupPlan(p);});
 if($('#soup-export'))$('#soup-export').onclick=e=>busy(e.target,async()=>{
  const format=$('#export-format').value;const review=await api('soup-export',{id:plan.id,format});
  modal('Export with Soup?','REVIEW EXPORT',`<pre>${esc(review.would_run)}</pre><div class="info-box">This conversion uses local compute and writes to the shown export directory. Format support depends on your model and installed Soup dependencies.</div><button class="button dark" id="export-confirm">Authorize this export</button>`);
  $('#export-confirm').onclick=e=>busy(e.target,async()=>{const r=await api('soup-export',{id:plan.id,format,confirmed:true});$('#modal-body').textContent='Export running · '+r.run_id;});
 });
}
