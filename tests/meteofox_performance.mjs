import { chromium } from 'playwright';
import fs from 'node:fs';
import assert from 'node:assert/strict';

// Mede a versão publicada, não uma simulação local. Relatório guardado em artifacts.
const SITE = process.env.METEOFOX_SITE || 'https://dfraposo1991-lang.github.io/MeteoFox/';
const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
const report={url:SITE,measured_utc:new Date().toISOString(),profiles:[]};
try{
 for(const profile of [
  {name:'desktop',width:1440,height:900,mobile:false},
  {name:'mobile',width:390,height:844,mobile:true}
 ]){
  const context=await browser.newContext({
   viewport:{width:profile.width,height:profile.height},
   isMobile:profile.mobile,hasTouch:profile.mobile,
   deviceScaleFactor:profile.mobile?2:1,
   serviceWorkers:'block'
  });
  const page=await context.newPage();
  const failures=[];
  const imageRequests=[];
  page.on('requestfailed',req=>failures.push({url:req.url(),reason:req.failure()?.errorText}));
  page.on('response',res=>{
   if(/(?:chuva|rajadas|VIS)_\\d{3}\\.png/.test(res.url()))
    imageRequests.push({url:res.url(),status:res.status(),bytes:Number(res.headers()['content-length']||0)});
  });
  const started=Date.now();
  let navStatus=null,loadError=null;
  try{
   const res=await page.goto(SITE,{waitUntil:'domcontentloaded',timeout:60000});
   navStatus=res?.status()||null;
   await page.waitForTimeout(3500);
   const tab=page.locator('[data-tab="precipGust"]');
   if(await tab.count())await tab.click({timeout:10000});
   await page.waitForTimeout(4000);
  }catch(e){loadError=String(e)}
  const performance=await page.evaluate(()=>{
   const nav=performance.getEntriesByType('navigation')[0];
   const res=performance.getEntriesByType('resource');
   return {
    domContentLoadedMs:Math.round(nav?.domContentLoadedEventEnd||0),
    loadEventMs:Math.round(nav?.loadEventEnd||0),
    resources:res.length,
    transferredBytes:res.reduce((n,r)=>n+(r.transferSize||0),0),
    pngRequests:res.filter(r=>/\\.(?:png)(?:\\?|$)/.test(r.name)).length,
    pageWidth:document.documentElement.scrollWidth,
    viewportWidth:document.documentElement.clientWidth,
    rainSrc:document.querySelector('#ecmwfRain')?.getAttribute('src')||null,
    gustSrc:document.querySelector('#ecmwfGust')?.getAttribute('src')||null,
    rainLoaded:!!document.querySelector('#ecmwfRain')?.naturalWidth,
    gustLoaded:!!document.querySelector('#ecmwfGust')?.naturalWidth,
    visibleImgBytes:Array.from(document.querySelectorAll('img')).filter(img=>img.complete&&img.naturalWidth).length
   };
  }).catch(()=>({}));
  const result={name:profile.name,viewport:[profile.width,profile.height],
   httpStatus:navStatus,elapsedMs:Date.now()-started,loadError,performance,
   imageRequests:imageRequests.slice(0,60),requestFailures:failures.slice(0,30)};
  report.profiles.push(result);
  console.log(JSON.stringify(result,null,2));
  await context.close();
 }
}finally{await browser.close()}
fs.mkdirSync('relatorios',{recursive:true});
fs.writeFileSync('relatorios/meteofox_performance.json',JSON.stringify(report,null,2));
assert.ok(report.profiles.every(p=>p.httpStatus===200),'Site público não devolveu HTTP 200 em ambos os perfis');
