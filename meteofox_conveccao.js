/* MeteoFox · diagnósticos cinemáticos experimentais.
   Alturas AGL aproximadas pela integração hipsométrica do perfil termodinâmico.
   Vetores em m/s; vento apresentado em kt. Sem extrapolação fora da cobertura. */
(function(){
'use strict';
const KT=0.514444444, TO_KT=1/KT;
const finite=Number.isFinite;
function interpolate(a,b,z){const f=(z-a.z)/(b.z-a.z);return {z,u:a.u+(b.u-a.u)*f,v:a.v+(b.v-a.v)*f};}
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
  return {z,u:-speed*Math.sin(rad)*KT,v:-speed*Math.cos(rad)*KT};
 }).filter(Boolean).sort((a,b)=>a.z-b.z);
 const unique=pts.filter((p,i)=>!i||p.z-pts[i-1].z>1);
 if(unique.length<3||unique[0].z>200)return {error:'Vento perto da superfície insuficiente'};
 // O primeiro nível disponível é a origem aproximada da camada AGL.
 const z0=unique[0].z,wind=unique.map(p=>({...p,z:p.z-z0}));
 const bulk=top=>{const a=at(wind,0),b=at(wind,top);return a&&b?Math.hypot(b.u-a.u,b.v-a.v)*TO_KT:null};
 const mean=(bottom,top)=>{const u=integrate(wind,top,(a,b)=>((a.u+b.u)/2)*(b.z-a.z)),v=integrate(wind,top,(a,b)=>((a.v+b.v)/2)*(b.z-a.z));if(u===null||v===null)return null;
  if(bottom===0)return {u:u/top,v:v/top};
  const ul=integrate(wind,bottom,(a,b)=>((a.u+b.u)/2)*(b.z-a.z)),vl=integrate(wind,bottom,(a,b)=>((a.v+b.v)/2)*(b.z-a.z));
  return ul===null||vl===null?null:{u:(u-ul)/(top-bottom),v:(v-vl)/(top-bottom)};
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
 return {shear1:bulk(1000),shear3:bulk(3000),shear6:bulk(6000),srh1:srh(1000,right),srh3:srh(3000,right),right:vector(right),left:vector(left),motionRight:right,wind,coverage:wind[wind.length-1].z};
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
window.MeteoFoxSevere={analyze,display};
})();
