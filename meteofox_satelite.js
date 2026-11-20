/* MeteoFox — Satélite EUMETSAT + Radar RainViewer sincronizados.
   Usa apenas datas UTC confirmadas. Sem imagens fictícias ou animação com horas inventadas.
   Observações de satélite com WMS; radar com frames históricos RainViewer.
*/
(function(){
'use strict';
const WMS='https://view.eumetsat.int/geoserver/wms';
const SAT_MANIFEST='https://raw.githubusercontent.com/dfraposo1991-lang/MeteoFox/main/data/satellite_times.json';
const LAYER='mtg_fd:rgb_geocolour';
const RADAR_API='https://api.rainviewer.com/public/weather-maps.json';
const RADAR_MAX_DIFF=8*60*1000;
const SAT_MAX_DIFF=8*60*1000;
const DATE=s=>{const n=Date.parse(s);return Number.isFinite(n)?n:null;};
const fmt=ms=>new Date(ms).toLocaleString('pt-PT',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+' UTC';
const short=ms=>new Date(ms).toLocaleTimeString('pt-PT',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'}).replace(':00','')+'Z';
function add(tag,parent,label,attrs={}){const n=document.createElement(tag);if(label!==null)n.textContent=label;for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);parent.append(n);return n;}
function firstChild(node,name){return [...node.children].find(x=>x.localName===name);}
function findLayer(node,name){if(node.localName==='Layer'&&firstChild(node,'Name')?.textContent?.trim()===name)return node;for(const c of node.children){const x=findLayer(c,name);if(x)return x;}return null;}
function parseTimes(text){const items=[];for(const part of String(text||'').split(',')){
  const p=part.trim();if(!p)continue;
  if(!p.includes('/')){const n=DATE(p);if(n!==null)items.push(n);continue;}
  const [a,b,interval]=p.split('/');const from=DATE(a),to=DATE(b);const m=/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(interval||'');
  if(from===null||to===null||!m)continue;const step=((+m[1]||0)*3600+(+m[2]||0)*60+(+m[3]||0))*1000;
  if(step<=0)continue;let count=0;for(let t=to;t>=from&&count<150;t-=step,count++)items.push(t);
 }
 return [...new Set(items)].filter(n=>n<=Date.now()+600000).sort((a,b)=>a-b).slice(-36);
}
async function actualSatelliteTimesDirect(){const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
 try{
  const r=await fetch(WMS+'?service=WMS&version=1.1.1&request=GetCapabilities',{signal:controller.signal,mode:'cors',cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);const xml=new DOMParser().parseFromString(await r.text(),'text/xml');
  const layer=findLayer(xml.documentElement,LAYER);if(!layer)throw Error('Camada Meteosat não encontrada');
  let current=layer,dim=null;
  while(current && !dim){dim=[...current.children].find(x=>['Dimension','Extent'].includes(x.localName)&&x.getAttribute('name')?.toLowerCase()==='time');current=current.parentElement;}
  const times=parseTimes(dim?.textContent);if(!times.length)throw Error('Sem horas UTC publicadas');return times;
 }finally{clearTimeout(timeout);}
}
async function actualSatelliteTimes(){
 // A lista de horários é recolhida pelo GitHub Actions: evita falhas de CORS do GetCapabilities no navegador.
 try{
  const r=await fetch(SAT_MANIFEST+'?v='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error('Manifesto HTTP '+r.status);
  const d=await r.json();
  if(d.layer!==LAYER||!Array.isArray(d.times_utc))throw Error('Formato do manifesto inválido');
  const checked=DATE(d.checked_utc);
  if(checked===null||Date.now()-checked>90*60000||checked>Date.now()+5*60000)throw Error('Manifesto de horários desatualizado');
  const times=[...new Set(d.times_utc.map(DATE).filter(x=>x!==null&&x<=Date.now()+120000&&x>=Date.now()-6*3600000))].sort((a,b)=>a-b);
  if(times.length<2)throw Error('Sem sequência recente confirmada');
  return times;
 }catch(manifestError){
  // Alternativa direta: funciona apenas quando o serviço permitir CORS.
  try{return await actualSatelliteTimesDirect();}
  catch(directError){throw Error('Manifesto: '+manifestError.message+'; EUMETSAT: '+directError.message);}
 }
}
class MeteoFoxSatellite{
 constructor(map,host){this.map=map;this.host=host;this.satOn=false;this.radarOn=false;this.satTimes=[];this.radarFrames=[];this.timeline=[];this.index=0;this.interval=null;this.satLayer=null;this.radarLayer=null;this.pending=0;this.satKnown=false;this.ready=false;this.radarLayers=new Set();this.radarEpoch=0;this.satRequestSeq=0;this.satRenderedTime=null;this.satPendingTime=null;this.satPendingLayer=null;this.transition=null;this.transitionSeq=0;this.frameTimeout=null;this.playing=false;this.fadeTimer=null;this.fadeOutLayers=[];
  this.sat=add('button',host,'☁ Satélite: desligado',{'type':'button','aria-pressed':'false'});
  this.radar=add('button',host,'🌧 Radar: desligado',{'type':'button','aria-pressed':'false'});
  this.play=add('button',host,'▶ Animar',{'type':'button'});this.play.disabled=true;
  this.back=add('button',host,'◀',{'type':'button','title':'Imagem anterior'});this.back.disabled=true;
  this.start=add('span',host,'—',{'class':'sat-clock'});
  this.slider=add('input',host,null,{type:'range',min:'0',max:'0',step:'1',value:'0','aria-label':'Navegação temporal UTC'});this.slider.disabled=true;this.slider.style.cssText='width:min(270px,40vw);accent-color:#07518b';
  this.end=add('span',host,'—',{'class':'sat-clock'});
  this.forward=add('button',host,'▶',{'type':'button','title':'Imagem seguinte'});this.forward.disabled=true;
  this.status=add('span',host,'Ativa o radar e/ou o satélite. As horas apresentadas são UTC verificadas.',{'class':'sat-status','aria-live':'polite'});
  this.attr=add('span',host,'Fonte: Meteosat MTG GeoColour RGB © EUMETSAT/NASA · Radar © RainViewer · dados de observação. ',{'class':'sat-attribution'});
  const a=add('a',this.attr,'EUMETView',{href:'https://view.eumetsat.int/',target:'_blank',rel:'noopener noreferrer'});a.style.color='#07518b';
  this.sat.onclick=()=>this.setSatellite(!this.satOn);this.radar.onclick=()=>this.setRadar(!this.radarOn);
  this.play.onclick=()=>this.togglePlay();this.back.onclick=()=>this.select(this.index-1);this.forward.onclick=()=>this.select(this.index+1);
  this.slider.oninput=()=>{this.stop();this.select(+this.slider.value)};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)this.stop();});
 }
 state(s){this.status.textContent=s;}
 async setSatellite(on){this.stop();this.cancelTransition();const satRequest=Symbol('sat');this.satRequest=satRequest;this.satOn=on;this.sat.textContent='☁ Satélite: '+(on?'ligado':'desligado');this.sat.setAttribute('aria-pressed',String(on));
  if(!on){this.satRequestSeq++;this.satRenderedTime=null;this.satPendingTime=null;if(this.satPendingLayer&&this.map.hasLayer(this.satPendingLayer))this.map.removeLayer(this.satPendingLayer);this.satPendingLayer=null;if(this.satLayer&&this.map.hasLayer(this.satLayer))this.map.removeLayer(this.satLayer);this.satLayer=null;this.satKnown=false;this.satTimes=[];this.refreshTimeline();return;}
  // A camada é criada com TIME explícito após obter horários publicados.
  // Opacidade fixa a 80%; sem controlos adicionais.
  this.ensureRadarAbove();
  this.state('Satélite ligado. A verificar os horários UTC da EUMETSAT…');
  try{const confirmed=await actualSatelliteTimes();if(this.satRequest!==satRequest)return;this.satTimes=confirmed;this.satKnown=true;this.state('Horários Meteosat confirmados: '+this.satTimes.length+' imagens.');}
  catch(e){if(this.satRequest!==satRequest)return;this.satKnown=false;this.satTimes=[];this.state('Satélite disponível sem horários confirmados ('+e.message+'). Não será animado com horas inventadas.');}
  if(this.satRequest===satRequest)this.refreshTimeline();
 }
 async setRadar(on){this.stop();this.cancelTransition();this.clearRadar();this.radarOn=on;this.radar.textContent='🌧 Radar: '+(on?'ligado':'desligado');this.radar.setAttribute('aria-pressed',String(on));
  if(!on){this.radarRequest=null;this.radarFrames=[];this.clearRadar();this.refreshTimeline();return;}
  this.state('A consultar horas de radar RainViewer…');
  const radarRequest=Symbol('radar');this.radarRequest=radarRequest;
  try{const r=await fetch(RADAR_API+'?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);
   const d=await r.json();if(this.radarRequest!==radarRequest||!this.radarOn)return;this.radarHost=String(d.host||'https://tilecache.rainviewer.com').replace(/\/$/,'');
   this.radarFrames=(d.radar?.past||[]).filter(f=>Number.isFinite(f.time)&&typeof f.path==='string').sort((a,b)=>a.time-b.time);
   if(!this.radarFrames.length)throw Error('Sem instantes disponíveis');this.state(this.radarFrames.length+' imagens de radar disponíveis, com hora UTC indicada.');
  }catch(e){if(this.radarRequest!==radarRequest||!this.radarOn)return;this.radarFrames=[];this.state('Radar indisponível: '+e.message);}
  if(!this.radarOn)return;this.refreshTimeline();
 }
 refreshTimeline(){
  this.cancelTransition();
  const sat=this.satOn&&this.satKnown?this.satTimes:[];
  const rad=this.radarOn?this.radarFrames.map(x=>x.time*1000):[];
  if(this.satOn&&this.radarOn){
   // As duas camadas só animam quando há pares temporalmente compatíveis (máx. 8 min).
   this.timeline=sat.length&&rad.length?rad.filter(t=>this.nearestSat(t)!==null):[];
  }else if(this.radarOn)this.timeline=rad;
  else if(this.satOn)this.timeline=sat;
  else this.timeline=[];
  const ok=this.timeline.length>0;
  this.play.disabled=!ok;this.back.disabled=!ok;this.forward.disabled=!ok;this.slider.disabled=!ok;
  this.slider.max=String(Math.max(0,this.timeline.length-1));
  this.start.textContent=ok?short(this.timeline[0]):'—';
  this.end.textContent=ok?short(this.timeline.at(-1)):'—';
  if(ok)this.select(this.timeline.length-1);
  else{
   if(this.radarOn)this.clearRadar();
   if(this.satOn&&this.satLayer&&this.map.hasLayer(this.satLayer)){this.map.removeLayer(this.satLayer);this.satLayer=null;this.satRenderedTime=null;}
   this.state(this.satOn&&this.radarOn?'Sem imagens radar/Meteosat com horários UTC compatíveis. Desliga uma camada para a consultar isoladamente.':this.satOn?'Meteosat sem horários recentes confirmados. A imagem fica oculta para não apresentar uma hora errada.':'Ativa uma camada com imagens temporais disponíveis.');
  }
 }
 nearestSat(time){if(!this.satKnown||!this.satTimes.length)return null;let best=null,delta=Infinity;
  for(const t of this.satTimes){const d=Math.abs(t-time);if(d<delta){delta=d;best=t;}}
  return delta<=SAT_MAX_DIFF?best:null;
 }
 nearestRadar(time){if(!this.radarFrames.length)return null;let best=null,delta=Infinity;
  for(const f of this.radarFrames){const d=Math.abs(f.time*1000-time);if(d<delta){delta=d;best=f;}}
  return delta<=RADAR_MAX_DIFF?best:null;
 }
 // A transição só revela novas imagens quando TODOS os mosaicos das camadas ativas
 // estiverem prontos. As imagens anteriores mantêm-se visíveis até esse instante.
 clearFades(){
  if(this.fadeTimer){clearTimeout(this.fadeTimer);this.fadeTimer=null;}
  for(const layer of this.fadeOutLayers){
   if(this.map.hasLayer(layer))this.map.removeLayer(layer);
  }
  this.fadeOutLayers=[];
 }
 cancelTransition(){
  this.clearFades();
  this.transitionSeq++;
  const job=this.transition;this.transition=null;
  if(!job)return;
  clearTimeout(job.timeout);
  for(const layer of job.layers){
   layer.off('load');layer.off('tileerror');
   if(this.map.hasLayer(layer))this.map.removeLayer(layer);
  }
 }
 clearRadar(){
  this.radarEpoch++;
  for(const layer of this.radarLayers){if(this.map.hasLayer(layer))this.map.removeLayer(layer);}
  if(this.radarLayer&&this.map.hasLayer(this.radarLayer))this.map.removeLayer(this.radarLayer);
  this.radarLayers.clear();this.radarLayer=null;
 }
 ensureRadarAbove(){
  // Os símbolos METAR permanecem sobre as imagens meteorológicas.
  if(this.radarLayer&&this.map.hasLayer(this.radarLayer))this.radarLayer.setZIndex(350);
 }
 stageFrame(time){
  this.cancelTransition();
  const seq=this.transitionSeq;
  const satTime=this.satOn?this.nearestSat(time):null;
  const radFrame=this.radarOn?this.nearestRadar(time):null;
  const both=this.satOn&&this.radarOn;
  const info=['Referência '+fmt(time)];
  if(this.satOn){
   if(satTime===null){this.state('Sem imagem Meteosat confirmada para '+fmt(time));return Promise.resolve(false);}
   info.push('Meteosat '+fmt(satTime));
  }
  if(this.radarOn){
   if(!radFrame){this.state('Sem imagem de radar confirmada para '+fmt(time));return Promise.resolve(false);}
   info.push('Radar '+fmt(radFrame.time*1000));
  }
  if(both)info.push('diferença '+Math.round(Math.abs(satTime-radFrame.time*1000)/60000)+' min');
  if(!this.satOn&&!this.radarOn)return Promise.resolve(false);
  this.state('A preparar imagens · '+info.join(' · '));
  const jobs=[];
  if(this.satOn){
   if(this.satLayer&&this.satRenderedTime===satTime&&this.map.hasLayer(this.satLayer))jobs.push({kind:'sat',layer:this.satLayer,reuse:true});
   else jobs.push({kind:'sat',layer:L.tileLayer.wms(WMS,{
    layers:LAYER,styles:'',format:'image/png',transparent:true,version:'1.1.1',
    time:new Date(satTime).toISOString(),opacity:0,zIndex:300,maxZoom:16,
    keepBuffer:0,updateWhenIdle:true,attribution:'© EUMETSAT / NASA'
   })});
  }
  if(this.radarOn){
   const url=this.radarHost+radFrame.path+'/256/{z}/{x}/{y}/2/1_1.png';
   if(this.radarLayer?.meteofoxUrl===url&&this.map.hasLayer(this.radarLayer))jobs.push({kind:'radar',layer:this.radarLayer,reuse:true});
   else {const layer=L.tileLayer(url,{
    opacity:0,zIndex:350,maxNativeZoom:10,maxZoom:18,
    attribution:'Radar © RainViewer',keepBuffer:0,updateWhenIdle:true
   });layer.meteofoxUrl=url;jobs.push({kind:'radar',layer});}
  }
  const pending=jobs.filter(x=>!x.reuse);
  return new Promise(resolve=>{
   let settled=false;
   const job={layers:pending.map(x=>x.layer),timeout:null};
   this.transition=job;
   const finish=(success)=>{
    if(settled)return;
    settled=true;
    clearTimeout(job.timeout);
    if(seq!==this.transitionSeq||this.transition!==job){resolve(false);return;}
    this.transition=null;
    if(!success){
     for(const x of pending){x.layer.off('load');x.layer.off('tileerror');if(this.map.hasLayer(x.layer))this.map.removeLayer(x.layer);}
     this.state('Não foi possível carregar todas as imagens de '+fmt(time)+'. Mantidas as anteriores.');
     resolve(false);return;
    }
    // Crossfade apenas depois de TODOS os mosaicos estarem prontos.
    // Conserva a imagem anterior durante 260 ms: evita a troca fragmentada
    // sem inventar fotogramas nem alterar a hora UTC das duas camadas.
    requestAnimationFrame(()=>{
     if(seq!==this.transitionSeq){for(const x of pending)if(this.map.hasLayer(x.layer))this.map.removeLayer(x.layer);resolve(false);return;}
     const oldSat=this.satLayer,oldRadar=this.radarLayer;
     const fading=[];
     for(const x of jobs){
      if(x.kind==='sat'){
       x.layer.setZIndex(300);this.satLayer=x.layer;this.satRenderedTime=satTime;
       if(!x.reuse){const c=x.layer.getContainer();if(c)c.style.transition='opacity 260ms ease-in-out';}
      }
      if(x.kind==='radar'){
       x.layer.setZIndex(350);this.radarLayer=x.layer;this.radarLayers.add(x.layer);
       if(!x.reuse){const c=x.layer.getContainer();if(c)c.style.transition='opacity 260ms ease-in-out';}
      }
     }
     for(const old of [oldSat,oldRadar]){
      if(old&&old!==this.satLayer&&old!==this.radarLayer&&this.map.hasLayer(old)){
       const c=old.getContainer();if(c)c.style.transition='opacity 260ms ease-in-out';
       fading.push(old);
      }
     }
     this.fadeOutLayers=fading;
     // Frame extra para o navegador pintar a opacidade inicial (0) dos novos
     // mosaicos antes de executar a animação.
     requestAnimationFrame(()=>{
      if(seq!==this.transitionSeq)return;
      for(const x of jobs){
       if(x.kind==='sat')x.layer.setOpacity(.8);
       if(x.kind==='radar')x.layer.setOpacity(.66);
      }
      for(const layer of fading)layer.setOpacity(0);
      this.fadeTimer=setTimeout(()=>this.clearFades(),300);
     });
     this.state(info.join(' · '));
     resolve(true);
    });
   };
   if(!pending.length){finish(true);return;}
   let remaining=pending.length;
   for(const x of pending){
    let errors=0;
    x.layer.on('tileerror',()=>{errors++;});
    x.layer.once('load',()=>{
     if(errors){finish(false);return;}
     remaining--;if(remaining===0)finish(true);
    });
   }
   job.timeout=setTimeout(()=>finish(false),18000);
   for(const x of pending)x.layer.addTo(this.map);
  });
 }
 select(i){
  if(!this.timeline.length)return Promise.resolve(false);
  this.index=Math.max(0,Math.min(this.timeline.length-1,i));
  this.slider.value=String(this.index);
  return this.stageFrame(this.timeline[this.index]);
 }
 stop(){
  this.playing=false;
  if(this.frameTimeout){clearTimeout(this.frameTimeout);this.frameTimeout=null;}
  this.play.textContent='▶ Animar';
 }
 togglePlay(){
  if(this.playing){this.stop();return;}
  if(!this.timeline.length)return;
  this.playing=true;this.play.textContent='Ⅱ Pausar';
  const tick=async()=>{
   if(!this.playing)return;
   const i=this.index>=this.timeline.length-1?0:this.index+1;
   await this.select(i);
   if(this.playing)this.frameTimeout=setTimeout(tick,1100);
  };
  tick();
 }

}
window.MeteoFoxSatellite=MeteoFoxSatellite;
})();
