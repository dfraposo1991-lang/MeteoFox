import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';

const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
await mkdir('capturas',{recursive:true});
try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
    const page=await browser.newPage({viewport,deviceScaleFactor:1});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:8765/index.html',{waitUntil:'networkidle',timeout:50000});
    await page.waitForFunction(()=>document.getElementById('status')?.textContent.includes('30 períodos'),{timeout:20000});
    assert.equal(errors.length,0,'Sem erros JS');
    const data=await page.evaluate(async()=>await (await fetch('./produtos_experimentais/previsao_ecmwf.json')).json());
    assert.equal(data.meteogram_lisboa.length,30);
    assert.equal(data.meteogram_lisboa[29].step_h,90);
    assert.equal(data.soundings.length,9);
    for(const chart of ['chartTemp','chartRain','chartWind','chartPressure','chartCloud']){
      assert.ok(await page.locator('#'+chart+' svg, #'+chart+' polyline, #'+chart+' rect').count()>0,
        'Gráfico não desenhado: '+chart);
    }
    await page.screenshot({path:'capturas/meteograma_'+viewport.width+'.png',fullPage:true});
    await page.locator('#tabS').click();
    assert.equal(await page.locator('#panelS').isVisible(),true);
    assert.equal(await page.locator('#step option').count(),9);
    for(const city of ['Porto','Lisboa','Beja']){
      await page.locator('#city').selectOption(city);
      await page.locator('#step').selectOption('48');
      assert.match(await page.locator('#validSounding').innerText(),new RegExp(city));
      const pts=await page.locator('#skew polyline').count();
      assert.equal(pts,2);
      const pressureLines=await page.locator('#skew line[stroke="#34526b"]').evaluateAll(lines=>lines.map(x=>({y1:Number(x.getAttribute('y1')),y2:Number(x.getAttribute('y2'))})));
      // Pressão menor (200 hPa) em cima: primeira linha de 1000 hPa deve estar em baixo.
      assert.ok(pressureLines[0].y1>pressureLines.at(-1).y1,
        'A escala vertical do Skew-T deve diminuir em altitude');
    }
    await page.locator('#city').selectOption('Lisboa');
    await page.locator('#step').selectOption('0');
    await page.screenshot({path:'capturas/skewt_'+viewport.width+'.png',fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
    assert.ok(overflow<4,'Overflow horizontal inesperado: '+overflow);
    assert.equal(errors.length,0,'Erros JS ao alternar sondagens');
    console.log('OK browser:',viewport.width,'sem erros; meteograma +90h; 3 cidades e 9 prazos; 5 gráficos; pressão Skew-T correta');
    await page.close();
  }
}finally{await browser.close()}
