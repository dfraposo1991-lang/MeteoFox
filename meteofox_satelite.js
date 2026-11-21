/* MeteoFox — Satélite EUMETSAT + Radar RainViewer sincronizados.
   Usa apenas datas UTC confirmadas. Sem imagens fictícias ou animação com horas inventadas.
   Observações de satélite com WMS; radar com frames históricos RainViewer.
*/
(function(){
'use strict';
const WMS='https://view.eumetsat.int/geoserver/wms';
const SAT_MANIFEST='https://raw.githubusercontent.com/dfraposo1991-lang/MeteoFox/main/data/satellite_times.json';
const LAYER='mtg_fd:rgb_geocolour';
const FOG_LAYER='mtg_fd:rgb_fog';
const BLANK_TILE='data:image/svg+xml,%3Csvg xmlns=%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22 width=%221%22 height=%221%22%2F%3E';
const FOG_STATUS='https://raw.githubusercontent.com/dfraposo1991-lang/MeteoFox/main/data/satellite_fog_status.json';
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
 constructor(map,host){this.map=map;this.host=host;this.satOn=false;this.radarOn=false;this.satTimes=[];this.radarFrames=[];this.timeline=[];this.index=0;this.interval=null;this.satLayer=null;this.radarLayer=null;this.pending=0;this.satKnown=false;this.ready=false;this.radarLayers=new Set();this.radarEpoch=0;this.satRequestSeq=0;this.satRenderedTime=null;this.satPendingTime=null;this.satPendingLayer=null;this.transition=null;this.transitionSeq=0;this.frameTimeout=null;this.playing=false;this.fadeTimer=null;this.fadeOutLayers=[];this.prefetchSat=null;this.prefetchTimer=null;this.speedIndex=1;this.speeds=[.5,1,1.5,2,3];this.satOpacity=.8;this.radarOpacity=.66;this.satMode='auto';this.satRenderedMode=null;this.fogLayer=null;this.fogRenderedTime=null;this.fogStatus=null;
  // Fronteiras discretas sobre a nebulosidade: só com satélite ativo.
  this.bordersLayer=null;this.bordersRequest=null;
  this.bordersPane=map.getPane('meteofoxCountryBorders')||map.createPane('meteofoxCountryBorders');
  this.bordersPane.style.zIndex='650';
  this.bordersPane.style.pointerEvents='none';
  this.sat=add('button',host,'🌗 VIS / FOG Auto: desligado',{'type':'button','aria-pressed':'false','title':'Satélite automático: GeoColour de dia e Fog RGB à noite; GeoColour de segurança'});
  this.radar=add('button',host,'🌧 Radar: desligado',{'type':'button','aria-pressed':'false'});
  this.play=add('button',host,'▶ Animar',{'type':'button'});this.play.disabled=true;
  this.speedButton=add('button',host,'Velocidade: 1×',{'type':'button','title':'Alterar velocidade da animação','aria-label':'Velocidade da animação: 1 vez'});
  this.opacityButton=add('button',host,'◐ Opacidade',{'type':'button','aria-expanded':'true','title':'Mostrar ou ocultar opções de opacidade'});
  const opacityControls=add('div',host,null,{'class':'mf-opacity-controls','role':'group','aria-label':'Opacidade das camadas'});
  this.opacityButton.onclick=()=>{
   const hide=!opacityControls.hidden;
   opacityControls.hidden=hide;
   this.opacityButton.setAttribute('aria-expanded',String(!hide));
   this.opacityButton.textContent=hide?'◐ Opacidade':'◐ Opacidade ▴';
   if(!hide)opacityControls.scrollIntoView({block:'nearest',behavior:'auto'});
  };
  const makeOpacity=(name,initial,key)=>{
   const label=add('label',opacityControls,null,{'class':'mf-opacity-item'});
   const text=add('span',label,name+' '+initial+'%',{'class':'mf-opacity-label'});
   const slider=add('input',label,null,{type:'range',min:'0',max:'100',step:'5',value:String(initial),'aria-label':'Opacidade '+name.toLowerCase()});
   slider.oninput=()=>{
    const value=Number(slider.value);
    text.textContent=name+' '+value+'%';
    if(key==='sat'){
     this.satOpacity=value/100;
     for(const layer of [this.satLayer,this.fogLayer,this.prefetchSat?.layer,...(this.transition?.layers||[]).filter(x=>x.wmsParams)])
      if(layer)layer.setOpacity(this.satOpacity);
     this.refreshAutoMasks();
    }else{
     this.radarOpacity=value/100;
     for(const layer of [this.radarLayer,...this.radarLayers,...(this.transition?.layers||[]).filter(x=>!x.wmsParams)])
      if(layer)layer.setOpacity(this.radarOpacity);
    }
   };
   return slider;
  };
  this.satOpacitySlider=makeOpacity('Satélite',80,'sat');
  this.radarOpacitySlider=makeOpacity('Radar',66,'radar');
  this.back=add('button',host,'◀',{'type':'button','title':'Imagem anterior'});this.back.disabled=true;
  this.start=add('span',host,'—',{'class':'sat-clock'});
  this.slider=add('input',host,null,{type:'range',min:'0',max:'0',step:'1',value:'0','aria-label':'Navegação temporal UTC'});this.slider.disabled=true;this.slider.style.cssText='width:min(270px,40vw);accent-color:#07518b';
  this.end=add('span',host,'—',{'class':'sat-clock'});
  this.forward=add('button',host,'▶',{'type':'button','title':'Imagem seguinte'});this.forward.disabled=true;
  this.status=add('span',host,'Ativa o radar e/ou o satélite. As horas apresentadas são UTC verificadas.',{'class':'sat-status','aria-live':'polite'});
  this.attr=add('span',host,'Fonte: Meteosat MTG GeoColour / Fog RGB © EUMETSAT/NASA · Radar © RainViewer · dados de observação. ',{'class':'sat-attribution'});
  const a=add('a',this.attr,'EUMETView',{href:'https://view.eumetsat.int/',target:'_blank',rel:'noopener noreferrer'});a.style.color='#07518b';
  this.sat.onclick=()=>this.setSatellite(!this.satOn);this.radar.onclick=()=>this.setRadar(!this.radarOn);
  this.play.onclick=()=>this.togglePlay();this.speedButton.onclick=()=>this.cycleSpeed();this.back.onclick=()=>this.select(this.index-1);this.forward.onclick=()=>this.select(this.index+1);
  this.slider.oninput=()=>{this.stop();this.select(+this.slider.value)};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){this.stop();this.dropPrefetch();}});
  map.on('zoomstart movestart',()=>this.dropPrefetch());
 }
 state(s){this.status.textContent=s;}
 async readFogStatus(){
  const r=await fetch(FOG_STATUS+'?v='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error('Diagnóstico Fog HTTP '+r.status);
  const d=await r.json();
  const timestamp=DATE(d.checked_utc);
  if(!d.ready||d.geo_layer!==LAYER||d.fog_layer!==FOG_LAYER||
     timestamp===null||Math.abs(Date.now()-timestamp)>2*3600000)
   throw Error('Fog MTG sem validação recente de imagens e horário UTC');
  this.fogStatus=d;return d;
 }
 fallbackToGeoColour(reason){
  if(this.satMode==='geo')return;
  this.stop();this.dropPrefetch();
  this.satMode='geo';this.satRenderedMode=null;
  this.sat.title='VIS / FOG Auto temporariamente em GeoColour de segurança';
  this.state('Fog RGB indisponível ('+reason+'). Reposição segura do GeoColour.');
  if(this.satOn&&this.timeline.length)this.select(this.index);
 }
 async syncSatelliteBorders(){
  if(!this.satOn){
   if(this.bordersLayer&&this.map.hasLayer(this.bordersLayer))this.map.removeLayer(this.bordersLayer);
   return;
  }
  if(this.bordersLayer){if(!this.map.hasLayer(this.bordersLayer))this.bordersLayer.addTo(this.map);return;}
  if(this.bordersRequest)return;
  // Natural Earth 1:110m: limites nacionais e linhas de costa, não fronteiras inventadas.
  const url='https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson';
  this.bordersRequest=fetch(url,{cache:'force-cache'}).then(r=>{
   if(!r.ok)throw Error('Natural Earth HTTP '+r.status);
   return r.json();
  }).then(data=>{
   if(!data||data.type!=='FeatureCollection'||!Array.isArray(data.features))throw Error('GeoJSON inválido');
   // O mapa usa preferCanvas:true; sem um renderer SVG explícito,
   // o GeoJSON pode acabar num canvas do overlayPane, atrás do satélite.
   const borderRenderer=L.svg({pane:'meteofoxCountryBorders',padding:.5});
   this.bordersLayer=L.geoJSON(data,{
    pane:'meteofoxCountryBorders',renderer:borderRenderer,interactive:false,
    style:{color:'#ffffff',weight:1.45,opacity:.9,fill:false,lineCap:'round',lineJoin:'round'}
   });
   if(this.satOn)this.bordersLayer.addTo(this.map);
  }).catch(e=>{console.warn('MeteoFox: contornos de países indisponíveis:',e.message)})
  .finally(()=>{this.bordersRequest=null});
 }
 async setSatellite(on){this.stop();this.dropPrefetch();this.cancelTransition();const satRequest=Symbol('sat');this.satRequest=satRequest;this.satOn=on;this.sat.textContent='🌗 VIS / FOG Auto: '+(on?'ligado':'desligado');this.sat.setAttribute('aria-pressed',String(on));this.syncSatelliteBorders();
  if(!on){this.satRequestSeq++;this.satRenderedTime=null;this.satRenderedMode=null;this.fogRenderedTime=null;if(this.fogLayer&&this.map.hasLayer(this.fogLayer))this.map.removeLayer(this.fogLayer);this.fogLayer=null;this.satPendingTime=null;if(this.satPendingLayer&&this.map.hasLayer(this.satPendingLayer))this.map.removeLayer(this.satPendingLayer);this.satPendingLayer=null;if(this.satLayer&&this.map.hasLayer(this.satLayer))this.map.removeLayer(this.satLayer);this.satLayer=null;this.satKnown=false;this.satTimes=[];this.refreshTimeline();return;}
  // A camada é criada com TIME explícito após obter horários publicados.
  // Opacidade configurável nos controlos, com valores iniciais 80% e 66%.
  this.ensureRadarAbove();
  // A escolha automática é a única exposta. Ao voltar a ligar, repetir
  // a validação Fog e recuperar o modo híbrido se o serviço voltou.
  this.satMode='auto';this.satRenderedMode=null;
  this.sat.title='VIS / FOG Auto: GeoColour de dia, Fog RGB à noite';
  if(!window.MeteoFoxFogMask){
   this.satMode='geo';
   this.sat.title='GeoColour de segurança: máscara solar indisponível';
  }else{
   try{await this.readFogStatus();}
   catch(error){
    if(this.satRequest!==satRequest)return;
    this.satMode='geo';
    this.sat.title='GeoColour de segurança: Fog RGB indisponível';
   }
  }
  if(this.satRequest!==satRequest)return;
  this.state(this.satMode==='auto'
   ?'VIS / FOG Auto: a verificar horários UTC EUMETSAT…'
   :'Fog RGB temporariamente indisponível; a utilizar GeoColour de segurança. A verificar horários UTC…');
  try{const confirmed=await actualSatelliteTimes();if(this.satRequest!==satRequest)return;this.satTimes=confirmed;this.satKnown=true;this.state('Horários Meteosat confirmados: '+this.satTimes.length+' imagens.');}
  catch(e){if(this.satRequest!==satRequest)return;this.satKnown=false;this.satTimes=[];this.state('Satélite disponível sem horários confirmados ('+e.message+'). Não será animado com horas inventadas.');}
  if(this.satRequest===satRequest)this.refreshTimeline();
 }
 async setRadar(on){this.stop();this.dropPrefetch();this.cancelTransition();this.clearRadar();this.radarOn=on;this.radar.textContent='🌧 Radar: '+(on?'ligado':'desligado');this.radar.setAttribute('aria-pressed',String(on));
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
  this.dropPrefetch();
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
   if(this.fogLayer&&this.map.hasLayer(this.fogLayer)){this.map.removeLayer(this.fogLayer);this.fogLayer=null;this.fogRenderedTime=null;}
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
 // Pré-carregamento limitado: um único fotograma Meteosat seguinte, nunca
 // a sequência inteira. A camada fica invisível enquanto recebe os mosaicos.
 createSatLayer(time){
  const mode=this.satMode;
  const layer=L.tileLayer.wms(WMS,{
   layers:mode==='fog'?FOG_LAYER:LAYER,styles:'',format:'image/png',transparent:true,version:'1.1.1',
   time:new Date(time).toISOString(),opacity:this.satOpacity,zIndex:300,maxZoom:16,
   keepBuffer:0,updateWhenIdle:true,attribution:'© EUMETSAT / NASA'
  });
  if(mode==='auto'){
   const original=layer.getTileUrl.bind(layer);
   layer.getTileUrl=coords=>window.MeteoFoxFogMask?.tileLighting(time,coords)==='night'?BLANK_TILE:original(coords);
   layer.on('tileload',e=>this.applyAutoGeoMask(e.tile,e.coords,time));
  }
  layer.meteofoxAutoGeo=mode==='auto';
  layer.meteofoxTime=time;
  return layer;
 }
 applyAutoGeoMask(tile,coords,time){
  const mask=window.MeteoFoxFogMask?.tileMask(time,coords,64,'geo',this.satOpacity);
  if(!mask||!tile)return;
  tile.style.webkitMaskImage='url("'+mask+'")';
  tile.style.maskImage='url("'+mask+'")';
  tile.style.webkitMaskSize='100% 100%';tile.style.maskSize='100% 100%';
 }
 refreshAutoMasks(){
  // GeoColour necessita de nova máscara quando muda a opacidade.
  // _tiles é a coleção de mosaicos carregados do Leaflet 1.9.
  const candidates=[this.satLayer,this.prefetchSat?.layer,...(this.transition?.layers||[])];
  for(const layer of new Set(candidates)){
   if(!layer?.meteofoxAutoGeo||!layer._tiles)continue;
   for(const entry of Object.values(layer._tiles))
    if(entry?.loaded&&entry.el&&entry.coords)
     this.applyAutoGeoMask(entry.el,entry.coords,layer.meteofoxTime);
  }
 }
 createFogOverlay(time){
  const layer=L.tileLayer.wms(WMS,{
   layers:FOG_LAYER,styles:'',format:'image/png',transparent:true,version:'1.1.1',
   time:new Date(time).toISOString(),opacity:this.satOpacity,zIndex:325,maxZoom:16,
   keepBuffer:0,updateWhenIdle:true,attribution:'Fog RGB © EUMETSAT'
  });
  const original=layer.getTileUrl.bind(layer);
  layer.getTileUrl=coords=>window.MeteoFoxFogMask?.tileLighting(time,coords)==='day'?BLANK_TILE:original(coords);
  layer.on('tileload',e=>{
   const url=window.MeteoFoxFogMask?.tileMask(time,e.coords);
   if(url&&e.tile){
    e.tile.style.webkitMaskImage='url("'+url+'")';
    e.tile.style.maskImage='url("'+url+'")';
    e.tile.style.webkitMaskSize='100% 100%';e.tile.style.maskSize='100% 100%';
   }
  });
  return layer;
 }
 dropPrefetch(keep=null){
  if(this.prefetchTimer){clearTimeout(this.prefetchTimer);this.prefetchTimer=null;}
  const item=this.prefetchSat;this.prefetchSat=null;
  if(item&&item.layer!==keep&&this.map.hasLayer(item.layer))this.map.removeLayer(item.layer);
 }
 schedulePrefetch(){
  if(!this.satOn||document.hidden||this.timeline.length<2)return;
  const next=this.timeline[(this.index+1)%this.timeline.length];
  const satTime=this.nearestSat(next);
  if(satTime===null||satTime===this.satRenderedTime)return;
  if(this.prefetchSat?.time===satTime&&this.prefetchSat?.mode===this.satMode)return;
  this.dropPrefetch();
  this.prefetchTimer=setTimeout(()=>{
   this.prefetchTimer=null;
   if(!this.satOn||document.hidden||this.nearestSat(this.timeline[(this.index+1)%this.timeline.length])!==satTime)return;
   const layer=this.createSatLayer(satTime);
   const item={time:satTime,mode:this.satMode,layer,ready:false,error:false};
   this.prefetchSat=item;
   layer.on('tileerror',()=>{item.error=true;});
   layer.on('load',()=>{item.ready=!item.error;});
   layer.once('add',()=>{
    const c=layer.getContainer();if(c){c.style.transition='none';c.style.opacity='0';}
   });
   layer.addTo(this.map);
  },180);
 }
 cycleSpeed(){
  this.speedIndex=(this.speedIndex+1)%this.speeds.length;
  const value=this.speeds[this.speedIndex];
  this.speedButton.textContent='Velocidade: '+value+'×';
  this.speedButton.setAttribute('aria-label','Velocidade da animação: '+value+' vezes');
  // Aplica-se no tick seguinte. Nunca acelera artificialmente imagens ainda incompletas.
 }
 // A transição só revela novas imagens quando TODOS os mosaicos das camadas ativas
 // estiverem prontos. As imagens anteriores mantêm-se visíveis até esse instante.
 clearFades(){
  if(this.fadeTimer){clearTimeout(this.fadeTimer);this.fadeTimer=null;}
  // Se o utilizador mudar de imagem durante o fade, terminar a anterior
  // primeiro. Caso contrário a remoção da imagem antiga expõe o mapa vazio.
  for(const layer of [this.satLayer,this.fogLayer,this.radarLayer]){
   const container=layer?.getContainer?.();
   if(container){container.style.transition='none';container.style.opacity='1';}
  }
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
   if(this.satLayer&&this.satRenderedTime===satTime&&this.satRenderedMode===this.satMode&&this.map.hasLayer(this.satLayer))jobs.push({kind:'sat',layer:this.satLayer,reuse:true});
   else {
    const cached=this.prefetchSat?.time===satTime&&this.prefetchSat?.mode===this.satMode?this.prefetchSat:null;
    if(cached)this.dropPrefetch(cached.layer);
    else this.dropPrefetch();
    if(cached&&!cached.error)jobs.push({kind:'sat',layer:cached.layer,preloaded:cached});
    else{
     if(cached&&this.map.hasLayer(cached.layer))this.map.removeLayer(cached.layer);
     jobs.push({kind:'sat',layer:this.createSatLayer(satTime)});
    }
   }
  }
  if(this.satOn&&this.satMode==='auto'){
   if(this.fogLayer&&this.fogRenderedTime===satTime&&this.map.hasLayer(this.fogLayer))
    jobs.push({kind:'fog',layer:this.fogLayer,reuse:true});
   else jobs.push({kind:'fog',layer:this.createFogOverlay(satTime)});
  }
  if(this.radarOn){
   const url=this.radarHost+radFrame.path+'/256/{z}/{x}/{y}/2/1_1.png';
   if(this.radarLayer?.meteofoxUrl===url&&this.map.hasLayer(this.radarLayer))jobs.push({kind:'radar',layer:this.radarLayer,reuse:true});
   else {const layer=L.tileLayer(url,{
    opacity:this.radarOpacity,zIndex:350,maxNativeZoom:10,maxZoom:18,
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
     // Se o produto experimental não devolver mosaicos, não imobilizar o mapa.
     if(this.satMode!=='geo')this.fallbackToGeoColour('mosaicos ou sincronização');
     resolve(false);return;
    }
    // O problema do piscar vinha da soma de dois fades por mosaico.
    // Mantemos a imagem anterior INTACTA; a seguinte surge sobre ela.
    // O fade é aplicado só ao container Leaflet, nunca a cada tile.
    requestAnimationFrame(()=>{
     if(seq!==this.transitionSeq){
      for(const x of pending)if(this.map.hasLayer(x.layer))this.map.removeLayer(x.layer);
      resolve(false);return;
     }
     const oldSat=this.satLayer,oldFog=this.fogLayer,oldRadar=this.radarLayer;
     const previous=[];
     for(const x of jobs){
      if(x.kind==='sat'){
       x.layer.setZIndex(300);this.satLayer=x.layer;this.satRenderedTime=satTime;this.satRenderedMode=this.satMode;
      }
      if(x.kind==='fog'){
       x.layer.setZIndex(325);this.fogLayer=x.layer;this.fogRenderedTime=satTime;
      }
      if(x.kind==='radar'){
       x.layer.setZIndex(350);this.radarLayer=x.layer;this.radarLayers.add(x.layer);
      }
     }
     if(!jobs.some(x=>x.kind==='fog')){this.fogLayer=null;this.fogRenderedTime=null;}
     for(const old of [oldSat,oldFog,oldRadar]){
      if(old&&old!==this.satLayer&&old!==this.fogLayer&&old!==this.radarLayer&&this.map.hasLayer(old))
       previous.push(old);
     }
     this.fadeOutLayers=previous;
     // As novas camadas estão por cima das anteriores (mesmo z-index e
     // inseridas mais tarde), com opacidade intrínseca final desde o início.
     // Nunca diminuir a opacidade da imagem que o utilizador já vê.
     requestAnimationFrame(()=>{
      if(seq!==this.transitionSeq)return;
      for(const x of pending){
       const container=x.layer.getContainer();
       if(container){
        container.style.transition='opacity 280ms ease-out';
        container.style.opacity='1';
       }
      }
      // Limpar só depois de terminar o fade. O temporizador é cancelável
      // quando o utilizador salta rapidamente para outro instante.
      this.fadeTimer=setTimeout(()=>this.clearFades(),340);
     });
     this.state(info.join(' · '));
     // Uma preparação em segundo plano só após estabilizar o fotograma atual.
     this.schedulePrefetch();
     resolve(true);
    });
   };
   if(!pending.length){finish(true);return;}
   let remaining=pending.filter(x=>!x.preloaded?.ready).length;
   for(const x of pending){
    if(x.preloaded?.ready)continue;
    let errors=0;
    x.layer.on('tileerror',()=>{errors++;});
    x.layer.once('load',()=>{
     if(errors){finish(false);return;}
     remaining--;if(remaining===0)finish(true);
    });
   }
   if(remaining===0){finish(true);return;}
   job.timeout=setTimeout(()=>finish(false),18000);
   for(const x of pending){
    if(x.preloaded)continue;
    // Preparar o container invisível ANTES do primeiro mosaico aparecer.
    // O Leaflet gere o carregamento de cada tile com a opacidade habitual,
    // mas essa fragmentação fica totalmente oculta até o conjunto estar pronto.
    x.layer.once('add',()=>{
     const container=x.layer.getContainer();
     if(container){container.style.transition='none';container.style.opacity='0';}
    });
    x.layer.addTo(this.map);
   }
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
   if(this.playing)this.frameTimeout=setTimeout(tick,Math.round(1100/this.speeds[this.speedIndex]));
  };
  tick();
 }

}
window.MeteoFoxSatellite=MeteoFoxSatellite;
})();
