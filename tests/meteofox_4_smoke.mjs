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
await page.route('**/raw.githubusercontent.com/**/data/satellite_fog_status.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({ready:true,checked_utc:new Date().toISOString(),geo_layer:'mtg_fd:rgb_geocolour',fog_layer:'mtg_fd:rgb_fog',matching_time_utc:new Date().toISOString()})}));
await page.route('**/raw.githubusercontent.com/**/data/satellite_times.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({layer:'mtg_fd:rgb_geocolour',checked_utc:new Date().toISOString(),times_utc:frames.map(t=>new Date(t).toISOString())})}));
await page.route('**/raw.githubusercontent.com/**/data/aviation.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({metar:{LPPT:{raw:'METAR LPPT 191100Z 27007KT 9999 BKN030 16/12 Q1022'}},taf:{},speci:{},metar_checked_utc:new Date().toISOString()})}));
await page.route('**/raw.githubusercontent.com/**/data/aviation_valencia.json*',r=>r.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({
 checked_utc:new Date().toISOString(),source:'NOAA',metar:{LEVC:{raw:'METAR LEVC 201900Z 28012G20KT 9999 FEW030 18/10 Q1018',utc:new Date().toISOString()}},
 taf:{LEVC:{raw:'TAF LEVC 201700Z 2018/2118 29010KT CAVOK TX23/2112Z TN11/2106Z TEMPO 2021/2101 4000 SHRA BKN020',utc:new Date().toISOString()}},speci:{}
})}));
const hourlyTimes=Array.from({length:186},(_,i)=>new Date(Math.floor(Date.now()/3600000)*3600000+(i-8)*3600000).toISOString().slice(0,16));
const fakeHours={time:hourlyTimes,temperature_2m:hourlyTimes.map(()=>18),
 relative_humidity_2m:hourlyTimes.map(()=>65),apparent_temperature:hourlyTimes.map(()=>19),
 precipitation:hourlyTimes.map(()=>0.2),precipitation_probability:hourlyTimes.map(()=>20),
 wind_speed_10m:hourlyTimes.map(()=>28),wind_direction_10m:hourlyTimes.map(()=>280),
 wind_gusts_10m:hourlyTimes.map(()=>45),pressure_msl:hourlyTimes.map(()=>1018),
 dew_point_2m:hourlyTimes.map(()=>10),cloud_cover:hourlyTimes.map(()=>45),
 weather_code:hourlyTimes.map(()=>2)};
const fakeDaily={time:Array.from({length:7},(_,i)=>new Date(Date.now()+i*86400000).toISOString().slice(0,10)),
 temperature_2m_max:Array(7).fill(20),temperature_2m_min:Array(7).fill(13),
 precipitation_sum:Array(7).fill(1.2),precipitation_probability_max:Array(7).fill(30),
 uv_index_max:Array(7).fill(2),weather_code:Array(7).fill(2)};
await page.route('**/api.open-meteo.com/v1/forecast?*',route=>{
 const u=new URL(route.request().url());
 if(u.searchParams.get('latitude')!=='39.4699'||u.searchParams.get('wind_speed_unit')!=='kmh')return route.continue();
 route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({
 latitude:39.4699,longitude:-0.3763,utc_offset_seconds:0,
 current:{time:hourlyTimes[8],temperature_2m:18,apparent_temperature:19,
 relative_humidity_2m:65,precipitation:0.2,wind_speed_10m:28,wind_gusts_10m:45},
 hourly:fakeHours,daily:fakeDaily})});
});
await page.route(/tilecache\.rainviewer\.com/,respondPNG);
await page.route(/tile\.openstreetmap\.org/,respondPNG);
await page.route(/view\.eumetsat\.int/,respondPNG);

