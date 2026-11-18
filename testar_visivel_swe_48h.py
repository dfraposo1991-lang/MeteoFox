#!/usr/bin/env python3
"""Diagnóstico ECMWF OpenCharts: VIS ch2, SW Europe, +3 a +48 h (sem publicar)."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from PIL import Image

API='https://charts.ecmwf.int/opencharts-api/v1/products/medium-simulated-vis/'
PROJECTION='opencharts_south_west_europe'
LAYER='sim_image_vis_ch2'
HEADERS={'User-Agent':'MeteoFox-diagnostico-VIS/1.0 (OpenCharts API)','Accept':'application/json, image/png;q=0.9, */*;q=0.7'}
ROOT=Path('diagnostico_visivel_48h')
PNG_MAGIC=b'\x89PNG\r\n\x1a\n'


def fetch(url, timeout=40, limit=7_000_000):
    req=Request(url, headers=HEADERS)
    with urlopen(req,timeout=timeout) as response:
        data=response.read(limit+1)
        if len(data)>limit: raise ValueError('Resposta maior do que o limite de segurança')
        return response.status, response.headers.get('Content-Type',''), data


def stamp(dt): return dt.strftime('%Y%m%d%H%M')

def iso(dt): return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_description(description):
    """Usa exclusivamente a descrição devolvida pelo ECMWF, nunca supõe validade."""
    rx=r'Base\s*time\s*:\s*(.*?)\s+Valid\s*time\s*:\s*(.*?)\s*\(\s*\+(\d+)h\s*\)\s+Area\s*:\s*(.*?)\s+Channel\s*:'
    match=re.search(rx,description,re.I)
    if not match: raise ValueError('Não foi possível extrair Run/Validade/Área da descrição ECMWF')
    base_str,valid_str,step_str,area=match.groups()
    # ECMWF: Wed 18 Nov 2026 06 UTC
    fmt='%a %d %b %Y %H UTC'
    base=datetime.strptime(base_str.strip(),fmt).replace(tzinfo=timezone.utc)
    valid=datetime.strptime(valid_str.strip(),fmt).replace(tzinfo=timezone.utc)
    return base,valid,int(step_str),area.strip()


def crop_map(image_bytes):
    """Localiza o maior bloco retangular de mapa sem recortar por coordenadas fixas."""
    im=Image.open(io.BytesIO(image_bytes)).convert('RGB')
    w,h=im.size
    # Colunas com cobertura não-branca, medindo amostras no miolo de cada linha
    pix=im.load(); stride=max(2,w//400)
    samples=list(range(0,w,stride))
    nonwhite=[]
    for y in range(h):
        count=sum(1 for x in samples if min(pix[x,y])<228)
        nonwhite.append(count/max(1,len(samples)))
    segments=[]; start=None
    for y,ratio in enumerate(nonwhite+[0]):
        if ratio>=0.67 and start is None: start=y
        if ratio<0.67 and start is not None:
            if y-start>=int(h*0.12): segments.append((start,y))
            start=None
    if not segments: raise ValueError('Não foi possível reconhecer a área retangular do mapa')
    y0,y1=max(segments,key=lambda t:t[1]-t[0])
    # Usar uma faixa significativa de linhas internas ao mapa
    ys=list(range(y0+int((y1-y0)*0.15),y1-int((y1-y0)*0.15),max(1,(y1-y0)//180)))
    x_counts=[]
    for x in range(w):
        count=sum(1 for y in ys if min(pix[x,y])<228)
        x_counts.append(count/max(1,len(ys)))
    xs=[x for x,v in enumerate(x_counts) if v>=0.60]
    if not xs: raise ValueError('Não foi possível reconhecer as margens laterais do mapa')
    x0,x1=min(xs),max(xs)+1
    if (x1-x0)<w*.55 or (y1-y0)<h*.20: raise ValueError('Recorte demasiado pequeno; rever imagem')
    box=(x0,y0,x1,y1)
    output=io.BytesIO(); im.crop(box).save(output,format='PNG',optimize=True)
    return output.getvalue(),box,(w,h)


def request_step(base,step):
    valid=base+timedelta(hours=step)
    query=urlencode({'base_time':stamp(base),'valid_time':stamp(valid), 'projection':PROJECTION,'layer_name':LAYER})
    url=API+'?'+query
    status,ctype,data=fetch(url)
    if status!=200 or 'json' not in ctype.lower(): raise ValueError(f'API inesperada: HTTP {status} / {ctype}')
    obj=json.loads(data)
    info=obj.get('data',{})
    attrs=info.get('attributes',{})
    description=attrs.get('description','')
    result_base,result_valid,result_step,result_area=parse_description(description)
    if result_base!=base or result_valid!=valid or result_step!=step:
        raise ValueError(f'Run/validade diferentes do solicitado: {description}')
    area_norm=re.sub(r'[^a-z]','',result_area.lower())
    if 'south' not in area_norm or 'west' not in area_norm or 'europe' not in area_norm:
        raise ValueError(f'Região não coincide com South West Europe: {result_area!r}')
    image_url=info.get('link',{}).get('href','')
    if not image_url.startswith('https://charts.ecmwf.int/'):
        raise ValueError('URL da imagem inexistente ou fora do domínio ECMWF')
    image_status,image_ct,image_data=fetch(image_url,timeout=60)
    if image_status!=200 or not image_data.startswith(PNG_MAGIC):
        raise ValueError(f'Não foi recebido PNG válido: {image_status}/{image_ct}')
    processed,box,original_size=crop_map(image_data)
    return {'run_utc':iso(result_base),'valid_utc':iso(result_valid),'step_h':step,
            'area':result_area,'source_url':image_url,'description':description,
            'original_png_sha256':hashlib.sha256(image_data).hexdigest(),
            'crop_box':box,'original_size':original_size,'image_bytes':processed}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base-time',help='Run específico YYYYMMDDHHMM; omitir para procurar Runs recentes')
    args=ap.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    if args.base_time:
        runs=[datetime.strptime(args.base_time,'%Y%m%d%H%M').replace(tzinfo=timezone.utc)]
    else:
        # Começa pelo último run de 6 h com margem de publicação de 5 h
        start=(now-timedelta(hours=5)).replace(minute=0,second=0,microsecond=0)
        start=start-timedelta(hours=start.hour%6)
        runs=[start-timedelta(hours=6*i) for i in range(3)]
    report={'generated_utc':iso(now),'product':'medium-simulated-vis','projection':PROJECTION,
            'layer_name':LAYER,'requested_steps_h':list(range(3,49,3)),
            'attempted_runs':[],'complete':False,'notes':'Teste separado: não altera o MeteoFox.'}
    complete_run=None
    for base in runs:
        run_report={'base_time_utc':iso(base),'frames':[],'success_count':0}
        temp_files=[]; hashes=set(); failed=False
        for step in range(3,49,3):
            frame_report={'step_h':step}
            try:
                data=request_step(base,step)
                digest=data['original_png_sha256']
                if digest in hashes: raise ValueError('PNG repetido noutro passo: não permite animação válida')
                hashes.add(digest)
                filename=f'VIS_{step:03d}.png'
                (ROOT/filename).write_bytes(data.pop('image_bytes'))
                temp_files.append(filename)
                frame_report.update({'ok':True,'filename':filename,**data})
                run_report['success_count']+=1
            except (HTTPError,URLError,OSError,ValueError,KeyError,TimeoutError) as exc:
                frame_report.update({'ok':False,'error':str(exc)[:350]})
                failed=True
                print(f'[{iso(base)} +{step:02d}h] ERRO: {exc}',flush=True)
            else:
                print(f'[{iso(base)} +{step:02d}h] OK / South West Europe',flush=True)
            run_report['frames'].append(frame_report)
            time.sleep(.3)
        report['attempted_runs'].append(run_report)
        if not failed and run_report['success_count']==16:
            complete_run=run_report
            break
        for filename in temp_files: (ROOT/filename).unlink(missing_ok=True)
    if complete_run:
        report['complete']=True
        manifest={'product':report['product'],'projection':PROJECTION,'layer_name':LAYER,
            'run_utc':complete_run['base_time_utc'], 'credit':'© ECMWF · CC BY 4.0',
            'frames':[{'file':f['filename'],'step_h':f['step_h'],'run_utc':f['run_utc'],
                       'valid_utc':f['valid_utc']} for f in complete_run['frames']]}
        (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print('SUCESSO: 16 PNG distintos e metadados confirmados.',flush=True)
    else:
        print('SEM SUCESSO COMPLETO: consultar relatorio.json; nenhuma alteração ao site.',flush=True)
    (ROOT/'relatorio.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if complete_run else 1

if __name__=='__main__': sys.exit(main())
