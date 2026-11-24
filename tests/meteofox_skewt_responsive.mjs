import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const base='http://127.0.0.1:8765';
const data=JSON.parse(fs.readFileSync('produtos_experimentais/previsao_ecmwf.json','utf8'));
const first=data.soundings[0];
const mock={model:data.model,run_utc:data.run_utc,experimental:true,soundings:data.soundings.map(s=>({valid_utc:s.valid_utc,cities:Object.fromEntries(Object.keys(s.cities).map(c=>[c,{status:'ok',mlcape_jkg:750,mlcin_jkg:-40,mucape_jkg:1100,mucin_jkg:-30,ml_lcl_hpa:920}]))}))};
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:850},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/produtos_experimentais/conveccao_termodinamica.json',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(mock)}));
  await page.goto(base+'/laboratorio.html',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#advMLCAPE')?.textContent.includes('750'),{timeout:20000});
  await page.locator('#foxAnalysis').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#foxExplanation')?.textContent.includes('1100 J/kg'));
  assert.equal(await page.locator('#foxTabs [role=tab]').count(),3);
  for(const [group,panel] of [['thermo','thermoAdvanced'],['kin','severePanel'],['conv','compositeAdvanced']]){
   await page.locator('[data-fox-tab="'+group+'"]').click();
   assert.equal(await page.locator('#'+panel).isVisible(),true,group+' deve estar visível');
   assert.equal(await page.locator('[data-fox-tab="'+group+'"]').getAttribute('aria-selected'),'true');
   for(const other of ['thermoAdvanced','severePanel','compositeAdvanced'].filter(x=>x!==panel))
    assert.equal(await page.locator('#'+other).isHidden(),true,other+' deve estar oculto');
   const positions=await page.evaluate(id=>{
    const layout=document.querySelector('.sounding-layout').getBoundingClientRect();
    const summary=document.querySelector('#foxAnalysis').getBoundingClientRect();
    const panel=document.getElementById(id).getBoundingClientRect();
    return {layoutBottom:layout.bottom,summaryTop:summary.top,summaryBottom:summary.bottom,panelTop:panel.top,scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth};
   },panel);
   assert.ok(positions.summaryTop>=positions.layoutBottom-1,'Síntese abaixo dos diagramas');
   assert.ok(positions.panelTop>=positions.summaryBottom-1,'Painel abaixo da síntese');
   assert.ok(positions.scrollWidth<=positions.viewport+3,'Sem scroll horizontal da página');
  }
  assert.ok(await page.locator('#skew > *').count()>0,'Skew-T desenhado');
  assert.ok(await page.locator('#hodograph > *').count()>0,'Hodógrafo desenhado');
  await page.locator('#city').selectOption('Porto');
  await page.waitForFunction(()=>window.currentSoundingCity==='Porto');
  assert.ok((await page.locator('#foxExplanation').innerText()).includes('1100 J/kg'));
  await page.locator('#skewNext').click();
  await page.waitForFunction(()=>Number(document.querySelector('#skewSlider').value)>0);
  assert.ok((await page.locator('#foxExplanation').innerText()).includes('1100 J/kg'));
  assert.equal(errors.length,0,'Sem erros JavaScript: '+errors.join('; '));
  fs.mkdirSync('capturas',{recursive:true});
  await page.screenshot({path:'capturas/skewt-'+width+'.png',fullPage:true});
  console.log(width,'Fox Analysis and tabs validated');
  await page.close();
 }
}finally{await browser.close()}
