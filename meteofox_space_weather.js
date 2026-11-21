(()=>{
'use strict';

const $=id=>document.getElementById(id);
function tab(which){for(const k of ['aviation','satellites']){const on=k===which;$(k).hidden=!on;$('tab-'+k).setAttribute('aria-selected',String(on))}}
$('tab-aviation').onclick=()=>tab('aviation');$('tab-satellites').onclick=()=>tab('satellites');
async function json(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function time(s){const d=new Date(s);return Number.isFinite(d.getTime())?d.toLocaleString('pt-PT',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+' UTC':'Hora indisponível'}
function valid(v){return v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))}
async function load(){
$('status').textContent='A atualizar indicadores NOAA…';
for(const id of ['kp','xray','speed','bz'])$(id).textContent='—';
$('kpTime').textContent='NOAA SWPC · índice planetário';
$('xrayTime').textContent='GOES · classificação indicativa';
$('speedTime').textContent='Velocidade · km/s';
$('bzTime').textContent='Componente magnética · nT';
let successes=0;
const results=await Promise.allSettled([
json('https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json'),
json('https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json'),
json('https://services.swpc.noaa.gov/products/summary/solar-wind-speed.json'),
json('https://services.swpc.noaa.gov/products/summary/solar-wind-mag-field.json'),
json('https://services.swpc.noaa.gov/products/geospace/propagated-solar-wind-1-hour.json')]);
if(results[0].status==='fulfilled'){
const data=results[0].value;
const a=(Array.isArray(data)?data:[]).map(r=>Array.isArray(r)?{time_tag:r[0],Kp:r[1]}:r).filter(r=>r&&valid(r.Kp));
if(a.length){const x=a[a.length-1];$('kp').textContent=Number(x.Kp).toFixed(1);$('kpTime').textContent=time(x.time_tag);successes++}
}
if(results[1].status==='fulfilled'){
const a=results[1].value.filter(r=>r.energy==='0.1-0.8nm'&&valid(r.flux));
if(a.length){const x=a[a.length-1],f=Number(x.flux);$('xray').textContent=f>=1e-4?'X'+(f/1e-4).toFixed(1):f>=1e-5?'M'+(f/1e-5).toFixed(1):f>=1e-6?'C'+(f/1e-6).toFixed(1):f>=1e-7?'B'+(f/1e-7).toFixed(1):'A'+(f/1e-8).toFixed(1);$('xrayTime').textContent=time(x.time_tag);successes++}
}
if(results[2].status==='fulfilled'){
const a=results[2].value.filter(r=>r&&valid(r.proton_speed));
if(a.length){const x=a[a.length-1];$('speed').textContent=Math.round(Number(x.proton_speed))+' km/s';$('speedTime').textContent=time(x.time_tag);successes++}
}
if(results[3].status==='fulfilled'){
const a=results[3].value.filter(r=>r&&valid(r.bz_gsm));
if(a.length){const x=a[a.length-1];$('bz').textContent=Number(x.bz_gsm).toFixed(1)+' nT';$('bzTime').textContent=time(x.time_tag);successes++}
}
if(results[4].status==='fulfilled'){
const a=results[4].value;
const header=Array.isArray(a[0])?a[0]:[];
const ti=header.indexOf('propagated_time_tag'),si=header.indexOf('speed');
const rows=a.slice(1).filter(r=>Array.isArray(r)&&si>=0&&valid(r[si]));
const sample=rows.filter((_,i)=>i%Math.max(1,Math.floor(rows.length/60))===0).slice(-60);
if(sample.length){const max=Math.max(700,...sample.map(r=>Number(r[si])));$('speedChart').replaceChildren(...sample.map(r=>{const b=document.createElement('div');b.className='bar';b.style.height=(Number(r[si])/max*100)+'%';b.title=time(r[ti>=0?ti:0])+' · '+r[si]+' km/s';return b}));$('chartCaption').textContent='Vento solar propagado · série NOAA da última hora (UTC)'}
}
$('status').textContent=successes===4?'4/4 indicadores NOAA disponíveis · '+new Date().toLocaleTimeString('pt-PT',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'})+' UTC':successes?'Atualização parcial ('+successes+'/4 indicadores) · verificar fontes':'Fontes NOAA indisponíveis neste momento · consultar ligações oficiais';
}

function drawSeries(id,info,values,description,negative=false){
const target=$(id);if(!target)return;
const a=values.filter(v=>Number.isFinite(v)).slice(-100);
target.replaceChildren();
if(!a.length){$(info).textContent='Sem série disponível nesta fonte; consultar produto oficial.';return}
const lo=negative?Math.min(0,...a):0,hi=Math.max(...a,lo+0.01),span=hi-lo;
for(const v of a){const bar=document.createElement('i');bar.style.height=Math.max(2,((v-lo)/span)*100)+'%';if(v<0)bar.className='negative';bar.title=String(v);target.appendChild(bar)}
$(info).textContent=description+' · '+a.length+' amostras · valores de fonte NOAA';
}
function setMap(id,url){const el=$(id);if(!el)return;const panel=el.closest('.sw-product');el.onload=()=>panel.classList.remove('failed');el.onerror=()=>panel.classList.add('failed');el.src=url+(url.includes('?')?'&':'?')+'t='+Math.floor(Date.now()/900000)}
async function loadProducts(){
setMap('drapMap','https://services.swpc.noaa.gov/images/animations/d-rap/global/d-rap/latest.png');
setMap('auroraMap','https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg');
const calls=await Promise.allSettled([
json('https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json'),
json('https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json'),
json('https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json'),
json('https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json'),
json('https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-1-day.json'),
json('https://services.swpc.noaa.gov/products/alerts.json')]);
const val=i=>calls[i].status==='fulfilled'?calls[i].value:null;
if(Array.isArray(val(0))){drawSeries('kpChart','kpChartInfo',val(0).slice(1).map(r=>Number(Array.isArray(r)?r[1]:r.Kp)),'Índice Kp')}
if(Array.isArray(val(1))){drawSeries('xrayChart','xrayChartInfo',val(1).filter(r=>r.energy==='0.1-0.8nm').map(r=>Math.log10(Math.max(1e-10,Number(r.flux)))),'Log10 do fluxo de raios X (W/m²)')}
if(Array.isArray(val(2))){const rows=val(2),h=rows[0]||[],idx=h.indexOf('bz_gsm');drawSeries('bzChart','bzChartInfo',rows.slice(1).map(r=>Number(r[idx])),'Bz GSM (nT)',true)}
if(Array.isArray(val(3))){const a=val(3).filter(r=>r.energy==='>=10 MeV');drawSeries('protonChart','protonChartInfo',a.map(r=>Math.log10(Math.max(1e-6,Number(r.flux)))),'Log10 fluxo integral ≥10 MeV (pfu)')}
if(Array.isArray(val(4))){const a=val(4).filter(r=>r.energy==='>=2 MeV');drawSeries('electronChart','electronChartInfo',a.map(r=>Math.log10(Math.max(1e-6,Number(r.flux)))),'Log10 fluxo integral ≥2 MeV')}
const out=$('swAlerts');out.replaceChildren();const messages=Array.isArray(val(5))?val(5).slice(0,8):[];
if(!messages.length){out.textContent='Não foi possível obter a lista de alertas NOAA. Consulta a fonte oficial.'}
else for(const a of messages){const box=document.createElement('div');box.className='sw-alert';const title=document.createElement('b');title.textContent=a.product_id||'Mensagem NOAA SWPC';const date=document.createElement('small');date.textContent=a.issue_datetime?time(a.issue_datetime):'Hora não indicada';const body=document.createElement('pre');body.textContent=String(a.message||'Mensagem indisponível').slice(0,1800);box.append(title,date,body);out.append(box)}
}

$('reload').onclick=()=>{load();loadProducts()};load();loadProducts();


})();
