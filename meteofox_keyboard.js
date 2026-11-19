/* MeteoFox — todos os cursores temporais operáveis pelo teclado.
   Apenas altera um cursor quando ele próprio está focado.
   Setas: passo; Home/End: extremos; PageUp/PageDown: três passos.
   Dispara input e change para manter mapas, imagens e metadados sincronizados. */
(function(){
'use strict';
document.addEventListener('keydown',function(event){
 var el=event.target;
 if(!el||el.tagName!=='INPUT'||el.type!=='range'||el.disabled)return;
 if(event.altKey||event.ctrlKey||event.metaKey)return;
 var min=Number(el.min||0),max=Number(el.max||100),step=Number(el.step||1),value=Number(el.value);
 if(!Number.isFinite(step)||step<=0)step=1;
 var next;
 switch(event.key){
  case 'ArrowLeft':case 'ArrowDown':next=value-step;break;
  case 'ArrowRight':case 'ArrowUp':next=value+step;break;
  case 'Home':next=min;break;
  case 'End':next=max;break;
  case 'PageDown':next=value-3*step;break;
  case 'PageUp':next=value+3*step;break;
  default:return;
 }
 event.preventDefault();
 event.stopImmediatePropagation();
 next=Math.max(min,Math.min(max,next));
 next=min+Math.round((next-min)/step)*step;
 next=Math.max(min,Math.min(max,next));
 if(next===value)return;
 el.value=String(next);
 el.dispatchEvent(new Event('input',{bubbles:true}));
 el.dispatchEvent(new Event('change',{bubbles:true}));
},true);
})();