/* MeteoFox · diagnósticos cinemáticos experimentais.
   Alturas AGL aproximadas pela integração hipsométrica do perfil termodinâmico.
   Vetores em m/s; vento apresentado em kt. Sem extrapolação fora da cobertura. */
(function(){
'use strict';
const KT=0.514444444, TO_KT=1/KT;
const finite=Number.isFinite;
function interpolate(a,b,z){const f=(z-a.z)/(b.z-a.z);return {z,u:a.u+(b.u-a.u)*f,v:a.v+(b.v-a.v)*f,p:a.p+(b.p-a.p)*f};}
function at(points,z){
 if(!points.length||z<points[0].z-1||z>points[points.length-1].z+1)return null;
 for(let i=1;i<points.length;i++)if(points[i-1].z<=z&&z<=points[i].z)return interpolate(points[i-1],points[i],z);
 return Math.abs(points[0].z-z)<1?points[0]:null;
}
function integrate(points,top,fn){
 const subset=[at(points,0),...points.filter(p=>p.z>0&&p.z<top),at(points,top)];
 if(subset.some(p=>!p))return null;
 let sum=0;for(let i=1;i<subset.length;i++)sum+=fn(subset[i-1],subset[i]);return sum;
}
function analyze(group,thermo){
 if(!thermo?.samples?.length)return {error:'Alturas hipsométricas indisponíveis'};
 const samples=thermo.samples.filter(p=>finite(p.p)&&finite(p.z)).sort((a,b)=>b.p-a.p);
 if(samples.length<2)return {error:'Perfil vertical insuficiente'};
 const height=p=>{
  if(p>samples[0].p||p<samples[samples.length-1].p)return null;
  for(let i=1;i<samples.length;i++){
   const a=samples[i-1],b=samples[i];
   if(a.p>=p&&p>=b.p){const f=Math.log(a.p/p)/Math.log(a.p/b.p);return a.z+f*(b.z-a.z);}
  }
  return null;
 };
 const pts=group.map(r=>{
  const p=Number(r.hpa),speed=Number(r.wind_kt),dir=Number(r.wind_dir_deg);
  const z=height(p);
  if(!finite(z)||!finite(speed)||!finite(dir)||speed<0||dir<0||dir>360)return null;
  const rad=dir*Math.PI/180;
  return {z,p,u:-speed*Math.sin(rad)*KT,v:-speed*Math.cos(rad)*KT};
 }).filter(Boolean).sort((a,b)=>a.z-b.z);
 const unique=pts.filter((p,i)=>!i||p.z-pts[i-1].z>1);
 if(unique.length<3||unique[0].z>200)return {error:'Vento perto da superfície insuficiente'};
 // O primeiro nível disponível é a origem aproximada da camada AGL.
 const z0=unique[0].z,wind=unique.map(p=>({...p,z:p.z-z0}));
 const bulk=top=>{const a=at(wind,0),b=at(wind,top);return a&&b?Math.hypot(b.u-a.u,b.v-a.v)*TO_KT:null};
 // MetPy Bunkers: médias de vento ponderadas pela pressão, não pela altura.
 const mean=(bottom,top)=>{
  const a=at(wind,bottom),b=at(wind,top);
  if(!a||!b)return null;
  const section=[a,...wind.filter(p=>p.z>bottom&&p.z<top),b];
  let su=0,sv=0,weight=0;
  for(let i=1;i<section.length;i++){
   const x=section[i-1],y=section[i],dp=x.p-y.p;
   if(!(dp>0))return null;
   su+=(x.u+y.u)*.5*dp;sv+=(x.v+y.v)*.5*dp;weight+=dp;
  }
  return weight>0?{u:su/weight,v:sv/weight}:null;
 };
 const m06=mean(0,6000),low=mean(0,500),high=mean(5500,6000);
 let right=null,left=null;
 if(m06&&low&&high){
  const du=high.u-low.u,dv=high.v-low.v,mag=Math.hypot(du,dv);
  if(mag>=0.5){
   // Bunkers (2000): desvio de 7.5 m/s à direita do shear 0–6 km.
   right={u:m06.u+7.5*dv/mag,v:m06.v-7.5*du/mag};
   left={u:m06.u-7.5*dv/mag,v:m06.v+7.5*du/mag};
  }
 }
 const srh=(top,motion)=>motion?integrate(wind,top,(a,b)=>(b.u-a.u)*(a.v-motion.v)-(b.v-a.v)*(a.u-motion.u)):null;
 const vector=v=>v?{speed:Math.hypot(v.u,v.v)*TO_KT,dir:(Math.atan2(v.u,v.v)*180/Math.PI+360)%360}:null; // direção PARA onde se desloca
 return {motionLeft:left,shear1:bulk(1000),shear3:bulk(3000),shear6:bulk(6000),srh1:srh(1000,right),srh3:srh(3000,right),right:vector(right),left:vector(left),motionRight:right,wind,coverage:wind[wind.length-1].z};
}

// Additional interactive hodograph annotations; no synthetic wind data.
function decorateHodograph(group,thermo){
 const svg=document.getElementById('hodograph');if(!svg)return;
 const result=analyze(group,thermo);
 const NS='http://www.w3.org/2000/svg',cx=290,cy=288,radius=228;
 const existing=svg.querySelectorAll('.fox-hodo-enhanced');existing.forEach(n=>n.remove());
 const wind=result.wind||[];
 const info=document.getElementById('hodoInteractiveInfo');
 if(info)info.textContent=result.error?'Alturas AGL indisponíveis: '+result.error:'Seleciona um ponto do hodógrafo para consultar o vento e a altura estimada.';
 if(!wind.length)return;
 const speeds=wind.map(p=>Math.hypot(p.u,p.v)*TO_KT);
 // Match the scale used by the existing drawHodograph renderer.
 const extent=Math.max(40,Math.ceil((Math.max(...speeds,20)+10)/20)*20);
 const scale=radius/extent;
 const point=(u,v)=>({x:cx+u*TO_KT*scale,y:cy-v*TO_KT*scale});
 const add=(tag,attrs,parent=svg)=>{const e=document.createElementNS(NS,tag);e.classList.add('fox-hodo-enhanced');for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));parent.appendChild(e);return e;};
 const show=(message)=>{if(info)info.textContent=message;};
 // Label selected height levels only where interpolation is supported.
 for(const height of [0,1000,3000,6000]){
  const p=at(wind,height);if(!p)continue;
  const xy=point(p.u,p.v);
  const marker=add('circle',{cx:xy.x,cy:xy.y,r:7,fill:'#ffffff',stroke:'#253c55','stroke-width':1.7,tabindex:0,role:'button','aria-label':'Vento a '+height/1000+' km AGL'});
  const label=(height/1000)+' km';
  const msg=label+' AGL (aprox.) · '+Math.round(Math.hypot(p.u,p.v)*TO_KT)+' kt · '+Math.round((Math.atan2(-p.u,-p.v)*180/Math.PI+360)%360)+'° (de onde sopra)';
  marker.addEventListener('pointerenter',()=>show(msg));
  marker.addEventListener('focus',()=>show(msg));
  marker.addEventListener('click',()=>show(msg));
  marker.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show(msg)}});
  const t=document.createElementNS(NS,'title');t.textContent=msg;marker.appendChild(t);
  add('text',{x:xy.x+9,y:xy.y-10,'font-size':12,fill:'#23364a','paint-order':'stroke',stroke:'#ffffff','stroke-width':3},svg).textContent=label;
 }
 const arrows=[['R',result.motionRight,'#b45309'],['L',result.motionLeft,'#7c3aed']];
 for(const [label,motion,color] of arrows){
  if(!motion||!Number.isFinite(motion.u)||!Number.isFinite(motion.v))continue;
  const xy=point(motion.u,motion.v);
  const circle=add('circle',{cx:xy.x,cy:xy.y,r:9,fill:'#ffffff',stroke:color,'stroke-width':3,tabindex:0,role:'button','aria-label':'Bunkers '+label});
  const speed=Math.hypot(motion.u,motion.v)*TO_KT;
  const dir=(Math.atan2(motion.u,motion.v)*180/Math.PI+360)%360;
  const msg='Bunkers '+(label==='R'?'direita':'esquerda')+' · '+Math.round(dir)+'° (para onde vai) / '+Math.round(speed)+' kt';
  for(const event of ['pointerenter','focus','click'])circle.addEventListener(event,()=>show(msg));
  circle.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show(msg)}});
  const title=document.createElementNS(NS,'title');title.textContent=msg;circle.appendChild(title);
  add('text',{x:xy.x+12,y:xy.y+4,'font-size':14,'font-weight':'bold',fill:color,'paint-order':'stroke',stroke:'#fff','stroke-width':3}).textContent=label;
 }
}

