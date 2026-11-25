#!/usr/bin/env python3
"""Obtém instantes da camada GeoColour MTG pela dimensão TIME do WMS EUMETSAT.
Não inventa instantes nem descarrega imagens. Python standard library.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import json, re, xml.etree.ElementTree as ET

ENDPOINT = 'https://view.eumetsat.int/geoserver/wms'
LAYER = 'mtg_fd:rgb_geocolour'
OUT = Path(__file__).resolve().parent / 'data' / 'satellite_times.json'
UTC = timezone.utc

def utc(s):
    try:
        value = datetime.fromisoformat(s.strip().replace('Z', '+00:00'))
        return value.astimezone(UTC) if value.tzinfo else None
    except ValueError:
        return None

def iso(d):
    return d.isoformat(timespec='seconds').replace('+00:00','Z')

def period_ms(p):
    match = re.fullmatch(r'P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)',p)
    if not match: return None
    seconds = sum(int(n or 0)*scale for n,scale in zip(match.groups(),[3600,60,1]))
    return timedelta(seconds=seconds) if seconds else None

def parse_dimension(raw, now, limit=36):
    found=set()
    for part in raw.replace('\n','').split(','):
        part=part.strip()
        if not part:continue
        v=part.split('/')
        if len(v)==1:
            dt=utc(v[0]);
            if dt:found.add(dt)
        elif len(v)==3:
            begin,end=utc(v[0]),utc(v[1]);step=period_ms(v[2])
            if not begin or not end or not step or end<begin:continue
            # Saltar diretamente para o fim do intervalo, sem iterar desde 2024.
            t=end
            for _ in range(200):
                if t < begin or t < now-timedelta(hours=6): break
                found.add(t);t-=step
    return sorted((v for v in found if now-timedelta(hours=6)<=v<=now+timedelta(minutes=2)))[-limit:]

def local(tag):return tag.rsplit('}',1)[-1]

def dimension_for(root, product=LAYER):
    # Procura a camada específica, ignorando outras fontes presentes no capabilities.
    parents={child:parent for parent in root.iter() for child in parent}
    layer=None
    for elem in root.iter():
        if local(elem.tag)!='Layer':continue
        if any(local(x.tag)=='Name' and (x.text or '').strip()==product for x in elem):
            layer=elem;break
    if layer is None:raise RuntimeError('Camada GeoColour não encontrada no GetCapabilities')
    node=layer
    while node is not None:
        for child in node:
            if local(child.tag) in ('Dimension','Extent') and child.attrib.get('name','').lower()=='time' and (child.text or '').strip():
                return child.text.strip()
        node=parents.get(node)
    raise RuntimeError('Dimensão TIME não publicada para a camada')

def main():
    query=ENDPOINT+'?service=WMS&version=1.1.1&request=GetCapabilities'
    request=Request(query,headers={'User-Agent':'MeteoFox/1.0 (+UTC satellite metadata)','Accept':'application/xml,text/xml,*/*'})
    with urlopen(request,timeout=45) as r:
        if r.status!=200:raise RuntimeError('GetCapabilities HTTP '+str(r.status))
        xml=r.read(50_000_001)
    if len(xml)>50_000_000:raise RuntimeError('GetCapabilities acima de 50MB')
    root=ET.fromstring(xml)
    now=datetime.now(UTC)
    times=parse_dimension(dimension_for(root),now)
    if len(times)<2:raise RuntimeError('Menos de 2 instantes recentes confirmados')
    payload={'source':'EUMETSAT EUMETView GetCapabilities','layer':LAYER,
             'checked_utc':iso(now),'times_utc':[iso(t) for t in times]}
    try:
        payload['fog_times_utc']=[iso(t) for t in parse_dimension(dimension_for(root,'mtg_fd:rgb_fog'),now)]
    except RuntimeError:
        payload['fog_times_utc']=[]
    try:
        payload['lightning_times_utc']=[iso(t) for t in parse_dimension(dimension_for(root,'mtg_fd:li_afa'),now,72) if t+timedelta(minutes=5)<=now]
    except RuntimeError:
        payload['lightning_times_utc']=[]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Instantes Meteosat confirmados:',len(times),iso(times[0]),iso(times[-1]))

if __name__=='__main__':main()
