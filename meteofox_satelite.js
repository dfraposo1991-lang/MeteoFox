/* MeteoFox — Camada georreferenciada Meteosat sobre mapas Leaflet.
 * Fonte: EUMETSAT EUMETView WMS; nenhuma chave/API privada é utilizada.
 * Só carrega tiles quando o utilizador ativa Satélite.
 * A animação só arranca se o GetCapabilities fornecer tempos reais da camada.
 */
(function(){
 'use strict';
 const SERVICE='https://view.eumetsat.int/geoserver/wms';
 const LAYER='mtg_fd:rgb_geocolour';
 const URL_VIEW='https://view.eumetsat.int/';
 function el(tag,label,parent,attributes={}){
  const n=document.createElement(tag);if(label!=null)n.textContent=label;
  for(const [k,v] of Object.entries(attributes))n.setAttribute(k,v);
  parent.appendChild(n);return n;
 }
 function delay(ms){return new Promise(resolve=>setTimeout(resolve,ms));}
 function timestamps(value){
  const times=[];
  for(const item of (value||'').trim().split(',')){
   const v=item.trim();if(!v)continue;
   if(!v.includes('/')){const ms=Date.parse(v);if(Number.isFinite(ms))times.push(new Date(ms).toISOString());continue;}
   const [a,b,period]=v.split('/');let start=Date.parse(a),end=Date.parse(b);
   // Só interpretar intervalos cuja resolução é explícita, sem inventar horas.
   const match=/^PT(?:(\d+)H)?(?:(\d+)M)?$/.exec(period||'');
   if(!match||!Number.isFinite(start)||!Number.isFinite(end))continue;
   const step=((Number(match[1]||0)*60)+Number(match[2]||0))*60*1000;
   if(step<=0)continue;
   // Ler apenas até 24 instantes mais recentes para não carregar listas enormes.
   let count=0;for(let t=end;t>=start&&count<24;t-=step,count++)times.push(new Date(t).toISOString());
  }
  return [...new Set(times)].sort().slice(-12);
 }
 function directChild(node,name){return [...node.children].find(x=>x.localName===name)||null;}
 function findLayer(node,name){
  if(node.localName==='Layer' && directChild(node,'Name')?.textContent?.trim()===name)return node;
  for(const c of node.children){const v=findLayer(c,name);if(v)return v;}
  return null;
 }
 async function discoverTimes(){
  const url=SERVICE+'?service=WMS&version=1.1.1&request=GetCapabilities';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
  try{
   const r=await fetch(url,{signal:controller.signal,mode:'cors'});
   if(!r.ok)throw Error('HTTP '+r.status);
   const xml=new DOMParser().parseFromString(await r.text(),'text/xml');
   const layer=findLayer(xml.documentElement,LAYER);
   if(!layer)throw Error('Camada não encontrada no catálogo');
   const dim=[...layer.children].find(x=>(x.localName==='Dimension'||x.localName==='Extent') && x.getAttribute('name')?.toLowerCase()==='time');
   if(!dim)throw Error('A fonte não publicou a lista de horas');
   return timestamps(dim.textContent);
  }finally{clearTimeout(timer);}
 }
 class MeteoFoxSatellite{
  constructor(map,container){
   if(!window.L||!map||!container)throw Error('Mapa não disponível');
   this.map=map;this.active=false;this.layer=null;this.timeline=[];this.timer=null;this.frameIndex=0;
   this.container=container;
   this.toggle=el('button','☁ Satélite: desligado',container,{'type':'button','aria-pressed':'false'});
   this.play=el('button','▶ Animar',container,{'type':'button'});
   this.play.disabled=true;
   this.opacityLabel=el('label','Transparência',container);
   this.opacity=el('input',null,this.opacityLabel,{'type':'range','min':'20','max':'100','step':'10','value':'70','aria-label':'Opacidade da imagem de satélite'});
   this.state=el('span','Satélite desligado · mapa e METAR disponíveis',container,{'class':'sat-status','aria-live':'polite'});
   this.attr=el('span','Fonte: EUMETSAT / Meteosat MTG GeoColour RGB · imagens observadas · disponibilidade dependente da EUMETView. ',container,{'class':'sat-attribution'});
   const link=el('a','Consultar na EUMETView',this.attr,{'href':URL_VIEW,'target':'_blank','rel':'noopener noreferrer'});link.style.color='#07518b';
   this.toggle.addEventListener('click',()=>this.setActive(!this.active));
   this.opacity.addEventListener('input',()=>this.layer?.setOpacity(Number(this.opacity.value)/100));
   this.play.addEventListener('click',()=>this.animate());
   document.addEventListener('visibilitychange',()=>{if(document.hidden)this.stop();});
  }
  setStatus(message){this.state.textContent=message;}
  async setActive(active){
   this.active=active;
   this.toggle.textContent='☁ Satélite: '+(active?'ligado':'desligado');
   this.toggle.setAttribute('aria-pressed',String(active));
   if(!active){this.stop();if(this.layer)this.map.removeLayer(this.layer);this.setStatus('Satélite desligado · marcadores METAR mantidos');return;}
   if(!this.layer){
    this.layer=L.tileLayer.wms(SERVICE,{
     layers:LAYER,styles:'',format:'image/png',transparent:true,version:'1.1.1',
     opacity:Number(this.opacity.value)/100,maxZoom:16,tileSize:256,
     attribution:'Imagem satélite © EUMETSAT / MTG GeoColour RGB'
    });
    // Colocar a imagem atrás dos marcadores, mesmo quando o mapa é reposicionado.
    this.layer.on('tileerror',()=>{
     this.errors=(this.errors||0)+1;
     if(this.errors===6 && this.active)this.setStatus('Imagens indisponíveis nesta fonte. Desliga a camada ou consulta a EUMETView.');
    });
    this.layer.on('load',()=>{this.errors=0;if(this.active&&!this.timer)this.setStatus(this.timeline.length?'Imagem disponível · animação preparada':'Imagem solicitada · para animar, consultar horas publicadas');});
   }
   this.layer.addTo(this.map);this.layer.bringToFront();
   this.setStatus('A carregar imagem Meteosat…');
   this.play.disabled=false;
  }
  stop(){if(this.timer){clearInterval(this.timer);this.timer=null;}this.play.textContent='▶ Animar';}
  showFrame(i){
   if(!this.timeline.length||!this.layer)return;
   this.frameIndex=(i+this.timeline.length)%this.timeline.length;
   const time=this.timeline[this.frameIndex];
   this.layer.setParams({time},false);
   this.setStatus('Satélite · '+new Date(time).toLocaleString('pt-PT',{timeZone:'UTC',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})+' UTC · '+(this.frameIndex+1)+'/'+this.timeline.length);
  }
  async animate(){
   if(this.timer){this.stop();return;}
   if(!this.active)return;
   if(!this.timeline.length){
    this.play.disabled=true;this.setStatus('A consultar instantes de satélite publicados…');
    try{this.timeline=await discoverTimes();}
    catch(e){this.setStatus('Animação indisponível: '+(e.name==='AbortError'?'tempo excedido':e.message)+'. A imagem estática continua disponível.');}
    finally{this.play.disabled=false;}
    if(!this.timeline.length)return;
   }
   this.showFrame(this.timeline.length-1);
   this.play.textContent='Ⅱ Pausar';
   this.timer=setInterval(()=>this.showFrame(this.frameIndex+1),1600);
  }
 }
 window.MeteoFoxSatellite=MeteoFoxSatellite;
})();
