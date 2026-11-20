import { chromium } from 'playwright';
import fs from 'node:fs';

const URL='https://dfraposo1991-lang.github.io/MeteoFox/mapa.html';
const configurations=[
 {name:'computador',width:1440,height:900,mobile:false,slow:false},
 {name:'telemovel',width:390,height:844,mobile:true,slow:false},
 {name:'telemovel_4g_lento',width:390,height:844,mobile:true,slow:true}
];
const report={url:URL,checked_utc:new Date().toISOString(),
 methodology:'Chromium Linux CI; 4G lento simulado com RTT 180 ms, 200 kB/s de download e CPU 4x mais lenta. Observa apenas tiles reais de radar/Meteosat; nunca substitui respostas externas por imagens artificiais.',
 profiles:[]};
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const now=()=>Date.now();
function classify(url){
 if(/view\.eumetsat\.int|geoserver\/wms/i.test(url))return 'meteosat';
 if(/rainviewer|tilecache/i.test(url))return 'radar';
 if(/openstreetmap|tile\.openstreetmap/i.test(url))return 'base';
 return null;
}
async function visibleTiles(page,source){
 return page.evaluate(s=>[...document.querySelectorAll('#largeMap img')]
   .filter(i=>i.complete&&i.naturalWidth>0&&
    (s==='meteosat'?/view\.eumetsat\.int|geoserver\/wms/i.test(i.currentSrc):
     s==='radar'?/rainviewer|tilecache/i.test(i.currentSrc):
     /openstreetmap/i.test(i.currentSrc))).length,source);
}
async function sampleTiles(page,source,timeout=18000){
 const begin=now();
 while(now()-begin<timeout){
  const n=await visibleTiles(page,source).catch(()=>0);
  if(n>0)return {visible:true,tiles:n,waitMs:now()-begin};
  await page.waitForTimeout(350);
 }
 return {visible:false,tiles:0,waitMs:now()-begin};
}
try{
 for(const cfg of configurations){
  const context=await browser.newContext({
   viewport:{width:cfg.width,height:cfg.height},
   deviceScaleFactor:cfg.mobile?2:1,isMobile:cfg.mobile,hasTouch:cfg.mobile,
   serviceWorkers:'block'
  });
  const page=await context.newPage();
  const cdp=await context.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  if(cfg.slow){
   await cdp.send('Network.emulateNetworkConditions',{
    offline:false,latency:180,downloadThroughput:200000,uploadThroughput:100000
   });
   await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
  }
  const start=now(),responses=[],failures=[];
  page.on('response',r=>{const cat=classify(r.url());if(cat)
   responses.push({category:cat,status:r.status(),bytes:Number(r.headers()['content-length']||0),
    ms:now()-start,url:r.url().slice(0,220)});
  });
  page.on('requestfailed',r=>{const cat=classify(r.url());if(cat)failures.push({
   category:cat,ms:now()-start,error:r.failure()?.errorText||'?',url:r.url().slice(0,180)})});
  const result={name:cfg.name,viewport:[cfg.width,cfg.height],httpStatus:null,
   timing:{},layers:{},network:{},errors:[]};
  try{
   const navigation=await page.goto(URL,{waitUntil:'domcontentloaded',timeout:90000});
   result.httpStatus=navigation?.status()??null;
   result.timing.domReadyMs=now()-start;
   await page.locator('#satTools button').first().waitFor({timeout:25000});
   result.timing.controlsReadyMs=now()-start;
   result.layers.base=await sampleTiles(page,'base',cfg.slow?15000:7000);
   const radar=page.getByRole('button',{name:/Radar: desligado/});
   await radar.click({timeout:12000});
   result.timing.radarClickedMs=now()-start;
   await page.waitForTimeout(500);
   result.layers.radar=await sampleTiles(page,'radar',cfg.slow?28000:15000);
   result.layers.radar.status=await page.locator('#satTools .sat-status').innerText().catch(()=>null);
   const satellite=page.getByRole('button',{name:/Satélite: desligado/});
   await satellite.click({timeout:12000});
   result.timing.satelliteClickedMs=now()-start;
   result.layers.meteosat=await sampleTiles(page,'meteosat',cfg.slow?30000:18000);
   result.layers.meteosat.status=await page.locator('#satTools .sat-status').innerText().catch(()=>null);
   result.layers.both=await page.evaluate(()=>({
    radarOn:document.querySelector('#satTools button:nth-child(2)')?.getAttribute('aria-pressed'),
    satelliteOn:document.querySelector('#satTools button:first-child')?.getAttribute('aria-pressed'),
    timelineEnabled:!document.querySelector('#satTools input[type="range"]')?.disabled,
    timelineSteps:Number(document.querySelector('#satTools input[type="range"]')?.max||0)+1
   }));
   result.timing.totalMs=now()-start;
   result.layout=await page.evaluate(()=>({
    viewportWidth:document.documentElement.clientWidth,
    pageWidth:document.documentElement.scrollWidth,
    mapWidth:Math.round(document.getElementById('largeMap').getBoundingClientRect().width),
    mapHeight:Math.round(document.getElementById('largeMap').getBoundingClientRect().height)
   }));
  }catch(e){result.errors.push(String(e));}
  result.network={
   requests:Object.fromEntries(['base','radar','meteosat'].map(k=>[k,responses.filter(x=>x.category===k).length])),
   failed:Object.fromEntries(['base','radar','meteosat'].map(k=>[k,failures.filter(x=>x.category===k).length])),
   declaredBytes:Object.fromEntries(['base','radar','meteosat'].map(k=>[k,responses.filter(x=>x.category===k).reduce((n,x)=>n+x.bytes,0)])),
   statuses:Object.fromEntries(['base','radar','meteosat'].map(k=>[k,[...new Set(responses.filter(x=>x.category===k).map(x=>x.status))]])),
   samples:responses.slice(0,5),
   failureSamples:failures.slice(0,5)
  };
  console.log(JSON.stringify(result,null,2));
  report.profiles.push(result);
  await context.close();
 }
}finally{await browser.close();}
fs.mkdirSync('relatorios',{recursive:true});
fs.writeFileSync('relatorios/mapa_radar_meteosat_performance.json',JSON.stringify(report,null,2)+'\n');
if(report.profiles.some(p=>p.httpStatus!==200))process.exitCode=1;
