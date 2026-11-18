#!/usr/bin/env python3
"""Diagnóstico não destrutivo de imagem visível simulada ECMWF OpenCharts."""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://charts.ecmwf.int'
PRODUCT = BASE + '/opencharts-api/v1/products/medium-simulated-vis/'
OUT = Path('diagnostico_visivel_simulado')
OUT.mkdir(exist_ok=True)
LOG = {'tested_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'product': 'medium-simulated-vis', 'steps': [], 'png_verified': False, 'conclusion': ''}
HEADERS = {'User-Agent': 'MeteoFox-OpenCharts-diagnostic/1.0', 'Accept': 'application/json,image/png,*/*'}

def record(name, **kw):
    LOG['steps'].append({'name': name, **kw})

def fetch(url, *, max_bytes=12_000_000):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Resposta excede limite de segurança')
        return data, dict(resp.headers), resp.geturl(), resp.status

def urls_in(obj):
    urls=[]
    def recurse(v, path='$', depth=0):
        if depth>12:return
        if isinstance(v, dict):
            for k,x in v.items():recurse(x, path+'.'+str(k),depth+1)
        elif isinstance(v,list):
            for i,x in enumerate(v[:50]):recurse(x,path+f'[{i}]',depth+1)
        elif isinstance(v,str):
            if (v.startswith('http://') or v.startswith('https://') or v.startswith('/')) and ('.png' in v.lower() or any(t in path.lower() for t in ('url','image','download','link','png'))):
                urls.append((path,urllib.parse.urljoin(BASE,v)))
    recurse(obj)
    return list(dict.fromkeys(urls))

def inspect_payload(name, obj):
    dump = OUT/(name+'.json')
    dump.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
    relevant = []
    def walk(x,p='$',depth=0):
        if depth>10:return
        if isinstance(x,dict):
            for k,v in x.items():
                if any(w in k.lower() for w in ('date','time','step','valid','base','run','area','layer','param','channel')):
                    relevant.append({'path':p+'.'+k,'value':str(v)[:250]})
                walk(v,p+'.'+k,depth+1)
        elif isinstance(x,list):
            for i,v in enumerate(x[:15]):walk(v,p+f'[{i}]',depth+1)
    walk(obj)
    return relevant[:60],urls_in(obj)

try:
    data,headers,final,status=fetch(PRODUCT,max_bytes=2_000_000)
    content_type=headers.get('Content-Type','')
    record('consulta_produto',http_status=status,content_type=content_type,final_url=final,bytes=len(data))
    info=json.loads(data)
    fields,urls=inspect_payload('resposta_produto',info)
    record('metadados_produto',top_level_keys=list(info) if isinstance(info,dict) else [],time_and_parameter_fields=fields,linked_urls=[{'field':p,'url':u} for p,u in urls[:25]])
    # Only download an image if the product explicitly advertises its URL.
    # Do not guess undocumented endpoint parameters or mislabel other products.
    urls=[(p,u) for p,u in urls if urllib.parse.urlparse(u).netloc.endswith('ecmwf.int')]
    for idx,(path,url) in enumerate(urls[:10],1):
        try:
            body,h,final_url,st=fetch(url)
            png=body[:8]==b'\x89PNG\r\n\x1a\n'
            record('descarga_candidata',field=path,http_status=st,content_type=h.get('Content-Type',''),url=final_url,bytes=len(body),valid_png_signature=png)
            if png:
                (OUT/'visivel_simulado_ecmwf.png').write_bytes(body)
                LOG['png_verified']=True
                LOG['image_url']=final_url
                LOG['conclusion']='PNG válido obtido do URL indicado pela resposta da API. Verificar manualmente produto, run, validade e condições de uso antes de integrar.'
                break
        except Exception as exc:
            record('descarga_candidata_erro',field=path,url=url,error=str(exc))
    if not LOG['png_verified']:
        LOG['conclusion']='Produto consultado, mas sem PNG obtido automaticamente. Ver resposta_produto.json para identificar parâmetros/URL oficiais exigidos pela API.'
except Exception as exc:
    record('erro',error=type(exc).__name__+': '+str(exc))
    LOG['conclusion']='Consulta falhou. Isto não prova inexistência do produto.'
finally:
    (OUT/'resultado.json').write_text(json.dumps(LOG,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(LOG,indent=2,ensure_ascii=False))
