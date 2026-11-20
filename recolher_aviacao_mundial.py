#!/usr/bin/env python3
"""MeteoFox: extrair os boletins mundiais originais das caches NOAA.

Ficheiros gzip/XML completos recomendados pelo Aviation Weather Center.
Publicação compacta na branch main. Não altera a recolha nacional.
"""
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import gzip
import json
import re

BASE='https://aviationweather.gov/data/cache/'
URLS={'metar':'metars.cache.xml.gz','taf':'tafs.cache.xml.gz'}
OUT=Path(__file__).resolve().parent/'data'/'aviation_world.json.gz'


def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def download(filename):
    request=Request(BASE+filename,headers={'User-Agent':'MeteoFox/4.0 (world aviation viewer; contact via GitHub MeteoFox)','Accept':'application/gzip,*/*'})
    with urlopen(request,timeout=65) as resp:
        binary=resp.read(30_000_000)
    if not binary.startswith(b'\x1f\x8b'):
        raise RuntimeError('NOAA não devolveu um ficheiro gzip válido: '+filename)
    data=gzip.decompress(binary)
    if len(data)>120_000_000:raise RuntimeError('Cache NOAA demasiado grande')
    return data


def val(element, tag):
    found=element.find(tag)
    return ''.join(found.itertext()).strip() if found is not None else ''


def parse_xml(raw, node):
    root=ET.fromstring(raw)
    output=[]
    for el in root.iter(node):
        code=val(el,'station_id').upper()
        report=val(el,'raw_text')
        utc=val(el,'observation_time') or val(el,'issue_time')
        if not re.fullmatch(r'[A-Z]{4}',code) or not report:continue
        output.append((code,{'raw':report,'utc':utc}))
    return output


def main():
    result={'checked_utc':stamp(),'source':'NOAA Aviation Weather Center (worldwide cache)',
            'metar':{},'speci':{},'taf':{}}
    all_metars=parse_xml(download(URLS['metar']),'METAR')
    for code,item in all_metars:
        kind='speci' if re.match(r'^\s*SPECI\b',item['raw'],re.I) else 'metar'
        old=result[kind].get(code)
        if old is None or item['utc']>=old['utc']:
            result[kind][code]=item
    for code,item in parse_xml(download(URLS['taf']),'TAF'):
        old=result['taf'].get(code)
        if old is None or item['utc']>=old['utc']:
            result['taf'][code]=item
    if not result['metar'] or not result['taf']:
        raise RuntimeError('Dados NOAA incompletos: preservar ficheiro anterior')
    # Se não houver novo boletim de um aeródromo, preservar o último emitido,
    # mas sempre com a hora original visível, sem o apresentar como atual.
    if OUT.exists():
        try:
            previous=json.loads(gzip.decompress(OUT.read_bytes()).decode('utf-8'))
            for kind in ('metar','speci','taf'):
                for code, old in previous.get(kind,{}).items():
                    current=result[kind].get(code)
                    if current is None or old.get('utc','')>current.get('utc',''):
                        result[kind][code]=old
        except (OSError,ValueError,EOFError):
            pass
    OUT.parent.mkdir(exist_ok=True)
    blob=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    temp=OUT.with_suffix('.tmp')
    temp.write_bytes(gzip.compress(blob,compresslevel=9,mtime=0))
    temp.replace(OUT)
    # Dados dedicados à LEVC no mapa interativo: pequeno JSON, sem descarregar
    # o arquivo mundial completo em cada visita ao mapa.
    levc={'checked_utc':result['checked_utc'],'source':result['source'],'metar':{},'speci':{},'taf':{}}
    for kind in ('metar','speci','taf'):
        if 'LEVC' in result[kind]:
            levc[kind]['LEVC']=result[kind]['LEVC']
    target=OUT.parent/'aviation_valencia.json'
    target.write_text(json.dumps(levc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Valência LEVC:',{k:bool(levc[k].get('LEVC')) for k in ('metar','speci','taf')})
    print('Mundo:',{k:len(result[k]) for k in ('metar','speci','taf')},'tamanho gzip:',OUT.stat().st_size)

if __name__=='__main__':main()