function install(){
 const h=document.getElementById('hodograph');if(!h||document.getElementById('severePanel'))return;
 const panel=document.createElement('section');panel.id='severePanel';panel.className='cloud-panel';
 panel.innerHTML='<h3>Convecção severa · cinemática estimada</h3><div class="convective-factors" aria-label="Diagnósticos de cisalhamento e helicidade">'+
 '<span>Shear 0–1 km <strong id="severeS1">—</strong></span>'+
 '<span>Shear 0–3 km <strong id="severeS3">—</strong></span>'+
 '<span>Shear 0–6 km <strong id="severeS6">—</strong></span>'+
 '<span>SRH 0–1 km <strong id="severeH1">—</strong></span>'+
 '<span>SRH 0–3 km <strong id="severeH3">—</strong></span>'+
 '<span>Bunkers direita <strong id="severeR">—</strong></span>'+
 '<span>Bunkers esquerda <strong id="severeL">—</strong></span></div>'+
 '<p class="muted" id="severeNote">Estimativas experimentais com altura hipsométrica AGL aproximada. Bunkers requer perfil até 6 km; SRH calculada para movimento Bunkers à direita. Direção do movimento indica para onde a tempestade se desloca. Não é aviso de tempo severo.</p>';
 const layout=h.closest('.sounding-layout');if(layout)layout.insertAdjacentElement('afterend',panel);
}
function display(group,thermo){
 install();const r=analyze(group,thermo),set=(id,value)=>{const e=document.getElementById(id);if(e)e.textContent=value;};
 const kt=v=>finite(v)?v.toFixed(0)+' kt':'—';
 const srh=v=>finite(v)?v.toFixed(0)+' m²/s²':'—';
 const motion=v=>v?Math.round(v.dir).toString().padStart(3,'0')+'° / '+v.speed.toFixed(0)+' kt':'—';
 set('severeS1',kt(r.shear1));set('severeS3',kt(r.shear3));set('severeS6',kt(r.shear6));
 set('severeH1',srh(r.srh1));set('severeH3',srh(r.srh3));
 set('severeR',motion(r.right));set('severeL',motion(r.left));
 const note=document.getElementById('severeNote');
 if(note)note.textContent=r.error?'Diagnóstico indisponível: '+r.error:
  'Cinemática experimental · alturas AGL aproximadas (integração hipsométrica). Shear vetorial em kt; SRH com movimento Bunkers à direita. Direção de deslocação da tempestade (para onde vai). '+(r.coverage<6000?'Perfil não cobre 6 km: parâmetros dependentes dessa camada indisponíveis. ':'')+'Não constitui aviso meteorológico.';
}
window.MeteoFoxSevere={analyze,display,decorateHodograph};
})();