try{
 await page.goto('http://127.0.0.1:8765/index.html',{waitUntil:'domcontentloaded',timeout:45000});
 assert.equal(await page.locator('#place option[value="Valência"]').count(),1,'Valência deve existir na lista da Síntese');
 await page.locator('#place').selectOption('Valência');
 await page.waitForFunction(()=>document.querySelector('#wind')?.textContent?.includes('км/ч'),{timeout:15000});
 assert.ok((await page.locator('#placeTitle').innerText()).includes('Валенсия'));
 assert.ok((await page.locator('#summary').innerText()).includes('км/ч'));
 assert.ok((await page.locator('#gust').innerText()).includes('км/ч'));
 assert.ok((await page.locator('#hours').innerText()).includes('км/ч'));
 assert.ok((await page.locator('#meteoLargeSvg').textContent()).includes('км/ч'));
 assert.equal(await page.locator('#foxVerifiedButton').isVisible(),true,'Fox Verified deve existir também para Valência');
 await page.locator('#place').selectOption('Lisboa');
 await page.waitForFunction(()=>document.querySelector('#placeTitle')?.textContent?.includes('Lisboa'),{timeout:15000});
 assert.equal(await page.locator('#overview .metric .k').first().innerText(),'Temperatura','Lisboa mantém português');
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
 // Os TAF formam linhas apenas nas mudanças, sem partir palavras ou grupos.
 const tafSpec=await page.evaluate(()=>{
  const short='TAF LPPT 201200Z 2012/2112 25008KT CAVOK BECMG 2015/2017 27012KT TEMPO 2018/2022 4000 SHRA BKN018';
  const long='TAF LPPR 201200Z 2012/2112 25008KT CAVOK PROB30 TEMPO 2018/2022 3000 TSRA BKN010CB FM210600 28015G25KT 9999 SCT030';
  const formatted=[formatTAF(short),formatTAF(long)];
  const sandbox=document.createElement('div');sandbox.className='aviation-results';
  sandbox.style.cssText='position:absolute;left:-3000px;top:0;width:1200px';
  sandbox.innerHTML=[short,long].map((raw,i)=>'<article class="aviation-card"><div class="aviation-bulletins">'+aviationReport('TAF',{raw,utc:new Date().toISOString()},'NOAA')+'</div></article>').join('');
  document.body.append(sandbox);
  const widths=[...sandbox.querySelectorAll('.aviation-card')].map(el=>el.getBoundingClientRect().width);
  const subWidths=[...sandbox.querySelectorAll('.aviation-report')].map(el=>el.getBoundingClientRect().width);
  const whiteSpace=getComputedStyle(sandbox.querySelector('pre.taf-formatted')).whiteSpace;
  sandbox.remove();
  return {formatted,widths,subWidths,whiteSpace};
 });
 assert.ok(tafSpec.formatted[0].includes('\nBECMG '),'BECMG inicia linha');
 assert.ok(tafSpec.formatted[0].includes('\nTEMPO '),'TEMPO inicia linha');
 assert.ok(tafSpec.formatted[1].includes('\nPROB30 TEMPO '),'PROB30 TEMPO permanece junto');
 assert.ok(tafSpec.formatted[1].includes('\nFM210600 '),'FM inicia linha');
 assert.equal(tafSpec.whiteSpace,'pre','A linha não pode partir a meio');
 assert.ok(tafSpec.widths[0]<tafSpec.widths[1],'Cada cartão ajusta à largura do TAF: '+JSON.stringify(tafSpec.widths));
 assert.ok(tafSpec.subWidths[0]<tafSpec.subWidths[1],'Caixas individuais seguem o comprimento do boletim');
 // Mesma estação: o bloco METAR deve ser mais curto que o TAF e
 // nem o cartão exterior nem o <pre> podem impor largura uniforme.
 const pairLayout=await page.evaluate(()=>{
  const metar='METAR LPBJ 201800Z 19005KT 9999 FEW020 16/10 Q1017';
  const taf='TAF LPBJ 201701Z 2018/2118 15005KT 9999 FEW030 BECMG 2110/2112 18012KT SCT015 BKN025 TEMPO 2112/2118 20015G25KT TEMPO 2116/2118 3000 RADZ BR SCT008 BKN014';
  const sandbox=document.createElement('div');
  sandbox.className='aviation-results';
  sandbox.style.cssText='position:absolute;left:-3000px;top:0;width:1200px';
  sandbox.innerHTML='<article class="aviation-card"><div class="aviation-bulletins">'+
   aviationReport('METAR',{raw:metar,utc:new Date().toISOString()},'OGIMET')+
   aviationReport('TAF',{raw:taf,utc:new Date().toISOString()},'NOAA')+'</div></article>';
  document.body.append(sandbox);
  const sections=[...sandbox.querySelectorAll('.aviation-report')];
  const out={widths:sections.map(x=>Math.round(x.getBoundingClientRect().width)),
   preScrolls:sections.map(x=>x.querySelector('pre').scrollWidth),
   contents:[...sections].map(x=>x.querySelector('pre').innerText),
   cardWidth:Math.round(sandbox.querySelector('.aviation-card').getBoundingClientRect().width)};
  sandbox.remove();return out;
 });
 console.log('TAF/METAR REALISTIC WIDTHS',JSON.stringify(pairLayout));
 assert.ok(pairLayout.widths[0]>pairLayout.widths[1],'A caixa METAR deve seguir a linha mais longa, mesmo que o TAF tenha mais texto: '+JSON.stringify(pairLayout.widths));
 assert.ok(pairLayout.widths[0]!==pairLayout.widths[1],'METAR e TAF não podem ser obrigados a ter largura idêntica');
 assert.ok(pairLayout.cardWidth>=Math.max(...pairLayout.widths),'Cartão exterior tem de comportar o boletim mais largo');
 assert.ok(pairLayout.contents[1].includes('\nBECMG ')&&pairLayout.contents[1].includes('\nTEMPO '),'TAF preserva cabeçalhos de grupos');


 // Regressão: popup do MAPA embutido em Aeródromos (não o mapa geral).
 const embeddedPopup=await page.evaluate(()=>{
  const a=AVIATION_AIRPORTS.find(a=>a.id==='LPPR');
  const metar='METAR LPPR 201900Z 14009KT 8000 -RA FEW018CB SCT020 BKN030 14/13 Q1018 RERA=';
  const taf='TAF LPPR 201700Z 2018/2118 15008KT 9999 SCT015 PROB40 TEMPO 2018/2022 4000 SHRA BKN013 FEW020CB BECMG 2022/2024 17015KT SCT006 BKN012 TEMPO 2100/2116 17018G30KT 3000 RADZ BR SCT002 BKN004 BECMG 2116/2118 27015KT SCT020';
  const html=obsAviationPopup(a,{metar:{LPPR:{raw:metar,utc:new Date().toISOString()}},taf:{LPPR:{raw:taf,utc:new Date().toISOString()}},speci:{}});
  const probe=document.createElement('div');probe.className='obs-popup';
  probe.style.cssText='position:absolute;left:-4000px;top:0';
  const root=document.createElement('div');root.className='leaflet-popup';
  const wrapper=document.createElement('div');wrapper.className='leaflet-popup-content-wrapper';
  const content=document.createElement('div');content.className='leaflet-popup-content';
  probe.innerHTML=html.replace(/^<div class="obs-popup">/,'').replace(/<\/div>$/,'');
  content.append(probe);wrapper.append(content);root.append(wrapper);document.body.append(root);
  const sections=[...probe.querySelectorAll('.obs-report')];
  const result={taf:sections[1].querySelector('pre').innerText,
   widths:sections.map(x=>Math.round(x.getBoundingClientRect().width)),
   popupWidth:Math.round(probe.getBoundingClientRect().width),
   whiteSpace:getComputedStyle(sections[1].querySelector('pre')).whiteSpace,
   maxHeight:getComputedStyle(sections[1].querySelector('pre')).maxHeight,
   scrollWidth:sections[1].querySelector('pre').scrollWidth,
   clientWidth:sections[1].querySelector('pre').clientWidth};
  root.remove();return result;
 });
 console.log('POPUP EMBUTIDO AERODROMOS',JSON.stringify(embeddedPopup));
 assert.ok(embeddedPopup.taf.includes('\nBECMG '),'Popup embutido inicia BECMG em linha nova');
 assert.ok(embeddedPopup.taf.includes('\nPROB40 TEMPO '),'PROB40 TEMPO no mesmo grupo');
 assert.ok(embeddedPopup.taf.includes('\nTEMPO '),'TEMPO autónomo em linha nova');
 assert.equal(embeddedPopup.whiteSpace,'pre','TAF popup não deve quebrar linhas');
 assert.equal(embeddedPopup.maxHeight,'none','TAF popup deve crescer em altura');
 assert.ok(embeddedPopup.widths[0]!==embeddedPopup.widths[1],'METAR e TAF devem ter caixas independentes');
 assert.ok(embeddedPopup.popupWidth>340,'Largura do popup não limitada a 340px');
 assert.equal(await page.locator('#aerodromes .metar-table:first-child tbody tr').count(),7);
 assert.equal(await page.locator('#aerodromes .metar-table:nth-child(2) tbody tr').count(),4);
 await page.goto('http://127.0.0.1:8765/mapa.html',{waitUntil:'domcontentloaded',timeout:45000});
 await page.waitForSelector('#satTools button',{timeout:25000});
 await page.waitForFunction(()=>data?.metar?.LEVC?.raw&&data?.taf?.LEVC?.raw,{timeout:20000});
 assert.equal(await page.locator('header #valencia').count(),1,'Atalho Valência no mapa');
 const reports=await page.evaluate(()=>{
  const find=(lat)=>{let html=null;markers.eachLayer(layer=>{
   if(Math.abs(layer.getLatLng().lat-lat)<.0001){
    const popup=layer.getPopup();const cb=popup.getContent();html=typeof cb==='function'?cb():cb;
   }
  });return html;};
  return {levc:find(39.4893),lisboa:find(38.781)};
 });
 assert.ok(reports.levc?.includes('Аэропорт Валенсии'),'LEVC em russo');
 assert.ok(reports.levc?.includes('Ветер'),'LEVC descodifica vento em russo');
 assert.ok(reports.levc?.includes('Период прогноза'),'LEVC descodifica TAF');
 assert.ok(reports.levc?.includes('Прогноз максимальной температуры'),'LEVC descodifica temperatura maxima TAF');
 assert.ok(!reports.levc?.includes('28012G20KT'),'LEVC não apresenta METAR bruto');
 assert.ok(reports.lisboa?.includes('27007KT'),'Lisboa conserva boletim original');
 const popupLayout=await page.evaluate(()=>{
  const sample='TAF LPPT 201200Z 2012/2112 25008KT CAVOK BECMG 2015/2017 27012KT TEMPO 2018/2022 4000 SHRA BKN018';
  const test=formatOriginalTAF(sample);
  const probe=document.createElement('div');probe.className='popup';
  probe.style.cssText='position:absolute;left:-5000px;top:0';
  probe.innerHTML=reportBlock('TAF',{raw:sample,utc:new Date().toISOString()});
  document.body.append(probe);
  const popupRect=probe.getBoundingClientRect();
  const block=probe.querySelector('.aviation-map-report');
  const pre=probe.querySelector('pre');
  const result={test,popupWidth:popupRect.width,blockWidth:block.getBoundingClientRect().width,
    nowrap:getComputedStyle(pre).whiteSpace,maxHeight:getComputedStyle(pre).maxHeight};
  probe.remove();
  return result;
 });
 assert.ok(popupLayout.test.includes('\nBECMG ')&&popupLayout.test.includes('\nTEMPO '),'Mapa principal preserva regras TAF');
 assert.equal(popupLayout.nowrap,'pre','TAF mapa não quebra linhas automaticamente');
 assert.equal(popupLayout.maxHeight,'none','Sem cortes verticais no TAF');
 assert.ok(popupLayout.popupWidth<680,'Popup curta não ocupa largura fixa 680px: '+JSON.stringify(popupLayout));
 console.log('MAP POPUP DIMENSIONS',JSON.stringify(popupLayout));

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
 // Modo VIS / FOG Auto com máscara dia/noite: mantém GeoColour como fallback.
 const solarMask=await page.evaluate(()=>{
  const mask=window.MeteoFoxFogMask;
  const noon=mask.sun(Date.parse('2026-06-21T12:00:00Z'));
  const night=mask.sun(Date.parse('2026-06-21T00:00:00Z'));
  return {loaded:!!mask,
   daytime:mask.fogWeight(mask.elevation(39,-9,noon)),
   nighttime:mask.fogWeight(mask.elevation(39,-9,night)),
   png:mask.tileMask(Date.parse('2026-06-21T00:00:00Z'),{z:6,x:30,y:24}).startsWith('data:image/png;base64,')};
 });
 assert.equal(solarMask.loaded,true,'Módulo de máscara solar disponível');
 assert.equal(solarMask.daytime,0,'Fog completamente oculto durante o dia');
 assert.equal(solarMask.nighttime,1,'Fog totalmente visível durante a noite');
 assert.equal(solarMask.png,true,'Máscara por mosaico renderizada');
 const blendQuality=await page.evaluate(async()=>{
  const M=window.MeteoFoxFogMask,a=.8,t=Date.parse('2026-11-20T17:00:00Z'),coords={z:6,x:30,y:24};
  const read=async kind=>{
   const im=new Image();im.src=M.tileMask(t,coords,64,kind,a);await im.decode();
   const c=document.createElement('canvas');c.width=c.height=64;
   const ctx=c.getContext('2d');ctx.drawImage(im,0,0);
   return ctx.getImageData(0,0,64,64).data;
  };
  const f=await read('fog'),g=await read('geo');
  let err=0,mixed=0;
  for(let i=3;i<f.length;i+=4){
   const x=f[i]/255,y=g[i]/255;
   err=Math.max(err,Math.abs(a*x+a*y*(1-a*x)-a));
   if(x>.01&&x<.99)mixed++;
  }
  return {err,mixed};
 });
 assert.ok(blendQuality.err<.005,'Mistura deve conservar opacidade com máscara complementar: '+JSON.stringify(blendQuality));
 const selective=await page.evaluate(()=>{
  const M=window.MeteoFoxFogMask,coord=L.point(30,24);coord.z=6;
  const day=Date.parse('2026-11-20T12:00:00Z'),night=Date.parse('2026-11-20T22:00:00Z');
  const orig=sat.satMode, wmsMethod=L.TileLayer.WMS.prototype.getTileUrl;
  // Espiar a chamada original evita adicionar camadas só para testar
  // se a seleção por mosaico efetua ou evita uma consulta WMS.
  L.TileLayer.WMS.prototype.getTileUrl=function(){return 'https://view.eumetsat.int/qa-wms-stub'};
  sat.satMode='auto';
  try{
   return {day:M.tileLighting(day,coord),night:M.tileLighting(night,coord),
    dayGeo:sat.createSatLayer(day).getTileUrl(coord),
    dayFog:sat.createFogOverlay(day).getTileUrl(coord),
    nightGeo:sat.createSatLayer(night).getTileUrl(coord),
    nightFog:sat.createFogOverlay(night).getTileUrl(coord)};
  }finally{
   sat.satMode=orig;
   L.TileLayer.WMS.prototype.getTileUrl=wmsMethod;
  }
 });
 assert.equal(selective.day,'day','Mosaico português de dia');
 assert.equal(selective.night,'night','Mosaico português à noite');
 assert.ok(selective.dayGeo.includes('view.eumetsat.int'),'GeoColour deve ser pedido de dia');
 assert.ok(selective.dayFog.startsWith('data:image/svg+xml'),'Fog desnecessário não deve pedir WMS de dia');
 assert.ok(selective.nightGeo.startsWith('data:image/svg+xml'),'GeoColour oculto não deve pedir WMS à noite');
 assert.ok(selective.nightFog.includes('view.eumetsat.int'),'Fog deve ser pedido à noite');


 const modes=await page.evaluate(async()=>{
  const initial=sat.satMode;
  await sat.cycleSatMode();
  const fog=sat.satMode;
  await sat.cycleSatMode();
  const auto=sat.satMode;
  const ready=await sat.select(sat.index);
  const fogLayer=sat.fogLayer;
  const fogRendered=!!fogLayer&&sat.map.hasLayer(fogLayer);
  const fogWms=fogLayer?.wmsParams?.layers;
  const geoUTC=sat.satLayer?.wmsParams?.time;
  const fogUTC=fogLayer?.wmsParams?.time;
  const maskUTC=sat.fogRenderedTime;
  const geoBaseUTC=sat.satRenderedTime;
  const tileMasks=fogLayer?.getContainer?.()?.querySelectorAll('img[style*="mask-image"]').length||0;
  await sat.cycleSatMode();
  const restored=sat.satMode;
  return {initial,fog,auto,ready,fogRendered,fogWms,tileMasks,geoUTC,fogUTC,maskUTC,geoBaseUTC,restored,geoLayer:sat.satLayer?.wmsParams?.layers};
 });
 assert.deepEqual([modes.initial,modes.fog,modes.auto,modes.restored],['geo','fog','auto','geo'],'Sequência de modos deve preservar fallback');
 assert.equal(modes.ready,true,'Fotograma experimental VIS/FOG Auto deve ficar preparado');
 assert.equal(modes.fogRendered,true,'Modo híbrido deve montar camada MTG Fog');
 assert.equal(modes.fogWms,'mtg_fd:rgb_fog','Camada Fog verificada em WMS');
 assert.equal(modes.geoUTC,modes.fogUTC,'GeoColour e Fog têm de pedir o MESMO instante UTC ao WMS');
 assert.equal(Date.parse(modes.geoUTC),modes.geoBaseUTC,'Hora UTC pedida deve coincidir com a referência GeoColour');
 assert.equal(modes.maskUTC,modes.geoBaseUTC,'Máscara solar tem de usar o mesmo instante UTC');
 assert.ok(modes.tileMasks>=1,'Máscara solar aplicada pelo menos a um mosaico Fog');
 const dualMasks=await page.evaluate(async()=>{
  await sat.cycleSatMode(); // Geo -> Fog
  await sat.cycleSatMode(); // Fog -> Auto
  const ok=await sat.select(sat.index);
  const geo=sat.satLayer,fog=sat.fogLayer;
  const maskedGeo=geo?.getContainer?.()?.querySelectorAll('img[style*="mask-image"]').length||0;
  const maskedFog=fog?.getContainer?.()?.querySelectorAll('img[style*="mask-image"]').length||0;
  let refreshCount=0;
  const origRefresh=sat.refreshAutoMasks;
  sat.refreshAutoMasks=function(){refreshCount++;return origRefresh.call(this);};
  const time=Date.parse('2026-11-20T17:00:00Z'),coord={z:6,x:30,y:24};
  const before=window.MeteoFoxFogMask.tileMask(time,coord,64,'geo',.8);
  sat.satOpacitySlider.value='50';
  sat.satOpacitySlider.dispatchEvent(new Event('input',{bubbles:true}));
  const after=window.MeteoFoxFogMask.tileMask(time,coord,64,'geo',.5);
  sat.satOpacitySlider.value='80';
  sat.satOpacitySlider.dispatchEvent(new Event('input',{bubbles:true}));
  sat.refreshAutoMasks=origRefresh;
  await sat.cycleSatMode(); // Auto -> Geo
  return {ok,maskedGeo,maskedFog,refreshCount,changed:before!==after};
 });
 assert.equal(dualMasks.ok,true,'Nova seleção Auto deve carregar');
 assert.ok(dualMasks.maskedGeo>0&&dualMasks.maskedFog>0,'Geo e Fog devem ter máscaras complementares: '+JSON.stringify(dualMasks));
 assert.ok(dualMasks.refreshCount>=2,'Mudança de opacidade deve recalcular máscaras');
 assert.equal(dualMasks.changed,true,'Máscara Geo no crepúsculo deve depender da opacidade');

 assert.equal(modes.geoLayer,'mtg_fd:rgb_geocolour','Voltar a GeoColour sem apagar fallback');
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
 await page.evaluate(()=>sat.select(1));
 const mobileStart=await page.evaluate(()=>sat.index);
 assert.equal(mobileStart,1,'Teste móvel deve partir de fotograma com anterior e seguinte');
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
