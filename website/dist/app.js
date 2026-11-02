'use strict';
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog,category='all',toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4500);}
const screens={library:['ad-library.png','The right data is a good place to start.','The actual Kira app dataset library'],inspect:['ad-inspect.png','Understand your data before using compute.','The actual Kira app data inspection screen'],soup:['ad-soup.png','Let Soup handle your complete local training run.','The actual Kira app optional Soup configuration review'],history:['ad-history.png','A little history. A clearer next step.','The actual Kira app activity history']};
document.querySelectorAll('[data-screen]').forEach(b=>b.addEventListener('click',()=>{const s=screens[b.dataset.screen];$('#product-image').src='assets/'+s[0];$('#product-image').alt=s[2];$('#screen-caption').textContent=s[1];document.querySelectorAll('[data-screen]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});}));
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#'+b.dataset.copy).textContent);toast('Copied. Your next step is in your terminal.');}catch{toast('Select the commands above to copy them.');}}));
function getHistory(){try{const value=JSON.parse(localStorage.getItem('kira-training-public-history')||'[]');return Array.isArray(value)?value.slice(0,12):[];}catch{return [];}}
function remember(name,rows){const history=getHistory();history.unshift({name:String(name).slice(0,160),rows,time:new Date().toISOString()});try{localStorage.setItem('kira-training-public-history',JSON.stringify(history.slice(0,12)));}catch{toast('Browser storage unavailable; this activity will not persist.');}renderHistory();}
function renderHistory(){const history=getHistory();$('#history-list').innerHTML=history.map(x=>`<li><span>${esc(x.name)} · ${esc(x.rows)} rows checked</span><small>${esc(new Date(x.time).toLocaleString())}</small></li>`).join('')||'<li>No checks yet. Start with a dataset above.</li>';}
$('#clear-history').addEventListener('click',()=>{try{localStorage.removeItem('kira-training-public-history');renderHistory();toast('Browser history cleared.');}catch{toast('Browser storage is unavailable.');}});renderHistory();
function renderLibrary(){
 const query=$('#dataset-search').value.trim().toLowerCase(),source=$('#dataset-source').value;
 const rows=catalog.datasets.filter(d=>(category==='all'||d.category===category)&&(source==='all'||d.kind===source)&&`${d.name} ${d.description} ${d.category}`.toLowerCase().includes(query));
 $('#dataset-count').textContent=`${rows.length} datasets`;
 $('#dataset-grid').innerHTML=rows.map(d=>{const c=catalog.categories.find(c=>c.id===d.category);return `<article class="dataset-card"><div class="card-top"><span class="dataset-symbol" aria-hidden="true">${esc(c.icon)}</span><span>${d.kind==='starter'?'KIRA STARTER':'PUBLIC DATASET'}</span></div><h3>${esc(d.name)}</h3><p>${esc(d.description)}</p><div class="tags"><span class="tag">${esc(c.name)}</span><span class="tag">${esc(d.license)}</span></div><div class="card-bottom"><span>${d.kind==='starter'?'6 synthetic examples':'Source-hosted files'}</span><button data-dataset="${esc(d.id)}">${d.kind==='starter'?'Explore & download':'Browse source files'} ↗</button></div></article>`;}).join('')||'<p class="empty">No matching datasets. Try another category or search.</p>';
 document.querySelectorAll('[data-dataset]').forEach(b=>b.addEventListener('click',()=>openDataset(b.dataset.dataset)));
}
$('#dataset-search').addEventListener('input',()=>catalog&&renderLibrary());$('#dataset-source').addEventListener('change',()=>catalog&&renderLibrary());
$('#dialog-close').addEventListener('click',()=>$('#dataset-dialog').close());
async function openDataset(id){
 const d=catalog.datasets.find(x=>x.id===id);if(!d)return;
 const panel=$('#dataset-details');panel.className='dataset-details';panel.innerHTML=`<p class="eyebrow">${d.kind==='starter'?'A SMALL START. A REAL WORKFLOW.':'DIRECT FROM THE SOURCE'}</p><h2>${esc(d.name)}</h2><p>${esc(d.description)}</p><p>License: <strong>${esc(d.license)}</strong>. Review the dataset card and underlying asset terms for your intended use.</p><div id="dataset-content"></div>`;$('#dataset-dialog').showModal();
 const target=$('#dataset-content');
 if(d.kind==='starter'){
  target.innerHTML=`<p>${d.category==='image'?'Text examples about image-edit review; no image pixels are included.':d.category==='live'?'Text conversations, not audio or streaming speech.':d.category==='preference'?'Prompt/chosen/rejected preference pairs for a compatible DPO trainer.':'Small synthetic examples for learning the data schema.'}</p><div class="actions"><a class="button dark" href="assets/datasets/${esc(d.category)}.jsonl" download>Download JSONL ↓</a><button class="button" id="try-starter">Check this starter</button></div><pre id="starter-preview">Loading example…</pre>`;
  try{const r=await fetch('assets/datasets/'+d.category+'.jsonl');if(!r.ok)throw Error('Starter file unavailable');const text=await r.text();if(!target.isConnected||!$('#dataset-dialog').open||!$('#starter-preview'))return;$('#starter-preview').textContent=JSON.stringify(JSON.parse(text.split('\n')[0]),null,2);$('#try-starter').addEventListener('click',()=>{$('#dataset-dialog').close();inspectText(text,d.name+'.jsonl');$('#inspect').scrollIntoView({behavior:'smooth'});});}catch(error){if($('#starter-preview'))$('#starter-preview').textContent=error.message;}
 }else{
  target.innerHTML=`<div class="actions"><a class="button" href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">Open dataset card ↗</a></div><p id="files-message" role="status">Resolving an immutable source revision…</p><div id="source-files"></div>`;
  try{
   const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),20000);
   let r;try{r=await fetch('https://huggingface.co/api/datasets/'+d.repo,{signal:controller.signal});}finally{clearTimeout(timeout);}
   if(!r.ok)throw Error('Source files could not be listed. Use the dataset card to check access.');const data=await r.json();
   if(!/^[a-f0-9]{40,64}$/.test(data.sha))throw Error('Source did not return a pinned revision. Please use the dataset card.');
   const files=(data.siblings||[]).filter(f=>/\.(json|jsonl|parquet|csv|tsv|zip|tar|gz|arrow|wav|flac)$/i.test(f.rfilename));
   if(!target.isConnected||!$('#files-message'))return;
   $('#files-message').textContent=`Revision ${data.sha.slice(0,12)} · ${files.length} source files${files.length>80?' · showing the first 80':''}. Keep evaluation files outside training. These links download from Hugging Face; file size and source access requirements apply.`;
   $('#source-files').innerHTML=files.slice(0,80).map(f=>{const path=f.rfilename.split('/').map(encodeURIComponent).join('/');return `<div class="source-file"><span>${esc(f.rfilename)}</span><a href="https://huggingface.co/datasets/${esc(d.repo)}/resolve/${data.sha}/${path}?download=true" target="_blank" rel="noopener noreferrer">Download ↓</a></div>`;}).join('')||'<p>No supported data files were listed. Browse the dataset card.</p>';
  }catch(error){if($('#files-message'))$('#files-message').textContent=error.name==='AbortError'?'The source took too long. Browse the dataset card directly.':error.message;}
 }
}
function stable(value,depth=0){if(depth>30)throw Error('Dataset nesting is too deep for this preview.');if(Array.isArray(value))return '['+value.map(x=>stable(x,depth+1)).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k],depth+1)).join(',')+'}';return JSON.stringify(value);}
function inspectText(text,name){
 const result=$('#inspection-result');result.hidden=false;
 try{
  if(new TextEncoder().encode(text).length>20*1024*1024)throw Error('Choose a file no larger than 20 MB.');
  let rows;if(text.trimStart().startsWith('[')){rows=JSON.parse(text);if(!Array.isArray(rows))throw Error('Expected a JSON array.');}else{rows=text.split(/\r?\n/).filter(x=>x.trim()).map((x,i)=>{try{return JSON.parse(x);}catch{throw Error('Invalid JSON at non-empty line '+(i+1));}});}
  if(!rows.length)throw Error('This dataset is empty.');
  let invalid=0,duplicates=0;const seen=new Set(),groups=new Map(),schemas=new Set();
  rows.forEach(row=>{
   if(!row||typeof row!=='object'||Array.isArray(row)){invalid++;return;}
   let schema;
   if(Array.isArray(row.messages)&&row.messages.length&&row.messages.every(m=>m&&typeof m.role==='string'&&typeof m.content==='string'))schema='chat';
   else if(typeof row.instruction==='string'&&typeof row.output==='string')schema='instruction/output';
   else if(typeof row.prompt==='string'&&typeof row.chosen==='string'&&typeof row.rejected==='string')schema='DPO';
   else{invalid++;return;}
   schemas.add(schema);
   const payload=Object.fromEntries(Object.entries(row).filter(([key])=>!['split','group_id','provenance','source','id'].includes(key)));const key=stable(payload);if(seen.has(key))duplicates++;seen.add(key);
   const raw=String(row.split||'train').toLowerCase();const split={training:'train',val:'eval',validation:'eval',valid:'eval',evaluation:'eval',dev:'eval',test:'eval'}[raw]||raw;
   for(const group of ['payload:'+key,...(row.group_id!==undefined?['group:'+String(row.group_id)]:[])]){if(!groups.has(group))groups.set(group,new Set());groups.get(group).add(split);}
  });
  const leakage=[...groups.values()].filter(s=>s.has('train')&&s.has('eval')).length;
  const report={filename:name,rows:rows.length,invalid_rows:invalid,duplicate_payloads:duplicates,explicit_leakage_groups:leakage,schemas:[...schemas],checked_at:new Date().toISOString(),note:'Browser-local structure preview. Does not certify privacy, semantic quality or training readiness.'};
  result.innerHTML=`<h3>${invalid||duplicates||leakage?'A few things to review.':'A little more clarity.'}</h3><div class="metrics"><div class="metric"><b>${rows.length}</b>rows</div><div class="metric"><b>${duplicates}</b>duplicates</div><div class="metric"><b>${invalid}</b>invalid rows</div></div><p>Schema: ${esc([...schemas].join(', ')||'unrecognized')} · Explicit leakage groups: ${leakage}</p><ul>${invalid?'<li>Review rows that do not match chat, instruction/output or string DPO fields.</li>':''}${duplicates?'<li>Duplicate training payloads were found. Review before preparing a run.</li>':''}${leakage?'<li>Training and evaluation rows share group IDs or exact payloads. Keep held-out data separate.</li>':''}<li>Structure checks do not establish training readiness. Review rights, privacy and task quality in your local app.</li></ul><button class="button small" id="download-report">Download inspection report ↓</button>`;
  $('#download-report').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='kira-inspection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});remember(name,rows.length);
 }catch(error){result.innerHTML=`<h3>Let’s take another look.</h3><p>${esc(error.message)}</p>`;}
}
async function inspectFile(file){if(!file)return;try{if(file.size>20*1024*1024)throw Error('Choose a file no larger than 20 MB.');inspectText(await file.text(),file.name);}catch(error){$('#inspection-result').hidden=false;$('#inspection-result').textContent=error.message;}}
$('#inspect-file').addEventListener('change',e=>inspectFile(e.target.files[0]));const drop=$('#file-drop');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');inspectFile(e.dataTransfer.files[0]);});
(async()=>{try{const response=await fetch('assets/catalog.json');if(!response.ok)throw Error('Library unavailable');catalog=await response.json();$('#category-filters').innerHTML=[{id:'all',name:'All datasets'},...catalog.categories].map(c=>`<button data-category="${esc(c.id)}" class="${c.id==='all'?'active':''}" aria-pressed="${c.id==='all'}">${esc(c.name)}</button>`).join('');document.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=b.dataset.category;document.querySelectorAll('[data-category]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});renderLibrary();}));renderLibrary();}catch{$('#dataset-grid').innerHTML='<p class="empty">The dataset library could not load. Please refresh or explore the catalog in the local app.</p>';}})();
