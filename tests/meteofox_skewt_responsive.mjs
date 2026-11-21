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
  const positions=await page.evaluate(()=>{
   const rect=id=>{const e=document.getElementById(id);const r=e.getBoundingClientRect();return {top:r.top+window.scrollY,bottom:r.bottom+window.scrollY,width:r.width}};
   const layout=document.querySelector('.sounding-layout').getBoundingClientRect();
   return {layoutBottom:layout.bottom+window.scrollY,thermo:rect('thermoAdvanced'),composite:rect('compositeAdvanced'),severe:rect('severePanel'),scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth};
  });
  assert.ok(positions.thermo.top>=positions.layoutBottom-1,'Termodinâmica deve ficar abaixo dos diagramas');
  assert.ok(positions.composite.top>=positions.thermo.bottom-1,'SCP/STP deve ficar abaixo da termodinâmica');
  assert.ok(positions.severe.top>=positions.layoutBottom-1,'Cinemática deve ficar abaixo dos diagramas');
  assert.ok(positions.scrollWidth<=positions.viewport+3,'Painéis não devem provocar scroll horizontal da página');
  assert.equal(errors.length,0,'Sem erros JavaScript: '+errors.join('; '));
  fs.mkdirSync('capturas',{recursive:true});
  await page.screenshot({path:'capturas/skewt-'+width+'.png',fullPage:true});
  console.log(width,positions);
  await page.close();
 }
}finally{await browser.close()}
