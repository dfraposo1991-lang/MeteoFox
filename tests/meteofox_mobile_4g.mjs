import { chromium } from 'playwright';
import fs from 'node:fs';
import assert from 'node:assert/strict';

// Auditoria do carregamento REAL dos produtos ECMWF numa rede móvel simulada.
// A emulação 4G é artificial (Chromium no CI), não uma medição num telemóvel físico.
const URL = 'https://dfraposo1991-lang.github.io/MeteoFox/';
const profiles = [
  {name:'desktop_normal',width:1440,height:900,mobile:false,throttle:false},
  {name:'telemovel_normal',width:390,height:844,mobile:true,throttle:false},
  {name:'telemovel_4g_lento',width:390,height:844,mobile:true,throttle:true},
];
const report={url:URL,utc:new Date().toISOString(),profiles:[],note:'Rede 4G lenta e CPU x4 simulados no Chromium, não num telefone físico'};
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});

function imageState(image){
 const i=document.getElementById(image);
 return i && i.complete && i.naturalWidth>0 && i.currentSrc ? {
  url:i.currentSrc,width:i.naturalWidth,height:i.naturalHeight
 } : null;
}
try{
 for(const profile of profiles){
  const context=await browser.newContext({
   viewport:{width:profile.width,height:profile.height},
   isMobile:profile.mobile,hasTouch:profile.mobile,
   deviceScaleFactor:profile.mobile?2:1,serviceWorkers:'block'
  });
  const page=await context.newPage();
  const session=await context.newCDPSession(page);
  await session.send('Network.enable');
  await session.send('Network.setCacheDisabled',{cacheDisabled:true});
  if(profile.throttle){
   await session.send('Network.emulateNetworkConditions',{
    offline:false,latency:180,downloadThroughput:200000,uploadThroughput:100000
   });
   await session.send('Emulation.setCPUThrottlingRate',{rate:4});
  }
  const started=Date.now();
  const failures=[];
  const responses=[];
  page.on('requestfailed',r=>failures.push({url:r.url(),error:r.failure()?.errorText}));
  page.on('response',r=>{
   if(/(?:chuva|rajadas|VIS)_\\d{3}\\.png/.test(r.url()))
    responses.push({url:r.url(),status:r.status(),contentLength:Number(r.headers()['content-length']||0)});
  });
  let httpStatus=null,error=null,times={};
  try{
   const response=await page.goto(URL,{waitUntil:'domcontentloaded',timeout:90000});
   httpStatus=response?.status();
   times.domReadyMs=Date.now()-started;
   const products=page.locator('[data-tab="precipGust"]');
   await products.click({timeout:15000});
   times.productsOpenedMs=Date.now()-started;
   for(const [key,id] of [['chuva','ecmwfRain'],['rajadas','ecmwfGust'],['vis','visSimImage']]){
    const element=page.locator('#'+id);
    await element.scrollIntoViewIfNeeded({timeout:15000});
    await page.waitForFunction(imageId=>{
      const e=document.getElementById(imageId);
      return !!(e&&e.complete&&e.naturalWidth&&e.currentSrc);
    },id,{timeout:90000});
    times[key+'VisibleMs']=Date.now()-started;
    times[key+'Url']=await element.evaluate(el=>el.currentSrc);
   }
  }catch(e){error=String(e)}
  const documentInfo=await page.evaluate(()=>{
   const nav=performance.getEntriesByType('navigation')[0];
   return {pageWidth:document.documentElement.scrollWidth,
    viewportWidth:document.documentElement.clientWidth,
    domContentLoadedMs:Math.round(nav?.domContentLoadedEventEnd||0),
    resources:performance.getEntriesByType('resource').length};
  }).catch(()=>({}));
  const result={name:profile.name,httpStatus,elapsedMs:Date.now()-started,
   times,documentInfo,responses,failures:failures.slice(0,15),error};
  report.profiles.push(result);
  console.log(JSON.stringify(result,null,2));
  await context.close();
 }
}finally{await browser.close()}
fs.mkdirSync('relatorios',{recursive:true});
fs.writeFileSync('relatorios/meteofox_mobile_4g.json',JSON.stringify(report,null,2)+'\n');
for(const r of report.profiles){
 assert.equal(r.httpStatus,200,r.name+': não foi possível abrir o site');
 assert.equal(r.error,null,r.name+': houve problemas ao carregar os três produtos');
 assert.ok(r.documentInfo.pageWidth<=r.documentInfo.viewportWidth+3,r.name+': overflow horizontal');
 assert.ok(r.times.visVisibleMs>=r.times.domReadyMs,r.name+': medições inválidas');
}
