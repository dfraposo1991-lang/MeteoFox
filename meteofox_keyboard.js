/* MeteoFox — controlos temporais pelo teclado.
 * Se um cursor estiver focado, controla esse cursor.
 * Caso contrário, controla o cursor da visualização ativa, sem obrigar a clicar nele.
 * Exclui escrita, selects e atalhos de sistema. Captura evita ações duplicadas.
 */
(function(){
'use strict';
function visible(el){
 if(!el||el.disabled||el.closest('[hidden]'))return false;
 for(let p=el;p&&p.nodeType===1;p=p.parentElement){
  const style=getComputedStyle(p);
  if(style.display==='none'||style.visibility==='hidden')return false;
 }
 return true;
}
function choose(){
 const focused=document.activeElement;
 if(focused?.matches?.('input[type="range"]')&&visible(focused))return focused;
 const modal=document.getElementById('meteoDialog');
 if(modal&&!modal.hidden)return document.getElementById('meteoTimeSlider');
 const panel=document.querySelector('.section.active');
 if(panel){
  // Cada separador controla apenas o seu próprio produto.
  const selected=panel.querySelector('input[type="range"]:not(:disabled)');
  if(visible(selected))return selected;
 }
 const skew=document.getElementById('skewSlider');
 if(visible(skew))return skew;
 const map=document.querySelector('#satTools input[aria-label="Navegação temporal UTC"]');
 if(visible(map))return map;
 return null;
}
document.addEventListener('keydown',function(e){
 if(e.altKey||e.ctrlKey||e.metaKey||e.isComposing)return;
 const focus=document.activeElement;
 if(focus?.isContentEditable||focus?.matches?.('textarea,select,input:not([type="range"])'))return;
 if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))return;
 const el=choose();
 if(!visible(el))return;
 const min=Number(el.min||0),max=Number(el.max||100);
 let step=Number(el.step||1);
 if(!Number.isFinite(step)||step<=0)step=1;
 const current=Number(el.value), n=Number.isFinite(current)?current:min;
 let next=n;
 if(e.key==='ArrowLeft'||e.key==='ArrowDown')next=n-step;
 if(e.key==='ArrowRight'||e.key==='ArrowUp')next=n+step;
 if(e.key==='PageDown')next=n-3*step;
 if(e.key==='PageUp')next=n+3*step;
 if(e.key==='Home')next=min;
 if(e.key==='End')next=max;
 e.preventDefault();
 e.stopImmediatePropagation();
 next=Math.max(min,Math.min(max,min+Math.round((next-min)/step)*step));
 if(next===n)return;
 el.value=String(next);
 el.dispatchEvent(new Event('input',{bubbles:true}));
 el.dispatchEvent(new Event('change',{bubbles:true}));
},true);
})();