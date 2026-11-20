import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:900}});
const errors=[];
page.on('pageerror',e=>errors.push(String(e)));
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lQAAAABJRU5ErkJggg==','base64');
const respondPNG=r=>r.fulfill({status:200,contentType:'image/png',body:png,headers:{'access-control-allow-origin':'*'}});
let mockCycleUTC='2026-11-20T06:00:00Z';
const expectedUrl=(kind,step)=>'./'+kind+'_'+step+'.png?run='+encodeURIComponent(mockCycleUTC);
const current=Math.floor(Date.now()/600000)*600000;
const frames=Array.from({length:5},(_,i)=>current-(4-i)*600000);
await page.route(/\/(chuva|rajadas)_\d{3}\.png(?:\?.*)?$/,respondPNG);
await page.route('**/meteofox_ecmwf_manifest.json*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({cycle_utc:mockCycleUTC,images:Object.fromEntries(Array.from({length:16},(_,i)=>'chuva_'+String(9+i*3).padStart(3,'0')+'.png').map(k=>[k,'ok']))})}));
await page.route('**/api.rainviewer.com/**',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({host:'https://tilecache.rainviewer.com',radar:{past:frames.map((t,i)=>({time:Math.floor(t/1000),path:'/mock'+i}))}})}));
await page.route('**/raw.githubusercontent.com/**/data/satellite_times.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({layer:'mtg_fd:rgb_geocolour',checked_utc:new Date().toISOString(),times_utc:frames.map(t=>new Date(t).toISOString())})}));
await page.route('**/raw.githubusercontent.com/**/data/aviation.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({metar:{LPPT:{raw:'METAR LPPT 191100Z 27007KT 9999 BKN030 16/12 Q1022'}},taf:{},speci:{},metar_checked_utc:new Date().toISOString()})}));
await page.route(/tilecache\.rainviewer\.com/,respondPNG);
await page.route(/tile\.openstreetmap\.org/,respondPNG);
await page.route(/view\.eumetsat\.int/,respondPNG);

try{
 await page.goto('http://127.0.0.1:8765/index.html',{waitUntil:'domcontentloaded',timeout:45000});
 assert.equal(await page.locator('[data-tab="precipGust"]').innerText(),'▤ Produtos');
 assert.equal(await page.locator('[data-tab="satRadar"]').count(),0);
 await page.locator('[data-tab="precipGust"]').click();
 await page.waitForFunction(()=>document.getElementById('ecmwfRain')?.getAttribute('src')?.includes('chuva_009.png'));
 const first=await page.locator('#ecmwfRain').getAttribute('src');
 const satValueBefore=await page.locator('#visSimSlider').inputValue();
 await page.locator('#ecmwfNext').click();
 const r=await page.locator('#ecmwfRain').getAttribute('src'),w=await page.locator('#ecmwfGust').getAttribute('src');
 assert.equal(first,expectedUrl('chuva','009'));assert.equal(r,expectedUrl('chuva','012'));assert.equal(w,expectedUrl('rajadas','012'));
 assert.equal(await page.locator('#visSimSlider').inputValue(),satValueBefore);
 // Testar os dezasseis prazos atuais (+9 a +54 h).
 for(let i=0;i<16;i++){
  await page.locator('#ecmwfSlider').fill(String(i));
  const step=String(9+i*3).padStart(3,'0');
  assert.equal(await page.locator('#ecmwfRain').getAttribute('src'),expectedUrl('chuva',step));
  assert.equal(await page.locator('#ecmwfGust').getAttribute('src'),expectedUrl('rajadas',step));
 }
 await page.locator('#ecmwfSlider').fill('15');
 assert.equal(await page.locator('#ecmwfRain').getAttribute('src'),expectedUrl('chuva','054'));
 assert.equal(await page.locator('#ecmwfGust').getAttribute('src'),expectedUrl('rajadas','054'));
 // Regressão de cache: a mesma carta de um novo run deve usar URL diferente.
 const priorURL=await page.locator('#ecmwfRain').getAttribute('src');
 mockCycleUTC='2026-11-20T12:00:00Z';
 await page.evaluate(()=>ecmwfLoadCycle());
 assert.equal(await page.locator('#ecmwfRain').getAttribute('src'),expectedUrl('chuva','054'));
 assert.notEqual(await page.locator('#ecmwfRain').getAttribute('src'),priorURL,'Novo run não pode reutilizar URL anterior');
 await page.locator('[data-tab="aerodromes"]').click();
 assert.equal(await page.locator('#aerodromes .metar-table:first-child tbody tr').count(),7);
 assert.equal(await page.locator('#aerodromes .metar-table:nth-child(2) tbody tr').count(),4);
 await page.goto('http://127.0.0.1:8765/mapa.html',{waitUntil:'domcontentloaded',timeout:45000});
 await page.waitForSelector('#satTools button',{timeout:25000});
 assert.equal(await page.locator('#mapLegends').isHidden(),true);
 const viewport=page.viewportSize(),mapBounds=await page.locator('#largeMap').boundingBox(),headerBounds=await page.locator('header').boundingBox();
 assert.ok(mapBounds.y>=headerBounds.y+headerBounds.height-3,'Mapa abaixo do cabeçalho');
 assert.ok(Math.abs(mapBounds.height-(viewport.height-headerBounds.height))<8,'Mapa ocupa altura disponível');
 assert.ok(Math.abs(mapBounds.width-viewport.width)<8,'Mapa ocupa largura do ecrã');
 for(const id of ['all','mainland','islands','madeira','refresh','showLegends']){
  assert.equal(await page.locator('header #'+id).count(),1,id+' deve estar no cabeçalho');
 }
 assert.equal(await page.locator('.map-overlays #satTools').count(),1);
 const panelBG=await page.locator('.map-overlays').evaluate(el=>getComputedStyle(el).backgroundColor);
 assert.ok(panelBG.startsWith('rgba(22, 53, 78, 0.22)'), 'Fundo transparente: '+panelBG);
 assert.equal(await page.locator('#count').evaluate(el=>getComputedStyle(el.parentElement).clip),'rect(0px, 0px, 0px, 0px)','Contador fora do ecrã');
 const ctrlBounds=await page.locator('.map-overlays').boundingBox();
 assert.ok(ctrlBounds.y>=mapBounds.y&&ctrlBounds.y<mapBounds.y+mapBounds.height,'Controlos sobre o mapa');
 await page.locator('#showLegends').click();
 assert.equal(await page.locator('#mapLegends').isVisible(),true);
 assert.equal(await page.locator('#showLegends').getAttribute('aria-expanded'),'true');
 await page.locator('#closeLegends').click();
 assert.equal(await page.locator('#mapLegends').isHidden(),true);
 assert.equal(await page.locator('.metar-table:first-child tbody tr').count(),7);
 assert.equal(await page.locator('.metar-table:nth-child(2) tbody tr').count(),4);
 const togglePanel=page.locator('#toggleMapControls');
 const controlPanel=page.locator('#mapControlsPanel');
 assert.equal(await togglePanel.count(),1,'O botão translúcido deve existir');
 assert.equal(await togglePanel.getAttribute('aria-expanded'),'true');
 await togglePanel.click();
 assert.equal(await togglePanel.getAttribute('aria-expanded'),'false');
 assert.equal(await controlPanel.isHidden(),true,'Painel deve recolher sem esconder botão');
 assert.equal(await togglePanel.isVisible(),true);
 assert.equal((await togglePanel.innerText()).trim(),'+','Quadrado deve mostrar apenas o símbolo +');
 assert.equal(await page.locator('#mapMiniTimeline').isHidden(),true,'No computador as setas flutuantes ficam ocultas');
 await togglePanel.click();
 assert.equal(await controlPanel.isVisible(),true,'Painel deve abrir novamente');
 const opacityButton=page.getByRole('button',{name:/Opacidade/});
 assert.equal(await opacityButton.count(),1,'Botão Opacidade claramente acessível');
 await opacityButton.click();
 assert.equal(await page.locator('.mf-opacity-controls').isHidden(),true);
 await opacityButton.click();
 assert.equal(await page.locator('.mf-opacity-controls').isVisible(),true);
 const satOpacity=page.getByRole('slider',{name:'Opacidade satélite'});
 const radarOpacity=page.getByRole('slider',{name:'Opacidade radar'});
 assert.equal(await satOpacity.count(),1);
 assert.equal(await radarOpacity.count(),1);
 await satOpacity.fill('90');
 await radarOpacity.fill('70');
 assert.equal(await satOpacity.inputValue(),'90');
 assert.equal(await radarOpacity.inputValue(),'70');
 const opacityValues=await page.evaluate(()=>({sat:sat.satOpacity,radar:sat.radarOpacity}));
 assert.equal(opacityValues.sat,.9);
 assert.equal(opacityValues.radar,.7);
 const speedControl=page.getByRole('button',{name:/Velocidade da animação/});
 assert.equal(await speedControl.count(),1,'Controlo de velocidade deve existir no mapa');
 assert.equal(await speedControl.innerText(),'Velocidade: 1×');
 await speedControl.click();
 assert.equal(await speedControl.innerText(),'Velocidade: 1.5×');
 await speedControl.click();
 assert.equal(await speedControl.innerText(),'Velocidade: 2×');
 // As restantes velocidades também devem estar disponíveis.
 await speedControl.click();
 assert.equal(await speedControl.innerText(),'Velocidade: 3×');
 await speedControl.click();
 assert.equal(await speedControl.innerText(),'Velocidade: 0.5×');
 await speedControl.click();
 assert.equal(await speedControl.innerText(),'Velocidade: 1×');
 await page.getByRole('button',{name:/Satélite: desligado/}).click();
 await page.getByRole('button',{name:/Radar: desligado/}).click();
 await page.waitForFunction(()=>{const slider=document.querySelector('#satTools input[aria-label="Navegação temporal UTC"]');return slider&&!slider.disabled&&Number(slider.max)>=1;},{timeout:15000});
 // Esperar a conclusão de ambas as consultas e da transição inicial;
 // caso contrário refreshTimeline pode repor o último prazo durante o teste.
 await page.waitForFunction(()=>sat.satKnown && sat.radarFrames.length>0 && !sat.transition,{timeout:15000});
 await page.waitForTimeout(400);
 // Desktop: navegar com setas do teclado, sem mostrar controlos flutuantes.
 await togglePanel.click();
 assert.equal(await page.locator('#mapMiniTimeline').isHidden(),true);
 const miniStarting=await page.evaluate(()=>sat.index);
 await togglePanel.focus();
 await page.keyboard.press('ArrowLeft');
 assert.equal(await page.evaluate(()=>sat.index),Math.max(0,miniStarting-1),'Teclado deve recuar com painel recolhido');
 await page.keyboard.press('ArrowRight');
 assert.equal(await page.evaluate(()=>sat.index),miniStarting,'Teclado deve avançar com painel recolhido');
 await togglePanel.click();
 const mapTimeline=page.locator('#satTools input[aria-label="Navegação temporal UTC"]');
 await mapTimeline.fill('0');
 await page.locator('#showLegends').focus();
 await page.keyboard.press('Home');
 const keyboardState=await page.evaluate(()=>{
  const range=document.querySelector('#satTools input[aria-label="Navegação temporal UTC"]');
  const p=document.querySelector('#satTools');
  return {value:range.value,max:range.max,disabled:range.disabled,
    rangeVisible:getComputedStyle(range).display,hostVisible:getComputedStyle(p).display,
    focused:document.activeElement?.id,scriptPresent:!!document.querySelector('script[src="./meteofox_keyboard.js"]')};
 });
 assert.equal(await mapTimeline.inputValue(),'0','Mapa Home deve selecionar a primeira imagem: '+JSON.stringify(keyboardState));
 await page.keyboard.press('ArrowRight');
 assert.equal(await mapTimeline.inputValue(),'1','Mapa com radar/Meteosat deve navegar pelo teclado sem cursor focado');

 // Regressão anti-piscar: a imagem antiga nunca perde opacidade
 // durante o carregamento da nova; só sai após o fade do novo container.
 await page.waitForTimeout(550);
 const fadeCheck=await page.evaluate(async()=>{
  const previous=sat.satLayer;
  if(!previous||!sat.timeline.length)return {available:false};
  const prior=previous.getContainer();
  const next=sat.index===0?Math.min(1,sat.timeline.length-1):0;
  const swap=sat.select(next);
  const oldStillOpaque=prior.style.opacity!=='0'&&getComputedStyle(prior).opacity==='1';
  const ok=await swap;
  const current=sat.satLayer;
  const newContainer=current?.getContainer();
  const oldStillMounted=sat.map.hasLayer(previous);
  await new Promise(resolve=>setTimeout(resolve,410));
  return {available:true,ok,oldStillOpaque,oldStillMounted,
   newOpaque:getComputedStyle(newContainer).opacity==='1',
   oldRemoved:!sat.map.hasLayer(previous)};
 });
 assert.equal(fadeCheck.available,true,'Camada Meteosat indisponível para teste');
 assert.equal(fadeCheck.ok,true,'Troca de fotograma falhou: '+JSON.stringify(fadeCheck));
 assert.equal(fadeCheck.oldStillOpaque,true,'A imagem anterior não pode esbater durante a troca');
 assert.equal(fadeCheck.oldStillMounted,true,'Não retirar a imagem antes de revelar a nova');
 assert.equal(fadeCheck.newOpaque,true,'Imagem nova deve terminar totalmente opaca');
 assert.equal(fadeCheck.oldRemoved,true,'Imagem antiga deve sair após a transição');
 // Scroll rápido de zoom: evita excesso de atualizações e mantém as layers ativas.
 const beforeZoom=await page.evaluate(()=>appMap.getZoom());
 await page.locator('#largeMap').hover();
 for(let n=0;n<5;n++)await page.mouse.wheel(0,-210);
 await page.waitForTimeout(1300);
 const afterZoom=await page.evaluate(()=>({
  zoom:appMap.getZoom(),satOn:sat.satOn,radarOn:sat.radarOn,
  satVisible:!!sat.satLayer&&appMap.hasLayer(sat.satLayer),
  radarVisible:!!sat.radarLayer&&appMap.hasLayer(sat.radarLayer),
  buffer:sat.satLayer?.options.keepBuffer,
  zoomUpdate:sat.satLayer?.options.updateWhenZooming
 }));
 assert.ok(afterZoom.zoom>=beforeZoom,'Zoom após scroll deve responder');
 assert.equal(afterZoom.satOn,true);
 assert.equal(afterZoom.radarOn,true);
 assert.equal(afterZoom.buffer,0,'Preservar configuração anterior de mosaicos');
 assert.equal(afterZoom.zoomUpdate,true,'Atualizar imagens durante o zoom');
 // Preload de apenas um instante: não acumular mosaicos escondidos.
 await page.waitForTimeout(900);
 const prefetched=await page.evaluate(()=>({
  count:sat.prefetchSat?1:0,
  time:sat.prefetchSat?.time??null,
  matched:sat.prefetchSat? sat.nearestSat(sat.timeline[(sat.index+1)%sat.timeline.length])===sat.prefetchSat.time : true,
  currentStillVisible:!!sat.satLayer&&appMap.hasLayer(sat.satLayer)
 }));
 assert.ok(prefetched.count<=1,'Pré-carregamento limitado a um fotograma');
 assert.equal(prefetched.matched,true,'Pré-carregar apenas instante seguinte');
 assert.equal(prefetched.currentStillVisible,true,'Não ocultar o fotograma atual');
 const endText=await page.locator('#satTools .sat-clock').last().innerText();
 assert.ok(endText.includes('Z'),endText);
 console.log('PASS desktop: Produtos, 16 passos +9..+54 chuva+rajadas, independência VIS, METAR, mapa radar/Meteosat');
 // Telemóvel: setas visíveis só quando o painel estiver recolhido.
 await page.setViewportSize({width:390,height:844});
 await togglePanel.click();
 assert.equal(await page.locator('#mapMiniTimeline').isVisible(),true,'Setas visíveis em telemóvel');
 await page.waitForFunction(()=>!document.querySelector('#mapMiniForward').disabled);
 const mobileStart=await page.evaluate(()=>sat.index);
 await page.locator('#mapMiniBack').click();
 assert.equal(await page.evaluate(()=>sat.index),Math.max(0,mobileStart-1));
 await page.locator('#mapMiniForward').click();
 assert.equal(await page.evaluate(()=>sat.index),mobileStart);
 await togglePanel.click();
 assert.equal(await page.locator('#mapMiniTimeline').isHidden(),true,'Setas desaparecem ao expandir painel');
 await page.goto('http://127.0.0.1:8765/index.html',{waitUntil:'domcontentloaded',timeout:45000});
 const mobile=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,pageWidth:document.documentElement.scrollWidth}));
 assert.ok(mobile.pageWidth<=mobile.viewport+3,'Overflow horizontal na página principal: '+JSON.stringify(mobile));
 console.log('PASS mobile 390px: página sem overflow horizontal');
 assert.deepEqual(errors,[],'Erros JavaScript inesperados');
}finally{await browser.close();}
