/* MeteoFox VIS / FOG Auto — máscara geográfica dia/noite.
 * Gera apenas uma máscara PNG pequena por mosaico; não lê pixels WMS,
 * não precisa de CORS e não descarrega nenhuma imagem adicional.
 * Convenção: máscara do Fog 0% de dia, 100% de noite e progressiva
 * entre elevação solar +3° e -6°.
 */
(function(){
'use strict';
const PI=Math.PI,RAD=PI/180;
const cache=new Map(),MAX_CACHE=60;
function sun(time){
 const date=new Date(time);
 if(!Number.isFinite(date.getTime()))return null;
 const day=(Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate())-
  Date.UTC(date.getUTCFullYear(),0,0))/86400000;
 const hour=date.getUTCHours()+date.getUTCMinutes()/60+date.getUTCSeconds()/3600;
 const gamma=2*PI/365*(day-1+(hour-12)/24);
 const eq=229.18*(0.000075+0.001868*Math.cos(gamma)-0.032077*Math.sin(gamma)-
  0.014615*Math.cos(2*gamma)-0.040849*Math.sin(2*gamma));
 const dec=0.006918-0.399912*Math.cos(gamma)+0.070257*Math.sin(gamma)-
  0.006758*Math.cos(2*gamma)+0.000907*Math.sin(2*gamma)-
  0.002697*Math.cos(3*gamma)+0.00148*Math.sin(3*gamma);
 return {minutes:hour*60+eq,dec};
}
function elevation(lat,lon,solar){
 const l=lat*RAD,ha=(solar.minutes+4*lon)/4-180;
 const dot=Math.sin(l)*Math.sin(solar.dec)+Math.cos(l)*Math.cos(solar.dec)*Math.cos(ha*RAD);
 return Math.asin(Math.max(-1,Math.min(1,dot)))/RAD;
}
function fogWeight(alt){
 const t=Math.max(0,Math.min(1,(3-alt)/9));
 return t*t*(3-2*t);
}
// Classifica cada mosaico sem descarregar imagens. Margem de 0,5°
// evita remover um produto demasiado perto do terminador.
function tileLighting(time,coords){
 const z=coords?.z,x=coords?.x,y=coords?.y;
 if(!Number.isInteger(z)||!Number.isInteger(x)||!Number.isInteger(y)||
    z<0||z>19||!Number.isFinite(time))return 'mixed';
 const solar=sun(time);if(!solar)return 'mixed';
 let minAlt=Infinity,maxAlt=-Infinity;
 const zoom=2**z;
 for(let j=0;j<=16;j++){
  const lat=Math.atan(Math.sinh(PI*(1-2*(y+j/16)/zoom)))/RAD;
  for(let i=0;i<=16;i++){
   const lon=(x+i/16)/zoom*360-180;
   const alt=elevation(lat,lon,solar);
   minAlt=Math.min(minAlt,alt);maxAlt=Math.max(maxAlt,alt);
  }
 }
 if(minAlt>3.5)return 'day';
 if(maxAlt< -6.5)return 'night';
 return 'mixed';
}
function tileMask(time,coords,dimension=64,kind='fog',opacity=0.8){
 const z=coords?.z,x=coords?.x,y=coords?.y;
 if(!Number.isInteger(z)||!Number.isInteger(x)||!Number.isInteger(y)||
    z<0||z>19||!Number.isFinite(time))return '';
 const a=Math.max(0,Math.min(1,Number(opacity)||0));
 const key=[time,z,x,y,dimension,kind,Math.round(a*1000)].join(':');
 if(cache.has(key))return cache.get(key);
 const solar=sun(time);if(!solar)return '';
 const canvas=document.createElement('canvas');canvas.width=canvas.height=dimension;
 const ctx=canvas.getContext('2d');if(!ctx)return '';
 const im=ctx.createImageData(dimension,dimension);
 const zoom=2**z;
 for(let j=0;j<dimension;j++){
  const wy=(y+(j+.5)/dimension)/zoom;
  const latitude=Math.atan(Math.sinh(PI*(1-2*wy)))/RAD;
  for(let i=0;i<dimension;i++){
   const longitude=(x+(i+.5)/dimension)/zoom*360-180;
   const k=4*(j*dimension+i);
   im.data[k]=im.data[k+1]=im.data[k+2]=0;
   const fog=fogWeight(elevation(latitude,longitude,solar));
   // Exata composição alpha dos dois layers com opacidade global a:
   // Fog: a*fog; GeoColour: a*(1-fog)/(1-a*fog).
   // A máscara do Geo deve usar (1-fog)/(1-a*fog) para que
   // a opacidade total e a proporção das cores sejam constantes.
   const m=kind==='geo'?(1-fog)/Math.max(1e-8,1-a*fog):fog;
   im.data[k+3]=Math.round(255*Math.max(0,Math.min(1,m)));
  }
 }
 ctx.putImageData(im,0,0);
 const url=canvas.toDataURL('image/png');
 cache.set(key,url);
 if(cache.size>MAX_CACHE)cache.delete(cache.keys().next().value);
 return url;
}
function clear(){cache.clear();}
window.MeteoFoxFogMask={tileMask,tileLighting,clear,fogWeight,elevation,sun};
})();