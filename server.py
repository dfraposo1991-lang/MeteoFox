"""MeteoFox local proxy: OGIMET SYNOP/METAR, NOAA TAF fallback. Python 3 stdlib."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json, csv, io, re, time, threading

ROOT=Path(__file__).resolve().parent
STATIONS={'08532':'Sintra / BA1','08509':'Lajes / BA4','08540':'Monte Real / BA5','08534':'Montijo / BA6','08562':'Beja / BA11','08544':'Ovar / AM1','08552':'Tancos','08539':'Ota','08537':'Alverca','08506':'Horta','08513':'Ponta Delgada','08524':'Porto Santo','08530':'Cabo Carvoeiro','08535':'Lisboa / Geofísico','08536':'Lisboa / Portela','08538':'Sagres','08543':'Viana do Castelo','08545':'Porto / Pedras Rubras','08521':'MADEIRA / LPMA','08554':'FARO / LPFR'}
AIRPORTS=['LPFR','LPPT','LPAR','LPST','LPCS','LPMT','LPBJ','LPPR','LPOV','LPMR','LPLA','LPMA','LPPS','LPPD','LPHR','LPFL','LPPI','LPSJ','LPGR','LPCR','LPAZ']
CACHE={}; LOCK=threading.Lock()
def cached(key,ttl,fn):
    with LOCK:
        item=CACHE.get(key)
        if item and time.time()-item[0]<ttl:return item[1]
    val=fn()
    with LOCK:CACHE[key]=(time.time(),val)
    return val

def fetch(url):
    req=Request(url,headers={'User-Agent':'MeteoFox/4.0 educational weather viewer (+OGIMET attribution)','Accept':'text/plain,application/json,*/*'})
    with urlopen(req,timeout=22) as r:
        if r.status!=200:raise RuntimeError('HTTP '+str(r.status))
        data=r.read(3_000_000)
    return data.decode('utf-8','replace')

def ogimet(kind,hours=30,block=None):
    now=datetime.now(timezone.utc);begin=now-timedelta(hours=hours)
    args={'begin':begin.strftime('%Y%m%d%H%M'),'end':now.strftime('%Y%m%d%H%M'),'header':'yes'}
    if kind=='synop':args['block']=block or '085'
    else:args['icao']='LP'
    endpoint='getsynop' if kind=='synop' else 'getmetar'
    return fetch('https://www.ogimet.com/cgi-bin/'+endpoint+'?'+urlencode(args))

def parse_csv(text):
    rows=[]
    for row in csv.reader(io.StringIO(text)):
        if len(row)<7:continue
        sid=row[0].strip().strip('"')
        if not re.fullmatch(r'[A-Za-z0-9]{4,5}',sid):continue
        try: stamp=datetime(*[int(x) for x in row[1:6]],tzinfo=timezone.utc).isoformat().replace('+00:00','Z')
        except (ValueError,TypeError):continue
        rows.append({'id':sid,'utc':stamp,'raw':','.join(row[6:]).strip()})
    return rows

def precip(raw):
    # FM-12 section 1: group 6RRRtR only; iR in iRixhVV controls whether precip is included.
    tokens=raw.replace('=',' ').split()
    try:
        a=tokens.index('AAXX');start=a+3
    except ValueError:
        start=0
    sec=tokens[start:]
    cut=next((i for i,x in enumerate(sec) if re.match(r'^(222|333|444|555)',x)),len(sec))
    sec=sec[:cut]
    # Mandatory initial groups: iRixhVV, Nddff, 1snTTT, 2snTdTdTd, 3P0P0P0P0, 4PPPP, 5appp
    if len(sec)<2:return None
    ir=sec[0][0] if re.fullmatch(r'[0-4/][0-9/]{4}',sec[0]) else None
    if ir not in ('0','1','2'):return None
    group=next((x for x in sec[2:] if re.fullmatch(r'6[0-9/]{4}',x)),None)
    if not group or '/' in group:return None
    n=int(group[1:4]);tr=group[4];period={'1':6,'2':12,'3':18,'4':24,'5':1,'6':2,'7':3,'8':9,'9':15}.get(tr)
    if period is None:return None
    if n<=989:amount=float(n);trace=False
    elif n==990:amount=None;trace=True
    else:amount=round((n-990)/10,1);trace=False
    return {'mm':amount,'hours':period,'trace':trace}

def synop_data():
    records=parse_csv(ogimet('synop'))
    out={s:{'station':s,'name':n,'periods':{},'latest_utc':None} for s,n in STATIONS.items()}
    for r in sorted(records,key=lambda x:x['utc'],reverse=True):
        s=r['id']
        if s not in out:continue
        p=precip(r['raw'])
        if p and str(p['hours']) not in out[s]['periods']:
            out[s]['periods'][str(p['hours'])]={**p,'utc':r['utc']}
        if out[s]['latest_utc'] is None:out[s]['latest_utc']=r['utc']
    return {'source':'OGIMET getsynop','retrieved_utc':datetime.now(timezone.utc).isoformat(),'stations':list(out.values())}

def metar_data():
    records=parse_csv(ogimet('metar',hours=12))
    out={}
    for r in sorted(records,key=lambda x:x['utc'],reverse=True):
        if r['id'] in AIRPORTS and r['id'] not in out:out[r['id']]={'raw':r['raw'],'utc':r['utc']}
    return out

def taf_data():
    # OGIMET does not document a CSV gettaf endpoint. Use NOAA for raw TAF only, explicitly labelled.
    url='https://aviationweather.gov/api/data/taf?'+urlencode({'ids':','.join(AIRPORTS),'format':'json'})
    data=json.loads(fetch(url));out={}
    for r in data:
        sid=r.get('icaoId');raw=r.get('rawTAF')
        if sid in AIRPORTS and raw:out[sid]={'raw':raw,'utc':r.get('issueTime')}
    return out

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_GET(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/'):return super().do_GET()
        try:
            if path=='/api/synop':data=cached('synop',900,synop_data)
            elif path=='/api/aviation':
                met=cached('metar',600,metar_data)
                try:taf=cached('taf',900,taf_data);taf_source='NOAA Aviation Weather Center'
                except Exception:taf={};taf_source='indisponível'
                data={'metar':met,'taf':taf,'metar_source':'OGIMET getmetar','taf_source':taf_source}
            else:self.send_error(404);return
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception as exc:
            body=json.dumps({'error':'Fonte temporariamente indisponível','detail':str(exc)},ensure_ascii=False).encode()
            self.send_response(502);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

if __name__=='__main__':
    print('MeteoFox: http://localhost:8765');ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
