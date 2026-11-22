#!/usr/bin/env python3
"""MeteoFox: discover and safely validate a NIGHT MICROPHYSICS/Fog RGB WMS layer.
Does not publish imagery or modify the established GeoColour animation.
Never substitute stale imagery or fabricate satellite timestamps.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json
import hashlib
import re
import time
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

WMS = 'https://view.eumetsat.int/geoserver/wms'
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'satellite_fog_status.json'
HEADERS = {'User-Agent': 'MeteoFox-fog-validation/1.0', 'Accept': 'application/xml,*/*'}
NOW = datetime.now(timezone.utc)

def fetch(url, limit=16_000_000, timeout=30):
    # A EUMETView devolve ocasionalmente 502/503/504 em GetMap.
    # Repetir transientes, nunca declarar produto validado sem PNG real.
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=HEADERS), timeout=timeout) as reply:
                data = reply.read(limit + 1)
                if len(data) > limit: raise ValueError('WMS response exceeds safety limit')
                return data
        except (HTTPError, URLError, TimeoutError) as exc:
            transient = not isinstance(exc, HTTPError) or exc.code in (429, 500, 502, 503, 504)
            if not transient or attempt == 2: raise
            time.sleep(2 * (attempt + 1))

def local(tag):
    return tag.rsplit('}', 1)[-1]

def child(node, tag):
    return next((c for c in node if local(c.tag) == tag), None)

def descendants(root, tag):
    return (n for n in root.iter() if local(n.tag) == tag)

def direct_text(node, tag):
    sub = child(node, tag)
    return (sub.text or '').strip() if sub is not None else ''

def parse_time(text):
    """Accept explicit instants and WMS ISO-8601 start/end/period, sampling recent end."""
    results = []
    for part in (text or '').split(','):
        token = part.strip()
        if not token: continue
        if '/' in token:
            # Take listed end only; never invent intermediate times.
            token = token.split('/')[1].strip()
        if not re.match(r'^\d{4}-\d\d-\d\dT', token): continue
        try:
            d = datetime.fromisoformat(token.replace('Z','+00:00'))
            if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
            results.append(d.astimezone(timezone.utc))
        except ValueError: pass
    return results

def load_reference():
    try:
        data=json.loads((ROOT/'data'/'satellite_times.json').read_text(encoding='utf-8'))
        times=[datetime.fromisoformat(s.replace('Z','+00:00')) for s in data.get('times_utc',[])]
        return sorted(t for t in times if NOW-t <= timedelta(hours=4) and t<=NOW+timedelta(minutes=5))
    except (ValueError, OSError): return []

def main():
    out={'checked_utc':NOW.isoformat().replace('+00:00','Z'),
         'ready':False, 'source':'EUMETSAT EUMETView WMS GetCapabilities',
         'geo_layer':'mtg_fd:rgb_geocolour','fog_layer':None,
         'matching_time_utc':None,'reason':'Validation has not finished',
         'candidate_layers':[], 'request_budget':{'capabilities':1,'sample_tiles':1}}
    try:
        params=urlencode({'service':'WMS','version':'1.1.1','request':'GetCapabilities'})
        root=ET.fromstring(fetch(WMS+'?'+params,timeout=35))
        # GeoServer may declare Time on an ancestor Layer rather than each
        # named product. Gather each explicit time dimension where it occurs.
        for layer in descendants(root,'Layer'):
            nm=direct_text(layer,'Name')
            if nm in ('mtg_fd:rgb_geocolour','mtg_fd:rgb_fog'):
                dims=[{'name':x.get('name'), 'raw_preview':(x.text or '')[:400]}
                     for x in layer if local(x.tag) in ('Dimension','Extent')]
                out.setdefault('wms_dimensions',{})[nm]=dims[:5]
        candidates=[]
        for node in descendants(root,'Layer'):
            name=direct_text(node,'Name')
            title=direct_text(node,'Title')
            if not name: continue
            title_low=title.lower()
            name_low=name.lower()
            if not (name.startswith('mtg_fd:') or name.startswith('msg_fes:')): continue
            if not ('fog' in name_low or 'night' in name_low or
                    'low cloud' in title_low or 'night microphysics' in title_low): continue
            dimension=next((x for x in node if local(x.tag) in ('Extent','Dimension') and
                            (x.get('name','').lower() == 'time')),None)
            times=parse_time(dimension.text if dimension is not None else '')
            last=max(times) if times else None
            candidates.append({'name':name,'title':title,
              'last_listed_utc':last.isoformat().replace('+00:00','Z') if last else None,
              'is_mtg':name.startswith('mtg_fd:')})
        out['candidate_layers']=candidates[:20]
        if not candidates:
            out['reason']='No MTG/European MSG Fog or Night Microphysics layer found in WMS capabilities'
        else:
            # Require the same satellite generation as existing GeoColour for geo-registration;
            # never silently combine MSG+MTG, which have different sampling geometries.
            mtg=[x for x in candidates if x['is_mtg']]
            reference=load_reference()
            matching=reference[-1] if reference else None
            # O Fog pode ter um atraso de publicação diferente do GeoColour.
            # Escolher um instante realmente anunciado por ambos os produtos.
            if selected and selected['last_listed_utc'] and reference:
                fog_end=datetime.fromisoformat(selected['last_listed_utc'].replace('Z','+00:00'))
                matching=next((t for t in reversed(reference) if t<=fog_end),None)
            selected=next((c for c in mtg if 'fog' in c['name'].lower()),None)
            out['time_basis']='GeoColour reference time; Fog WMS tested with explicit TIME'
            if not mtg:
                out['reason']='Fog found only on another satellite generation; not aligned with MTG GeoColour'
            elif selected is None:
                out['reason']='No confirmed Fog RGB in the MTG family'
            elif matching is None or abs((NOW-matching).total_seconds())>90*60:
                out['reason']='GeoColour reference timestamps are absent or too old'
            elif selected['last_listed_utc'] and (datetime.fromisoformat(selected['last_listed_utc'].replace('Z','+00:00'))-matching).total_seconds()>3*3600:
                out['reason']='MTG Fog time extent does not agree with GeoColour'
            else:
                # Probe a single modest-sized tile; do not start a bulk download.
                params={
                  'service':'WMS','version':'1.1.1','request':'GetMap',
                  'layers':selected['name'],'styles':'','format':'image/png',
                  'transparent':'true','srs':'EPSG:4326','bbox':'-11,35,4,45',
                  'width':'128','height':'128',
                  'time':matching.isoformat().replace('+00:00','Z')}
                sample=fetch(WMS+'?'+urlencode(params),limit=650_000,timeout=25)
                if not sample.startswith(b'\x89PNG\r\n\x1a\n') or len(sample)<900:
                    out['reason']='WMS did not return a valid PNG for the selected UTC time'
                else:
                    out['ready']=True
                    out['fog_layer']=selected['name']
                    out['matching_time_utc']=matching.isoformat().replace('+00:00','Z')
                    out['reason']='MTG Fog RGB discovered; explicit-time WMS sample returned PNG; frame-by-frame availability still to validate'
                    out['sample_test']={'time_utc':out['matching_time_utc'],
                      'bytes':len(sample),'sha256':hashlib.sha256(sample).hexdigest()}
                    # Compare actual image bytes for two requested UTC instants.
                    # Distinct hashes show that Fog WMS responds to TIME;
                    # identical hashes remain inconclusive (e.g. slow evolution).
                    previous=reference[-2] if len(reference)>1 else None
                    if previous is not None and (matching-previous).total_seconds()<=20*60:
                        p2=dict(params)
                        p2['time']=previous.isoformat().replace('+00:00','Z')
                        other=fetch(WMS+'?'+urlencode(p2),limit=650_000,timeout=25)
                        valid=other.startswith(b'\x89PNG\r\n\x1a\n') and len(other)>900
                        out['time_pair_test']={'earlier_utc':p2['time'],
                          'later_utc':out['matching_time_utc'],
                          'earlier_is_png':valid,'earlier_bytes':len(other),
                          'different_pixels':valid and hashlib.sha256(sample).digest()!=hashlib.sha256(other).digest(),
                          'later_is_png':True}
                        if not valid:
                            out['ready']=False
                            out['reason']='Fog WMS did not return an earlier valid paired frame'
                        elif out['time_pair_test']['different_pixels']:
                            out['reason']='Fog WMS returned differing PNGs for two GeoColour UTC times; exact source acquisition stamps remain unproven'
                        else:
                            out['reason']='Fog WMS returned the same PNG for adjacent GeoColour UTC times; time alignment remains unproven'
    except Exception as e:
        out['ready']=False
        out['reason']='Fog WMS validation unavailable: '+str(e)[:250]
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
