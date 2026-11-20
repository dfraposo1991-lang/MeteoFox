/* MeteoFox · meteograma por localidade, a partir da previsão ECMWF IFS 0p25 via Open-Meteo (sem ciclos inferidos). */
(function () {
'use strict';
var svgNS='http://www.w3.org/2000/svg', rows=[], region='', active=0, expanded=false, previousFocus=null;
var $=function(id){return document.getElementById(id);};
function node(tag,attrs,value){var el=document.createElementNS(svgNS,tag);Object.keys(attrs||{}).forEach(function(k){el.setAttribute(k,attrs[k]);});if(value!==undefined)el.textContent=value;return el;}
function add(parent,tag,attrs,value){var el=node(tag,attrs,value);parent.appendChild(el);return el;}
function txt(svg,value,x,y,size,color,weight,anchor){return add(svg,'text',{x:x,y:y,'font-family':'Inter,system-ui,sans-serif','font-size':size||13,fill:color||'#26374b','font-weight':weight||500,'text-anchor':anchor||'start'},value);}
function dateOf(row){return new Date(row.valid_utc);}
function isRussian(){return region==='Валенсия';}
function windUnit(){return isRussian()?'км/ч':'kt';}
function dayName(d){return d.toLocaleDateString(isRussian()?'ru-RU':'pt-PT',{timeZone:'UTC',weekday:'short',day:'numeric',month:'short'});}
function hour(d){return d.toLocaleTimeString('pt-PT',{timeZone:'UTC',hour:'2-digit',hourCycle:'h23'}).slice(0,2)+'h';}
function cloudIcon(cover,rain){if(rain>=0.3&&cover>=45)return '🌧';if(cover>=85)return '☁';if(cover>=55)return '☁';if(cover>=25)return '⛅';return '☀';}
function draw(target,compact){
 var svg=$(target);if(!svg||!rows.length)return;
 svg.replaceChildren();
 var col=42, left=170, top=33, width=left+col*rows.length+10, height=420;
 svg.setAttribute('viewBox','0 0 '+width+' '+height);
 svg.setAttribute('role','img');
 add(svg,'rect',{x:0,y:0,width:width,height:height,rx:10,fill:'#ffffff'});
 var boundaries=[0,33,70,127,275,315,350,385,419];
 boundaries.forEach(function(y){add(svg,'line',{x1:0,x2:width,y1:y,y2:y,stroke:'#d9e2ea','stroke-width':1});});
 for(var i=0;i<=rows.length;i++)add(svg,'line',{x1:left+i*col,x2:left+i*col,y1:33,y2:419,stroke:'#e2e8f0','stroke-width':0.8});
 txt(svg,isRussian()?'Время UTC':'Hora UTC',12,56,13,'#475569');
 txt(svg,isRussian()?'Облачность':'Nuvens',12,107,16,'#243447',600);
 txt(svg,isRussian()?'Осадки':'Precipitação',12,193,15,'#243447',600);
 txt(svg,'(mm/3 h)',12,212,12,'#667788');
 txt(svg,isRussian()?'Температура (°C)':'Temperatura (°C)',12,303,14,'#26374b',600);
 txt(svg,isRussian()?'Направление ветра':'Direção do vento',12,338,13,'#26374b',600);
 txt(svg,isRussian()?'Ветер (км/ч)':'Vento médio (kt)',12,373,13,'#26374b',600);
 txt(svg,isRussian()?'Порывы (км/ч)':'Rajadas (kt)',12,408,14,'#26374b',600);
 var groups=[],key='';
 rows.forEach(function(r,i){var d=dateOf(r),k=r.valid_utc.slice(0,10);if(k!==key){groups.push({start:i,n:1,date:d});key=k;}else groups[groups.length-1].n++;});
 groups.forEach(function(g,j){
  var x=left+g.start*col;
  add(svg,'rect',{x:x,y:0,width:g.n*col,height:33,fill:j%2?'#f1f5f9':'#f8fafc',stroke:'#dde5ec'});
  txt(svg,dayName(g.date),x+g.n*col/2,22,14,'#26374b',700,'middle');
  add(svg,'line',{x1:x,x2:x,y1:33,y2:419,stroke:'#c5d2df','stroke-width':1.5});
 });
 var rainScale=Math.max(1,Math.ceil(Math.max.apply(null,rows.map(function(r){return Number(r.rain_3h_mm)||0;}))*2)/2);
 for(var j=0;j<=4;j++){
  var y=266-j*124/4, val=rainScale*j/4;
  add(svg,'line',{x1:left,x2:width,y1:y,y2:y,stroke:'#d2dce7','stroke-dasharray':'3 5'});
  txt(svg,val.toFixed(1),left-8,y+4,11,'#4f6477',400,'end');
 }
 rows.forEach(function(r,i){
  var x=left+i*col, mid=x+col/2, d=dateOf(r), precip=Math.max(0,Number(r.rain_3h_mm)||0), cover=Math.max(0,Number(r.cloud_percent)||0);
  txt(svg,hour(d),mid,55,13,'#26374b',500,'middle');
  txt(svg,cloudIcon(cover,precip),mid,107,23,'#d3eaf4',500,'middle');
  var bar=Math.max(0,precip/rainScale*124);
  if(precip>0)add(svg,'rect',{x:x+6,y:266-Math.max(2,bar),width:col-12,height:Math.max(2,bar),rx:2,fill:'#3797ec'});
  txt(svg,Math.round(Number(r.temp_c))+'°',mid,303,16,'#a15b10',700,'middle');
  var degrees=Number(r.wind_dir_deg)||0;
  // Seta orientada para onde o vento sopra (180° oposto à direção meteorológica de origem).
  txt(svg,'↑',mid,340,25,'#1a567b',700,'middle').setAttribute('transform','rotate('+((degrees+180)%360)+' '+mid+' 333)');
  txt(svg,String(Math.round(Number(r.wind_kt))),mid,373,15,'#26374b',600,'middle');
  txt(svg,String(Math.round(Number(r.gust_kt))),mid,408,15,'#9b4e13',700,'middle');
  if(!compact&&active===i)add(svg,'rect',{x:x+1,y:33,width:col-2,height:385,rx:3,fill:'#dbeafe','fill-opacity':0.45,stroke:'#356d9b','stroke-width':1.5,'pointer-events':'none'});
  if(!compact){var hit=add(svg,'rect',{x:x,y:33,width:col,height:385,fill:'transparent',style:'cursor:pointer'});hit.addEventListener('click',function(){select(i);});}
 });
}
function select(i){active=Math.max(0,Math.min(rows.length-1,i));draw('meteoLargeSvg',false);if(!$('meteoDetails'))return;var r=rows[active],d=dateOf(r);
 $('meteoDetails').textContent=isRussian()?
  region+' · '+dayName(d)+' '+hour(d)+' UTC · Осадки '+Number(r.rain_3h_mm).toFixed(2)+' мм/3 ч · Температура '+Number(r.temp_c).toFixed(1)+' °C · Ветер '+Number(r.wind_kt).toFixed(0)+' км/ч · Порывы '+Number(r.gust_kt).toFixed(0)+' км/ч · Облачность '+Math.round(r.cloud_percent)+'%':
  region+' · '+dayName(d)+' '+hour(d)+' UTC · Chuva '+Number(r.rain_3h_mm).toFixed(2)+' mm/3h · Temperatura '+Number(r.temp_c).toFixed(1)+' °C · Vento '+Number(r.wind_kt).toFixed(0)+' kt · Rajadas '+Number(r.gust_kt).toFixed(0)+' kt · Nuvens '+Math.round(r.cloud_percent)+'%';
 $('meteoTimeSlider').value=String(active);
}
function open(){if(!rows.length)return;expanded=true;previousFocus=document.activeElement;$('meteoDialog').hidden=false;document.body.classList.add('meteo-dialog-open');select(active);$('meteoClose').focus();}
function close(){if(!expanded)return;expanded=false;$('meteoDialog').hidden=true;document.body.classList.remove('meteo-dialog-open');if(previousFocus)previousFocus.focus();}
function fromHourly(data){
 var h=data&&data.hourly;
 if(!h||!Array.isArray(h.time))throw Error('Previsão horária não disponível');
 var required=['temperature_2m','cloud_cover','precipitation','wind_speed_10m','wind_direction_10m','wind_gusts_10m'];
 if(required.some(function(k){return !Array.isArray(h[k])||h[k].length!==h.time.length;}))throw Error('Faltam variáveis horárias do meteograma');
 var look=new Map(h.time.map(function(t,i){return [String(t).slice(0,16),i];}));
 var now=new Date(),start=new Date(now);
 start.setUTCMinutes(0,0,0);
 start.setUTCHours(Math.ceil((start.getUTCHours()+1)/3)*3);
 var output=[];
 for(var i=0;i<30;i++){
  var valid=new Date(start.getTime()+i*3*3600000);
  var indexes=[];
  for(var back=2;back>=0;back--){
   var d=new Date(valid.getTime()-back*3600000),key=d.toISOString().slice(0,16),idx=look.get(key);
   if(idx===undefined)throw Error('Períodos ECMWF incompletos para esta localidade: '+key);
   indexes.push(idx);
  }
  var last=indexes[2],v=function(key,j){var n=Number(h[key][j]);if(!Number.isFinite(n))throw Error('Valor ECMWF inválido: '+key);return n;};
  output.push({
   step_h:(i+1)*3,valid_utc:valid.toISOString(),
   temp_c:v('temperature_2m',last),
   cloud_percent:indexes.reduce(function(sum,j){return sum+v('cloud_cover',j);},0)/3,
   rain_3h_mm:indexes.reduce(function(sum,j){return sum+Math.max(0,v('precipitation',j));},0),
   wind_kt:indexes.reduce(function(sum,j){return sum+v('wind_speed_10m',j);},0)/3,
   wind_dir_deg:v('wind_direction_10m',last),
   gust_kt:Math.max.apply(null,indexes.map(function(j){return v('wind_gusts_10m',j);}))
  });
 }
 return output;
}
function reset(){rows=[];$('meteoPreview').disabled=true;$('meteoSmallSvg').replaceChildren();$('meteoLargeSvg').replaceChildren();}
function loading(name){region=name;reset();$('meteoInfo').textContent=isRussian()?name+' · Загрузка прогноза ECMWF…':name+' · A consultar previsão ECMWF…';$('meteoModalTitle').textContent=(isRussian()?'Метеограмма · ':'Meteograma · ')+name;}
function error(name,exception){if(name!==region)return;reset();$('meteoInfo').textContent=name+(isRussian()?' · Метеограмма недоступна: ':' · Meteograma indisponível: ')+exception.message;}
function setForecast(name,data){
 region=name;rows=fromHourly(data);active=0;
 $('meteoModalTitle').textContent=(isRussian()?'Метеограмма · ':'Meteograma · ')+name;
 draw('meteoSmallSvg',true);select(0);
 $('meteoInfo').textContent=isRussian()?name+' · ECMWF IFS 0,25° / Open-Meteo · время UTC · нажмите для увеличения':name+' · ECMWF IFS 0,25° via Open-Meteo · horas UTC · clicar para ampliar';
 $('meteoPreview').disabled=false;
}
window.MeteoFoxMeteogram={loading:loading,error:error,setForecast:setForecast};
function init(){
 var preview=$('meteoPreview'),dialog=$('meteoDialog');if(!preview||!dialog)return;
 preview.addEventListener('click',open);$('meteoClose').addEventListener('click',close);
 dialog.addEventListener('click',function(e){if(e.target===dialog)close();});
 $('meteoPrevious').addEventListener('click',function(){select(active-1);});
 $('meteoNext').addEventListener('click',function(){select(active+1);});
 $('meteoTimeSlider').addEventListener('input',function(e){select(Number(e.target.value));});
 document.addEventListener('keydown',function(e){if(!expanded||e.altKey||e.ctrlKey||e.metaKey)return;if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='ArrowLeft'){e.preventDefault();select(active-1);}else if(e.key==='ArrowRight'){e.preventDefault();select(active+1);}});
 loading('Lisboa');
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();