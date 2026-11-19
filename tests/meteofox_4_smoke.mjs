import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:900}});
const errors=[];
page.on('pageerror',e=>errors.push(String(e)));
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lQAAAABJRU5ErkJggg==','base64');
const respondPNG=r=>r.fulfill({status:200,contentType:'image/png',body:png,headers:{'access-control-allow-origin':'*'}});
const current=Math.floor(Date.now()/600000)*600000;
const frames=Array.from({length:5},(_,i)=>current-(4-i)*600000);
await page.route(/\/(chuva|rajadas)_\d{3}\.png(?:\?.*)?$/,respondPNG);
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
 await page.waitForFunction(()=>document.getElementById('ecmwfRain')?.getAttribute('src')?.includes('chuva_003.png'));
 const first=await page.locator('#ecmwfRain').getAttribute('src');
 const satValueBefore=await page.locator('#visSimSlider').inputValue();
 await page.locator('#ecmwfNext').click();
 const r=await page.locator('#ecmwfRain').getAttribute('src'),w=await page.locator('#ecmwfGust').getAttribute('src');
 assert.equal(first,'./chuva_003.png');assert.equal(r,'./chuva_006.png');assert.equal(w,'./rajadas_006.png');
 assert.equal(await page.locator('#visSimSlider').inputValue(),satValueBefore);
 await page.locator('#ecmwfSlider').fill('15');
 assert.equal(await page.locator('#ecmwfRain').getAttribute('src'),'./chuva_048.png');
 assert.equal(await page.locator('#ecmwfGust').getAttribute('src'),'./rajadas_048.png');
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
 await page.getByRole('button',{name:/Satélite: desligado/}).click();
 await page.getByRole('button',{name:/Radar: desligado/}).click();
 await page.waitForFunction(()=>{const slider=document.querySelector('#satTools input[type="range"]');return slider&&!slider.disabled&&Number(slider.max)>=1;},{timeout:15000});
 const mapTimeline=page.locator('#satTools input[type="range"]');
 await mapTimeline.fill('0');
 await page.locator('#showLegends').focus();
 await page.keyboard.press('Home');
 const keyboardState=await page.evaluate(()=>{
  const range=document.querySelector('#satTools input[type="range"]');
  const p=document.querySelector('#satTools');
  return {value:range.value,max:range.max,disabled:range.disabled,
    rangeVisible:getComputedStyle(range).display,hostVisible:getComputedStyle(p).display,
    focused:document.activeElement?.id,scriptPresent:!!document.querySelector('script[src="./meteofox_keyboard.js"]')};
 });
 assert.equal(await mapTimeline.inputValue(),'0','Mapa Home deve selecionar a primeira imagem: '+JSON.stringify(keyboardState));
 await page.keyboard.press('ArrowRight');
 assert.equal(await mapTimeline.inputValue(),'1','Mapa com radar/Meteosat deve navegar pelo teclado sem cursor focado');

 const endText=await page.locator('#satTools .sat-clock').last().innerText();
 assert.ok(endText.includes('Z'),endText);
 console.log('PASS: Produtos, 16 passos chuva+rajadas, independência VIS, tabelas METAR, mapa radar/Meteosat sincronizado');
 assert.deepEqual(errors,[],'Erros JavaScript inesperados');
}finally{await browser.close();}
