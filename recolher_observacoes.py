#!/usr/bin/env python3
"""Consulta METAR/SPECI OGIMET, TAF (incluindo AMD) NOAA, SYNOP OGIMET.
Mantém a última mensagem por aeródromo/tipo quando nenhuma mais recente chegou.
Um ficheiro de estado por categoria, sem séries temporais de consultas.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, re, sys
import server

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)

def stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def load(name):
    path=DATA/name
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}

def save(name, data):
    path=DATA/name
    content=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return
    temp=path.with_suffix('.tmp')
    temp.write_text(content,encoding='utf-8')
    temp.replace(path)
    print('Atualizado:',path)

def latest(previous, incoming):
    """Aceita mensagens apenas se forem mais recentes ou corrigidas na mesma hora."""
    newraw=(incoming or {}).get('raw','').strip()
    if not newraw: return previous
    if not previous or not previous.get('raw'): return incoming
    prevtime=previous.get('utc') or ''
    newtime=incoming.get('utc') or ''
    if newtime and prevtime:
        return incoming if newtime>prevtime or (newtime==prevtime and newraw!=previous['raw']) else previous
    # Não eliminar mensagens antigas por falta de data comparável.
    return previous

def merge_records(old, new):
    result=dict(old or {})
    for station,report in (new or {}).items():
        candidate=latest(result.get(station),report)
        if candidate:result[station]=candidate
    return result

def observation_data():
    """OGIMET getmetar inclui METAR e SPECI; distinguir pelo prefixo da mensagem."""
    rows=server.parse_csv(server.ogimet('metar',hours=12))
    metar={}; speci={}
    for r in sorted(rows,key=lambda item:item['utc'],reverse=True):
        station=r['id']; raw=r['raw'].strip()
        if station not in server.AIRPORTS:continue
        if re.match(r'^SPECI\b',raw,re.I):target=speci
        else:target=metar
        if station not in target:target[station]={'raw':raw,'utc':r['utc']}
    if not metar and not speci:
        raise RuntimeError('OGIMET sem METAR nem SPECI no período consultado')
    return metar,speci

def update_aviation():
    data=load('aviation.json')
    data.setdefault('metar',{});data.setdefault('speci',{});data.setdefault('taf',{})
    data['metar_source']='OGIMET getmetar'
    data['speci_source']='OGIMET getmetar'
    data['taf_source']='NOAA Aviation Weather Center'
    successes=0
    try:
        metar,speci=observation_data()
        data['metar']=merge_records(data['metar'],metar)
        data['speci']=merge_records(data['speci'],speci)
        data['metar_checked_utc']=data['speci_checked_utc']=stamp()
        successes+=1
    except Exception as exc:print('Aviso OGIMET METAR/SPECI:',exc,file=sys.stderr)
    try:
        taf=server.taf_data()
        if not taf:raise RuntimeError('NOAA devolveu lista TAF vazia')
        data['taf']=merge_records(data['taf'],taf)
        data['taf_checked_utc']=stamp()
        successes+=1
    except Exception as exc:print('Aviso NOAA TAF/AMD:',exc,file=sys.stderr)
    # O TAF AMD está no próprio relatório atual, quando houver emenda.
    # Não mantemos separadamente um AMD já substituído por um TAF normal.
    save('aviation.json',data)
    return successes

def update_synop():
    existing=load('synop.json')
    try:
        incoming=server.synop_data()
        if not any(s.get('latest_utc') for s in incoming.get('stations',[])):
            raise RuntimeError('Nenhuma estação trouxe observações')
        existing={'source':'OGIMET getsynop','stations':incoming['stations'],'checked_utc':stamp(),'decoder_version':6,'references_utc':incoming.get('references_utc',[]),'reference_utc':incoming.get('reference_utc')}
        save('synop.json',existing)
        return 1
    except Exception as exc:
        print('Aviso OGIMET SYNOP:',exc,file=sys.stderr)
        return 0

if __name__=='__main__':
    count=update_aviation()+update_synop()
    if count==0:
        print('Nenhuma fonte disponível; últimos relatórios mantidos.')
        # Sem falhar deliberadamente o workflow quando não há novas mensagens.
