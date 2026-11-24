/* MeteoFox · Fox Verified
   Confronto indicativo ECMWF IFS/Open-Meteo com METAR e SYNOP.
   Não se trata de verificação histórica de um ciclo de previsão arquivado. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const sites={
 'Lisboa':{lat:38.7223,lon:-9.1393,icao:'LPPT',wmo:'08536',label:'Lisboa / Portela'},
 'Valência':{lat:39.4699,lon:-0.3763,icao:'LEVC',wmo:'08284',label:'Валенсия / Манисес'},
 'Porto':{lat:41.1579,lon:-8.6291,icao:'LPPR',wmo:'08545',label:'Porto / Pedras Rubras'},
 'Beja':{lat:38.0151,lon:-7.8632,icao:'LPBJ',wmo:'08562',label:'Beja'}
};
const m=(value,dec=1)=>Number.isFinite(value)?value.toFixed(dec):'—';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const utc=s=>s?new Date(s).toLocaleString('pt-PT',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+' UTC':'—';
const ms=s=>s?Date.parse(s):NaN;
const fresh=(date,h)=>Number.isFinite(ms(date))&&Date.now()-ms(date)>=-3600000&&Date.now()-ms(date)<=h*3600000;
const near=(times,stamp)=>{if(!Array.isArray(times)||!Number.isFinite(ms(stamp)))return -1;let best=-1,diff=Infinity;times.forEach((s,i)=>{const x=Math.abs(ms(s+'Z')-ms(stamp));if(x<diff){diff=x;best=i;}});return diff<=45*60000?best:-1;};
const parseMetar=raw=>{
 if(!raw||/\bNIL\b/i.test(raw))return {};
 const speed=raw.match(/\b(?:\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b/);
 const temp=raw.match(/\s(M?\d{2})\/(?:M?\d{2}|\/\/)(?=\s|=)/);
 const dec=s=>s?Number(s.replace('M','-')):null;
 return {wind:speed?Number(speed[1]):null,gust:speed&&speed[2]?Number(speed[2]):null,temp:temp?dec(temp[1]):null};
};
function row(label,model,obs,unit,desc,dec=1){
 const both=Number.isFinite(model)&&Number.isFinite(obs);
 const delta=both?model-obs:null;
 const diff=both?(delta>0?'+':'')+m(delta,dec):'—';
 return '<tr><td>'+esc(label)+'</td><td>'+ (Number.isFinite(model)?m(model,dec):'—')+
 '</td><td>'+(Number.isFinite(obs)?m(obs,dec):'—')+'</td><td class="'+(both?'fox-delta':'')+'">'+diff+
 '</td><td>'+esc(unit)+'</td><td class="fox-cell-note">'+esc(desc)+'</td></tr>';
}
let request=0;
let focusBefore=null;
function closeFox(){
 const panel=$('foxVerifiedPanel'),button=$('foxVerifiedButton');
 if(!panel||!panel.open)return;
 request++;
 panel.close();
}
function showFox(panel,html){
 panel.innerHTML='<div class="fox-modal" role="document">'+html+'</div>';
}
async function verify(){
 const place=$('place')?.value;
 const info=sites[place],panel=$('foxVerifiedPanel'),button=$('foxVerifiedButton');
 if(!info||!panel)return;
 const id=++request,ru=place==='Valência';
 focusBefore=document.activeElement;
 button.disabled=true;panel.hidden=false;
 showFox(panel,'<div class="fox-panel-head"><div><strong>Fox Verified · '+(ru?'Валенсия':esc(place))+'</strong><span>'+(ru?'ECMWF IFS × инструментальные наблюдения':'ECMWF IFS × observações instrumentais')+'</span></div><button type="button" class="action" data-fox-close>'+(ru?'✕ Закрыть':'✕ Fechar')+'</button></div><div class="fox-wait" role="status">'+(ru?'Загрузка прогноза и наблюдений METAR/SYNOP…':'A consultar previsões ECMWF e observações METAR/SYNOP…')+'</div>');
 panel.showModal();
 button.setAttribute('aria-expanded','true');
 panel.querySelector('[data-fox-close]')?.focus();
 try{
  const url='https://api.open-meteo.com/v1/forecast?latitude='+info.lat+'&longitude='+info.lon+
   '&hourly=temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation'+
   '&models=ecmwf_ifs025&past_days=3&forecast_days=1&timezone=GMT&wind_speed_unit='+(ru?'kmh':'kn');
  const [weather,aviation,synop]=await Promise.all([
   fetch(url,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('ECMWF/Open-Meteo indisponível ('+r.status+')');return r.json()}),
   fetch(ru?'./data/aviation_valencia.json':'./data/aviation.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('METAR indisponível');return r.json()}),
   fetch('./data/synop.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('SYNOP indisponível');return r.json()})
  ]);
  if(id!==request||$('place').value!==place)return;
  const h=weather.hourly||{},metar=aviation.metar?.[info.icao];
  const mm=parseMetar(metar?.raw),mTime=metar?.utc;
  if(ru){if(mm.wind!=null)mm.wind*=1.852;if(mm.gust!=null)mm.gust*=1.852;}
  const mi=near(h.time,mTime);
  const metarOK=fresh(mTime,6)&&mi>=0&&!/\bNIL\b/.test(metar?.raw||'');
  const st=synop.stations?.find(s=>String(s.station)===info.wmo);
  const periods=st?.periods||{};
  // Prioridade a intervalos observados mais recentes; nunca comparar acumulado de 12 h com valor horário.
  const candidates=Object.entries(periods).filter(([k,p])=>[6,12,24].includes(Number(k))&&p&&!p.suspect&&!p.lower_bound&&p.trace!==true&&p.mm!=null&&Number.isFinite(p.mm)&&p.hours===Number(k)&&fresh(p.utc,36))
    .sort((a,b)=>ms(b[1].utc)-ms(a[1].utc)||Number(a[0])-Number(b[0]));
  const pick=candidates[0],hours=pick?Number(pick[0]):null,p=pick?.[1];
  let predicted=null;
  if(p&&Array.isArray(h.time)&&Array.isArray(h.precipitation)){
   const end=ms(p.utc),start=end-hours*3600000;
   const inds=h.time.map((t,i)=>({t:ms(t+'Z'),i})).filter(x=>x.t>start&&x.t<=end);
   if(inds.length===hours&&inds.every((x,i)=>x.t===start+(i+1)*3600000&&Number.isFinite(h.precipitation[x.i])))
    predicted=inds.reduce((a,x)=>a+Number(h.precipitation[x.i]),0);
  }
  const metarNote=metarOK?info.icao+' · '+utc(mTime):(ru?'Нет актуального METAR':'METAR recente indisponível');
  const rainNote=p?info.wmo+' · '+hours+(ru?' ч до ':' h até ')+utc(p.utc):(ru?'Нет сопоставимых данных SYNOP':'Acumulado SYNOP recente indisponível');
  const content='<div class="fox-panel-head"><div><strong>Fox Verified · '+(ru?'Валенсия':esc(place))+'</strong><span>'+(ru?'ECMWF IFS × инструментальные наблюдения':'ECMWF IFS × observações instrumentais')+'</span></div><button type="button" class="action" data-fox-close>'+(ru?'✕ Закрыть':'✕ Fechar')+'</button></div>'+
   '<div class="tablewrap"><table class="fox-table"><thead><tr><th>'+(ru?'Параметр':'Elemento')+'</th><th>'+(ru?'Модель':'Modelo')+'</th><th>'+(ru?'Наблюдение':'Observado')+'</th><th>'+(ru?'Разница':'Diferença')+'</th><th>'+(ru?'Ед.':'Unid.')+'</th><th>'+(ru?'Источник':'Referência')+'</th></tr></thead><tbody>'+
   row(ru?'Температура':'Temperatura',metarOK&&mi>=0?Number(h.temperature_2m?.[mi]):null,metarOK?mm.temp:null,'°C',metarNote)+
   row(ru?'Средний ветер':'Vento médio',metarOK&&mi>=0?Number(h.wind_speed_10m?.[mi]):null,metarOK?mm.wind:null,ru?'км/ч':'kt',metarNote)+
   row(ru?'Порывы':'Rajada',metarOK&&mi>=0&&mm.gust!=null?Number(h.wind_gusts_10m?.[mi]):null,metarOK?mm.gust:null,ru?'км/ч':'kt',mm.gust==null?(ru?'Порывы не указаны в METAR; это не означает нулевую скорость':'Rajada não reportada no METAR · não equivale a 0 kt'):metarNote)+
   row(ru?'Осадки':'Precipitação '+(hours?hours+' h':''),predicted,p&&Number.isFinite(Number(p.mm))?Number(p.mm):null,ru?'мм':'mm',rainNote)+
   '</tbody></table></div>'+
   '<p class="note">'+(ru?'Разница = модель минус наблюдение. Сравниваются ближайшие сроки по UTC. Порывы в METAR могут отличаться по определению от часовых порывов модели. Осадки сравниваются только за одинаковые интервалы.':'Diferença = modelo − observado. As horas e intervalos são aproximados à resolução horária do modelo. A rajada METAR é uma observação reportada e pode não ser diretamente equivalente à rajada horária prevista. A precipitação é comparada apenas em intervalos de igual duração.')+'</p>'+
   '<p class="note">'+(ru?'Методология: ориентировочное сопоставление с текущим прогнозом, не архивная проверка отдельного цикла ECMWF. Пропущенные или устаревшие данные показаны знаком «—».':'Nota metodológica: comparação indicativa com previsões consultadas no momento, que podem já incorporar observações recentes; não constitui verificação histórica de um ciclo ECMWF arquivado. Dados em falta ou desatualizados ficam assinalados como «—».')+'</p>';
  showFox(panel,content);
 }catch(e){
  if(id!==request)return;
  showFox(panel,'<div class="fox-panel-head"><strong>Fox Verified · '+(ru?'Валенсия':esc(place))+'</strong><button type="button" class="action" data-fox-close>'+(ru?'✕ Закрыть':'✕ Fechar')+'</button></div><div role="status" class="fox-fail">'+(ru?'Не удалось выполнить сравнение: ':'Não foi possível obter a comparação: ')+esc(e.message)+'.</div>');
 }finally{if(id===request)button.disabled=false;}
}
function init(){
 const region=$('overview'),heading=region?.querySelector('.heading'),place=$('place');
 if(!region||!heading||!place)return;
 const button=document.createElement('button');
 button.type='button';button.id='foxVerifiedButton';button.className='action fox-trigger';
 button.textContent='✓ Fox Verified';button.setAttribute('aria-controls','foxVerifiedPanel');button.setAttribute('aria-expanded','false');
 heading.append(button);
 const panel=document.createElement('dialog');panel.id='foxVerifiedPanel';panel.className='fox-verified';panel.hidden=true;
 panel.setAttribute('aria-label','Fox Verified · comparação meteorológica');
 document.body.append(panel);
 panel.addEventListener('click',event=>{
  if(event.target.closest?.('[data-fox-close]')){closeFox();return;}
  if(event.target===panel)closeFox();
 });
 panel.addEventListener('close',()=>{
  request++;
  panel.hidden=true;
  button.setAttribute('aria-expanded','false');
  button.disabled=false;
  if(focusBefore?.isConnected)focusBefore.focus();else button.focus();
 });

 function sync(){closeFox();request++;const active=!!sites[place.value];button.hidden=!active;if(!panel.open)panel.hidden=true;button.disabled=false;button.setAttribute('aria-expanded','false');}
 place.addEventListener('change',sync);
 button.addEventListener('click',verify);sync();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();