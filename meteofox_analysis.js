/* MeteoFox Fox Analysis: deterministic, data-aware interpretation of existing soundings. */
(function(){
'use strict';
const finite=Number.isFinite;
const $=id=>document.getElementById(id);
const text=(id,value)=>{const e=$(id);if(e)e.textContent=value;};
function install(){
 const layout=document.querySelector('.sounding-layout');
 if(!layout||$('foxAnalysis'))return;
 const summary=document.createElement('section');
 summary.id='foxAnalysis';summary.className='cloud-panel fox-analysis';
 summary.setAttribute('aria-label','Fox Analysis - síntese meteorológica');
 summary.innerHTML='<div class="fox-analysis-head"><h3>Fox Analysis · Diagnóstico vertical</h3><span class="fox-experimental">Análise experimental</span></div><p id="foxHeadline" class="fox-headline">A aguardar perfil…</p><p id="foxExplanation" class="muted"></p><div class="fox-metrics"><div><small>Instabilidade</small><strong id="foxInstability">—</strong></div><div><small>Cisalhamento 0–6 km</small><strong id="foxShear">—</strong></div><div><small>Humidade média</small><strong id="foxHumidity">—</strong></div><div><small>Organização convectiva</small><strong id="foxOrganization">—</strong></div></div><p id="foxQuality" class="fox-quality"></p><p class="muted">Síntese determinística do perfil, não uma previsão de ocorrência. Não avalia forçamento, convergência ou iniciação convectiva.</p>';
 layout.insertAdjacentElement('afterend',summary);
 const panels=[
  {id:'thermoAdvanced',group:'thermo'},
  {id:'severePanel',group:'kin'},
  {id:'compositeAdvanced',group:'conv'},
 ];
 // Existing severePanel is installed dynamically by meteofox_conveccao.js.
 const cloud=[...document.querySelectorAll('.cloud-panel')].find(p=>p.querySelector('#cloudDepth'));
 if(cloud)cloud.dataset.foxGroup='conv';
 for(const p of panels){const el=$(p.id);if(el)el.dataset.foxGroup=p.group;}
 const nav=document.createElement('div');nav.id='foxTabs';nav.className='fox-tabs';nav.setAttribute('role','tablist');nav.setAttribute('aria-label','Parâmetros de análise');
 for(const [group,label] of [['thermo','Termodinâmica'],['kin','Cinemática'],['conv','Convecção']]){
  const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.foxTab=group;b.setAttribute('role','tab');b.addEventListener('click',()=>activate(group));nav.appendChild(b);
 }
 summary.insertAdjacentElement('afterend',nav);
 activate('thermo');
}
function activate(group){
 document.querySelectorAll('[data-fox-tab]').forEach(b=>{const selected=b.dataset.foxTab===group;b.setAttribute('aria-selected',String(selected));b.classList.toggle('active',selected);});
 document.querySelectorAll('[data-fox-group]').forEach(p=>{p.hidden=p.dataset.foxGroup!==group;});
}
function update(group,thermo,run,valid,city){
 install();
 if(!$('foxAnalysis'))return;
 // The diagnostics use the SAME selected profile as the two diagrams.
 const kin=window.MeteoFoxSevere?.analyze(group,thermo)||{};
 const record=window.advancedThermo?.run_utc===run?window.advancedThermo.soundings?.find(x=>x.valid_utc===valid)?.cities?.[city]:null;
 // advancedThermo is lexical in laboratorio.html; use rendered MetPy fields only if they have valid numbers.
 const read=id=>{const v=$(id)?.textContent?.trim();return v&&v!=='—'&&/^-?\d+(\.\d+)?\s/.test(v)?Number.parseFloat(v):null;};
 const ml=read('advMLCAPE'),mu=read('advMUCAPE');
 const cape=finite(mu)?mu:finite(ml)?ml:finite(thermo?.cape)?thermo.cape:null;
 const shear=finite(kin.shear6)?kin.shear6:null;
 const rhRaw=$('cloudRH')?.textContent||'';
 const rh=/^\s*\d+(?:\.\d+)?\s*%/.test(rhRaw)?Number.parseFloat(rhRaw):null;
 const hasCape=finite(cape),hasShear=finite(shear),hasRh=finite(rh);
 let inst='Dados insuficientes',humidity='Dados insuficientes',organization='Indeterminada';
 if(hasCape)inst=cape<100?'Muito reduzida':cape<500?'Reduzida':cape<1500?'Moderada':cape<2500?'Elevada':'Muito elevada';
 if(hasRh)humidity=rh<20?'Muito baixa':rh<40?'Baixa':rh<65?'Moderada':'Elevada';
 if(hasCape&&hasShear)organization=cape<100?'Não favorecida pelo perfil':shear<20?'Limitada pelo cisalhamento':shear<35?'Potencial de organização moderado':'Ambiente potencialmente organizado';
 let headline='Diagnóstico inconclusivo: dados essenciais indisponíveis';
 if(hasCape&&hasShear)headline=cape<100?'Convecção profunda não favorecida pelo perfil':cape<500?'Instabilidade limitada; avaliar forçamento e humidade':shear>=35?'Instabilidade e cisalhamento favoráveis à organização potencial':'Instabilidade presente; organização depende do ambiente';
 const parts=[];
 if(hasCape)parts.push('CAPE de referência '+Math.round(cape)+' J/kg'+(finite(mu)?' (MU)':finite(ml)?' (ML)':' (parcela de superfície)'));
 if(hasShear)parts.push('shear 0–6 km '+Math.round(shear)+' kt');
 if(hasRh)parts.push('HR 700–500 hPa '+Math.round(rh)+'%');
 text('foxHeadline',headline);
 text('foxExplanation',parts.length?parts.join(' · ')+'. A presença de cisalhamento, isoladamente, não implica formação de tempestades.':'Não há parâmetros suficientes para uma interpretação integrada.');
 text('foxInstability',inst);
 text('foxShear',hasShear?Math.round(shear)+' kt':'Indisponível');
 text('foxHumidity',humidity);
 text('foxOrganization',organization);
 const missing=[];
 if(!hasCape)missing.push('CAPE');if(!hasShear)missing.push('shear 0–6 km');if(!hasRh)missing.push('HR média');
 const top=thermo?.complete===false?' LFC/EL não completos ou não identificados.':'';
 text('foxQuality',missing.length?'Qualidade: análise parcial; indisponível: '+missing.join(', ')+'.'+top:'Qualidade: parâmetros principais disponíveis; alturas AGL aproximadas e níveis isobáricos limitados.'+top);
}
window.MeteoFoxAnalysis={install,update};
})();