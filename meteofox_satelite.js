/* MeteoFox — Satélite EUMETSAT + Radar RainViewer sincronizados.
   Usa apenas datas UTC confirmadas. Sem imagens fictícias ou animação com horas inventadas.
   Observações de satélite com WMS; radar com frames históricos RainViewer.
*/
(function(){
'use strict';
const WMS='https://view.eumetsat.int/geoserver/wms';
const LAYER='mtg_fd:rgb_geocolour';
const RADAR_API='https://api.rainviewer.com/public/weather-maps.json';
const RADAR_MAX_DIFF=8*60*1000;
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
async function actualSatelliteTimes(){const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
 try{
  const r=await fetch(WMS+'?service=WMS&version=1.1.1&request=GetCapabilities',{signal:controller.signal,mode:'cors',cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);const xml=new DOMParser().parseFromString(await r.text(),'text/xml');
  const layer=findLayer(xml.documentElement,LAYER);if(!layer)throw Error('Camada Meteosat não encontrada');
  let current=layer,dim=null;
  while(current && !dim){dim=[...current.children].find(x=>['Dimension','Extent'].includes(x.localName)&&x.getAttribute('name')?.toLowerCase()==='time');current=current.parentElement;}
  const times=parseTimes(dim?.textContent);if(!times.length)throw Error('Sem horas UTC publicadas');return times;
 }finally{clearTimeout(timeout);}
}
class MeteoFoxSatellite{
 constructor(map,host){this.map=map;this.host=host;this.satOn=false;this.radarOn=false;this.satTimes=[];this.radarFrames=[];this.timeline=[];this.index=0;this.interval=null;this.satLayer=null;this.radarLayer=null;this.pending=0;this.satKnown=false;this.ready=false;
  this.sat=add('button',host,'☁ Satélite: desligado',{'type':'button','aria-pressed':'false'});
  this.radar=add('button',host,'🌧 Radar: desligado',{'type':'button','aria-pressed':'false'});
  this.play=add('button',host,'▶ Animar',{'type':'button'});this.play.disabled=true;
  const lab=add('label',host,'Opacidade satélite ');this.opacity=add('input',lab,null,{type:'range',min:'10',max:'100',value:'70',step:'5','aria-label':'Opacidade satélite'});
  const rlab=add('label',host,'Radar ');this.radarOpacity=add('input',rlab,null,{type:'range',min:'10',max:'100',value:'75',step:'5','aria-label':'Opacidade radar'});
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
  this.opacity.oninput=()=>this.satLayer?.setOpacity(+this.opacity.value/100);
  this.radarOpacity.oninput=()=>this.radarLayer?.setOpacity(+this.radarOpacity.value/100);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)this.stop();});
 }
 state(s){this.status.textContent=s;}
 async setSatellite(on){this.stop();this.satOn=on;this.sat.textContent='☁ Satélite: '+(on?'ligado':'desligado');this.sat.setAttribute('aria-pressed',String(on));
  if(!on){if(this.satLayer)this.map.removeLayer(this.satLayer);this.refreshTimeline();return;}
  if(!this.satLayer){this.satLayer=L.tileLayer.wms(WMS,{layers:LAYER,styles:'',format:'image/png',transparent:true,version:'1.1.1',opacity:+this.opacity.value/100,maxZoom:16,updateWhenIdle:true,keepBuffer:3,attribution:'© EUMETSAT / NASA'});}
  this.satLayer.addTo(this.map);this.satLayer.bringToFront();this.ensureRadarAbove();
  this.state('Satélite ligado. A verificar os horários UTC da EUMETSAT…');
  try{this.satTimes=await actualSatelliteTimes();this.satKnown=true;this.state('Horários Meteosat confirmados: '+this.satTimes.length+' imagens.');}
  catch(e){this.satKnown=false;this.satTimes=[];this.state('Satélite disponível sem horários confirmados ('+e.message+'). Não será animado com horas inventadas.');}
  this.refreshTimeline();
 }
 async setRadar(on){this.stop();this.radarOn=on;this.radar.textContent='🌧 Radar: '+(on?'ligado':'desligado');this.radar.setAttribute('aria-pressed',String(on));
  if(!on){if(this.radarLayer)this.map.removeLayer(this.radarLayer);this.refreshTimeline();return;}
  this.state('A consultar horas de radar RainViewer…');
  try{const r=await fetch(RADAR_API+'?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);
   const d=await r.json();this.radarHost=String(d.host||'https://tilecache.rainviewer.com').replace(/\/$/,'');
   this.radarFrames=(d.radar?.past||[]).filter(f=>Number.isFinite(f.time)&&typeof f.path==='string').sort((a,b)=>a.time-b.time);
   if(!this.radarFrames.length)throw Error('Sem instantes disponíveis');this.state(this.radarFrames.length+' imagens de radar disponíveis, com hora UTC indicada.');
  }catch(e){this.radarFrames=[];this.state('Radar indisponível: '+e.message);}
  this.refreshTimeline();
 }
 refreshTimeline(){
  // Com radar ativo, o cursor percorre tempos reais de radar; caso contrário usa os de satélite confirmados.
  this.timeline=this.radarOn&&this.radarFrames.length?this.radarFrames.map(x=>x.time*1000):(this.satOn&&this.satKnown?this.satTimes:[]);
  const ok=this.timeline.length>0;this.play.disabled=!ok;this.back.disabled=!ok;this.forward.disabled=!ok;this.slider.disabled=!ok;
  this.slider.max=String(Math.max(0,this.timeline.length-1));this.start.textContent=ok?short(this.timeline[0]):'—';this.end.textContent=ok?short(this.timeline.at(-1)):'—';
  if(ok)this.select(this.timeline.length-1);else this.state(this.satOn&&!this.satKnown?'Imagem Meteosat estática; sem horários confirmados para animação.':'Ativa uma camada com imagens temporais disponíveis.');
 }
 nearestSat(time){if(!this.satKnown||!this.satTimes.length)return null;let best=null,delta=Infinity;for(const t of this.satTimes){const d=Math.abs(t-time);if(d<delta){delta=d;best=t;}}return delta<=RADAR_MAX_DIFF?best:null;}
 ensureRadarAbove(){if(this.radarLayer&&this.radarOn)this.radarLayer.bringToFront();}
 swapRadar(frame){if(!frame)return;const url=this.radarHost+frame.path+'/256/{z}/{x}/{y}/2/1_1.png';
  if(this.radarLayer&&this.radarLayer._url===url){if(!this.map.hasLayer(this.radarLayer))this.radarLayer.addTo(this.map);return;}
  const next=L.tileLayer(url,{opacity:0,zIndex:420,maxNativeZoom:10,maxZoom:18,attribution:'Radar © RainViewer',keepBuffer:3});
  const prev=this.radarLayer;this.radarLayer=next;next.addTo(this.map);next.bringToFront();
  const op=+this.radarOpacity.value/100;let settled=false;
  const finish=()=>{if(settled)return;settled=true;if(this.radarLayer!==next){this.map.removeLayer(next);return;}next.setOpacity(op);if(prev&&this.map.hasLayer(prev))this.map.removeLayer(prev);};
  next.once('load',finish);next.once('tileerror',()=>{if(!settled)this.state('Há mosaicos de radar indisponíveis; a imagem anterior pode permanecer visível.');});
  // Leaflet may not dispatch load if no tiles are in view.
  setTimeout(()=>{if(!settled&&this.radarLayer===next)finish();},4000);
 }
 select(i){if(!this.timeline.length)return;this.index=Math.max(0,Math.min(this.timeline.length-1,i));const time=this.timeline[this.index];this.slider.value=String(this.index);
  let texts=['Referência '+fmt(time)];
  if(this.radarOn){const frame=this.radarFrames.find(f=>f.time*1000===time);if(frame){this.swapRadar(frame);texts.push('Radar '+fmt(frame.time*1000));}}
  if(this.satOn){
   const satTime=this.radarOn?this.nearestSat(time):(this.satKnown?time:null);
   if(satTime!==null&&this.satLayer){this.satLayer.setParams({time:new Date(satTime).toISOString()},false);this.satLayer.redraw();texts.push('Meteosat '+fmt(satTime));if(this.radarOn)texts.push('diferença '+Math.round(Math.abs(time-satTime)/60000)+' min');}
   else if(this.radarOn){if(this.satLayer&&this.map.hasLayer(this.satLayer))this.map.removeLayer(this.satLayer);texts.push('Sem imagem Meteosat confirmada próxima desta hora');}
   else texts.push('Meteosat sem horário confirmado');
   if(satTime!==null&&this.satLayer&&!this.map.hasLayer(this.satLayer))this.satLayer.addTo(this.map);
  }
  this.ensureRadarAbove();this.state(texts.join(' · '));
 }
 stop(){if(this.interval){clearInterval(this.interval);this.interval=null;}this.play.textContent='▶ Animar';}
 togglePlay(){if(this.interval){this.stop();return;}if(!this.timeline.length)return;this.play.textContent='Ⅱ Pausar';this.interval=setInterval(()=>{if(this.index>=this.timeline.length-1)this.select(0);else this.select(this.index+1);},2800);}
}
window.MeteoFoxSatellite=MeteoFoxSatellite;
})();
