"""MeteoFox local proxy: OGIMET SYNOP/METAR, NOAA TAF fallback. Python 3 stdlib."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json, csv, io, re, time, threading

ROOT=Path(__file__).resolve().parent
STATIONS={'08532':'Sintra / BA1','08509':'Lajes / BA4','08540':'Monte Real / BA5','08534':'Montijo / BA6','08561':'Beja / BA11','08562':'Beja','08544':'Ovar / AM1','08552':'Tancos','08539':'Ota','08537':'Alverca','08506':'Horta','08512':'Ponta Delgada','08524':'Porto Santo','08531':'Cabo Carvoeiro','08535':'Lisboa / Geofísico','08536':'Lisboa / Portela','08533':'Sagres','08551':'Viana do Castelo','08545':'Porto / Pedras Rubras','08521':'MADEIRA / LPMA','08554':'FARO / LPFR','08558':'Évora','08560':'Viseu'}
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

def precip_groups(raw):
    tokens=raw.replace('=',' ').split()
    if 'AAXX' not in tokens:return []
    sec=tokens[tokens.index('AAXX')+3:]
    if len(sec)<2:return []
    ir=sec[0][0]
    sections={1:[],3:[]}; section=1
    for token in sec[2:]:
        if token in ('333','444','555') or re.fullmatch(r'222[0-9/]{2}',token):
            section=3 if token=='333' else 0
            continue
        if section in sections:sections[section].append(token)
    # Portuguese reports use a radiation value immediately after each 55 group.
    # Consume the supplementary group before interpreting precipitation.
    filtered=[]
    skip=False
    for g in sections[3]:
        if skip:
            skip=False
            if re.fullmatch(r'[0-6][0-9/]{4}',g) and not g.startswith('55'):
                continue
        if re.fullmatch(r'55[0-9/]{3}',g):
            skip=True
            continue
        filtered.append(g)
    sections[3]=filtered
    out=[]
    for section in (1,3):
        if (section==1 and ir not in ('0','1')) or (section==3 and ir not in ('0','2')):continue
        for g in sections[section]:
            if re.fullmatch(r'6[0-9]{4}',g):
                h={'1':6,'2':12,'3':18,'4':24,'5':1,'6':2,'7':3,'8':9,'9':15}.get(g[4])
                if h is None:continue
                n=int(g[1:4])
                out.append({'mm':None if n==990 else float(n) if n<990 else (n-990)/10,'hours':h,'trace':n==990,'method':'reported','group':g,'section':section})
    for g in sections[3]:
        if re.fullmatch(r'7[0-9]{4}',g):
            n=int(g[1:])
            if n<=9999:out.append({'mm':None if n==9999 else n/10,'hours':24,'trace':n==9999,'lower_bound':n==9998,'method':'reported','group':g,'section':3})
    return out

def precip(raw):
    return next(iter(precip_groups(raw)),None)

def accumulate(records, reference=None):
    # Exact contiguous intervals only. Never infer duration from iR=3 alone.
    edges={}
    for end,p in records:
        start=end-timedelta(hours=p['hours'])
        edges.setdefault(end,{}).setdefault(start,p)
    result={}
    for end in ([reference] if reference is not None else sorted(edges,reverse=True)):
        for h in (6,12,24):
            if str(h) in result:continue
            start=end-timedelta(hours=h)
            def path(t):
                if t==start:return []
                for prev,p in sorted(edges.get(t,{}).items()):
                    if prev<start:continue
                    tail=path(prev)
                    if tail is not None:return [p]+tail
                return None
            direct=edges.get(end,{}).get(start)
            parts=[direct] if direct else path(end)
            if not parts:continue
            if direct:p=dict(direct)
            else:
                total=round(sum(x['mm'] or 0 for x in parts),1)
                trace=any(x['trace'] for x in parts)
                p={'hours':h,'mm':None if trace and total==0 else total,'trace':trace and total==0,'contains_trace':trace,'method':'calculated','components':len(parts)}
            result[str(h)]={**p,'utc':end.isoformat().replace('+00:00','Z')}
    # Nested intervals ending at the same time must be monotonic.
    for a,b in ((6,12),(6,24),(12,24)):
        x,y=result.get(str(a)),result.get(str(b))
        if x and y and x['utc']==y['utc'] and not y.get('lower_bound') and (x.get('mm') or 0)>(y.get('mm') or 0)+0.5:
            x['suspect']=y['suspect']=True
    return result

def synop_data():
    records=parse_csv(ogimet('synop',hours=48))
    out={s:{'station':s,'name':n,'periods':{},'latest_utc':None,'reports':0,'dry_reports':0} for s,n in STATIONS.items()}
    intervals={s:[] for s in out}
    for r in sorted(records,key=lambda x:x['utc'],reverse=True):
        s=r['id']
        if s not in out:continue
        st=out[s];st['reports']+=1
        if st['latest_utc'] is None:st['latest_utc']=r['utc']
        tokens=r['raw'].split()
        if 'AAXX' in tokens:
            i=tokens.index('AAXX')+3
            if i<len(tokens) and tokens[i].startswith('3'):st['dry_reports']+=1
        end=datetime.fromisoformat(r['utc'].replace('Z','+00:00'))
        intervals[s].extend((end,p) for p in precip_groups(r['raw']))
    # Common UTC reference: latest observed whole hour across the network.
    latest=max((st['latest_utc'] for st in out.values() if st['latest_utc']),default=None)
    reference=datetime.fromisoformat(latest.replace('Z','+00:00')).replace(minute=0,second=0,microsecond=0) if latest else None
    for s,st in out.items():st['periods']=accumulate(intervals[s],reference) if reference else {}
    return {'source':'OGIMET getsynop','reference_utc':reference.isoformat().replace('+00:00','Z') if reference else None,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'stations':list(out.values())}

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
