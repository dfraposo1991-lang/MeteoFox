/* MeteoFox · meteograma único ECMWF Lisboa. Dados: previsão ECMWF IFS 0p25, não ilustrativos. */
(function () {
'use strict';
var svgNS='http://www.w3.org/2000/svg', rows=[], run='', active=0, expanded=false, previousFocus=null;
var $=function(id){return document.getElementById(id);};
function node(tag,attrs,value){var el=document.createElementNS(svgNS,tag);Object.keys(attrs||{}).forEach(function(k){el.setAttribute(k,attrs[k]);});if(value!==undefined)el.textContent=value;return el;}
function add(parent,tag,attrs,value){var el=node(tag,attrs,value);parent.appendChild(el);return el;}
function txt(svg,value,x,y,size,color,weight,anchor){return add(svg,'text',{x:x,y:y,'font-family':'Inter,system-ui,sans-serif','font-size':size||13,fill:color||'#e8f1f8','font-weight':weight||500,'text-anchor':anchor||'start'},value);}
function dateOf(row){return new Date(row.valid_utc);}
function dayName(d){return d.toLocaleDateString('pt-PT',{timeZone:'UTC',weekday:'short',day:'numeric',month:'short'});}
function hour(d){return d.toLocaleTimeString('pt-PT',{timeZone:'UTC',hour:'2-digit',hourCycle:'h23'}).slice(0,2)+'h';}
function cloudIcon(cover,rain){if(rain>=0.3&&cover>=45)return '🌧';if(cover>=85)return '☁';if(cover>=55)return '☁';if(cover>=25)return '⛅';return '☀';}
function draw(target,compact){
 var svg=$(target);if(!svg||!rows.length)return;
 svg.replaceChildren();
 var col=42, left=170, top=33, width=left+col*rows.length+10, height=420;
 svg.setAttribute('viewBox','0 0 '+width+' '+height);
 svg.setAttribute('role','img');
 add(svg,'rect',{x:0,y:0,width:width,height:height,rx:10,fill:'#071b2d'});
 var boundaries=[0,33,70,127,275,315,350,385,419];
 boundaries.forEach(function(y){add(svg,'line',{x1:0,x2:width,y1:y,y2:y,stroke:'#28475e','stroke-width':1});});
 for(var i=0;i<=rows.length;i++)add(svg,'line',{x1:left+i*col,x2:left+i*col,y1:33,y2:419,stroke:'#244056','stroke-width':0.8});
 txt(svg,'Hora UTC',12,56,13,'#a8bdce');
 txt(svg,'Nuvens',12,107,16,'#d4eafa',600);
 txt(svg,'Precipitação',12,193,15,'#d4eafa',600);
 txt(svg,'(mm/3 h)',12,212,12,'#9ebbd1');
 txt(svg,'Temperatura (°C)',12,303,14,'#e8f1f8',600);
 txt(svg,'Direção do vento',12,338,13,'#e8f1f8',600);
 txt(svg,'Vento médio (kt)',12,373,13,'#e8f1f8',600);
 txt(svg,'Rajadas (kt)',12,408,14,'#e8f1f8',600);
 var groups=[],key='';
 rows.forEach(function(r,i){var d=dateOf(r),k=r.valid_utc.slice(0,10);if(k!==key){groups.push({start:i,n:1,date:d});key=k;}else groups[groups.length-1].n++;});
 groups.forEach(function(g,j){
  var x=left+g.start*col;
  add(svg,'rect',{x:x,y:0,width:g.n*col,height:33,fill:j%2?'#12324b':'#0e283e',stroke:'#35576e'});
  txt(svg,dayName(g.date),x+g.n*col/2,22,14,'#e6f6ff',700,'middle');
  add(svg,'line',{x1:x,x2:x,y1:33,y2:419,stroke:'#69869c','stroke-width':1.5});
 });
 var rainScale=Math.max(1,Math.ceil(Math.max.apply(null,rows.map(function(r){return Number(r.rain_3h_mm)||0;}))*2)/2);
 for(var j=0;j<=4;j++){
  var y=266-j*124/4, val=rainScale*j/4;
  add(svg,'line',{x1:left,x2:width,y1:y,y2:y,stroke:'#35536c','stroke-dasharray':'3 5'});
  txt(svg,val.toFixed(1),left-8,y+4,11,'#aec8d8',400,'end');
 }
 rows.forEach(function(r,i){
  var x=left+i*col, mid=x+col/2, d=dateOf(r), precip=Math.max(0,Number(r.rain_3h_mm)||0), cover=Math.max(0,Number(r.cloud_percent)||0);
  txt(svg,hour(d),mid,55,13,'#e8f1f8',500,'middle');
  txt(svg,cloudIcon(cover,precip),mid,107,23,'#d3eaf4',500,'middle');
  var bar=Math.max(0,precip/rainScale*124);
  if(precip>0)add(svg,'rect',{x:x+6,y:266-Math.max(2,bar),width:col-12,height:Math.max(2,bar),rx:2,fill:'#3797ec'});
  txt(svg,Math.round(Number(r.temp_c))+'°',mid,303,16,'#ffca72',700,'middle');
  var degrees=Number(r.wind_dir_deg)||0;
  // Seta orientada para onde o vento sopra (180° oposto à direção meteorológica de origem).
  txt(svg,'↑',mid,340,25,'#b9efff',700,'middle').setAttribute('transform','rotate('+((degrees+180)%360)+' '+mid+' 333)');
  txt(svg,String(Math.round(Number(r.wind_kt))),mid,373,15,'#edf8ff',600,'middle');
  txt(svg,String(Math.round(Number(r.gust_kt))),mid,408,15,'#ffd58c',700,'middle');
  if(!compact&&active===i)add(svg,'rect',{x:x+1,y:33,width:col-2,height:385,rx:3,fill:'#51d6e7','fill-opacity':0.11,stroke:'#51d6e7','stroke-width':1.5,'pointer-events':'none'});
  if(!compact){var hit=add(svg,'rect',{x:x,y:33,width:col,height:385,fill:'transparent',style:'cursor:pointer'});hit.addEventListener('click',function(){select(i);});}
 });
}
function select(i){active=Math.max(0,Math.min(rows.length-1,i));draw('meteoLargeSvg',false);if(!$('meteoDetails'))return;var r=rows[active],d=dateOf(r);
 $('meteoDetails').textContent=dayName(d)+' '+hour(d)+' UTC · Chuva '+Number(r.rain_3h_mm).toFixed(2)+' mm/3h · Temperatura '+Number(r.temp_c).toFixed(1)+' °C · Vento '+Number(r.wind_kt).toFixed(0)+' kt · Rajadas '+Number(r.gust_kt).toFixed(0)+' kt · Nuvens '+Math.round(r.cloud_percent)+'%';$('meteoTimeSlider').value=String(active);
}
function open(){if(!rows.length)return;expanded=true;previousFocus=document.activeElement;$('meteoDialog').hidden=false;document.body.classList.add('meteo-dialog-open');select(active);$('meteoClose').focus();}
function close(){if(!expanded)return;expanded=false;$('meteoDialog').hidden=true;document.body.classList.remove('meteo-dialog-open');if(previousFocus)previousFocus.focus();}
function validate(data){
 if(!data||!Array.isArray(data.meteogram_lisboa)||data.meteogram_lisboa.length!==30)throw Error('Faltam os 30 períodos ECMWF de Lisboa');
 var arr=data.meteogram_lisboa;
 arr.forEach(function(r,i){if(r.step_h!==(i+1)*3||!Number.isFinite(Date.parse(r.valid_utc))||!['rain_3h_mm','temp_c','wind_dir_deg','wind_kt','gust_kt','cloud_percent'].every(function(k){return Number.isFinite(Number(r[k]));}))throw Error('Dados meteorológicos incompletos no prazo '+i);});
 return arr;
}
function init(){
 var preview=$('meteoPreview'),dialog=$('meteoDialog');if(!preview||!dialog)return;
 preview.addEventListener('click',open);$('meteoClose').addEventListener('click',close);
 dialog.addEventListener('click',function(e){if(e.target===dialog)close();});
 $('meteoPrevious').addEventListener('click',function(){select(active-1);});
 $('meteoNext').addEventListener('click',function(){select(active+1);});
 $('meteoTimeSlider').addEventListener('input',function(e){select(Number(e.target.value));});
 document.addEventListener('keydown',function(e){if(!expanded)return;if(e.key==='Escape'){e.preventDefault();close();}else if(e.key==='ArrowLeft'){e.preventDefault();select(active-1);}else if(e.key==='ArrowRight'){e.preventDefault();select(active+1);}});
 fetch('./produtos_experimentais/previsao_ecmwf.json?t='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw Error('HTTP '+r.status);return r.json();}).then(function(data){rows=validate(data);run=data.run_utc;draw('meteoSmallSvg',true);select(0);$('meteoInfo').textContent='Lisboa · ECMWF IFS '+data.resolution+' · ciclo '+new Date(run).toLocaleString('pt-PT',{timeZone:'UTC'})+' UTC · selecionar para ampliar';preview.disabled=false;}).catch(function(e){$('meteoInfo').textContent='Meteograma indisponível: '+e.message;preview.disabled=true;});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();