#!/usr/bin/env python3
"""MeteoFox: produção de 16 imagens de satélite simulado visível ECMWF.
Confere run/validade/área no JSON antes de publicar.
Rejeita o conjunto incompleto; workflow efetua commit apenas após 16 frames.
"""
import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from PIL import Image

API = 'https://charts.ecmwf.int/opencharts-api/v1/products/medium-simulated-vis/'
PROJECTION = 'opencharts_south_west_europe'
LAYER = 'sim_image_vis_ch2'
OUT = Path('data/satellite_vis')
STAGING = Path('data/.satellite_vis_preparacao')
HEADERS = {'User-Agent': 'MeteoFox-ECMWF-VIS/1.0 (rate-limited; CC-BY-4.0)', 'Accept': 'application/json'}

class RequestFailure(Exception):
    def __init__(self, status, url, body='', retry_after=''):
        super().__init__(f'HTTP {status}: {body[:250]}')
        self.status, self.url, self.body, self.retry_after = status, url, body, retry_after


def get_bytes(url, *, image=False, size_limit=8_000_000):
    """Aguarda e repete apenas falhas transitórias de rede e HTTP 5xx.

    Nunca repetir HTTP 429 (limite de pedidos) ou 400/404. Os tempos de
    espera são curtos e fixos, para não prolongar desnecessariamente o job.
    """
    if urlparse(url).hostname != 'charts.ecmwf.int' or not url.startswith('https://'):
        raise ValueError('URL não autorizado; apenas charts.ecmwf.int')
    headers = dict(HEADERS)
    if image:
        headers['Accept'] = 'image/png'
    req = Request(url, headers=headers)
    delays = (10, 25)  # total máximo 3 pedidos para falhas transitórias
    for attempt in range(len(delays) + 1):
        try:
            with urlopen(req, timeout=50) as response:
                content = response.read(size_limit + 1)
                if len(content) > size_limit:
                    raise ValueError('Resposta excedeu limite de tamanho')
                return content, response.headers.get('Content-Type', '')
        except HTTPError as e:
            try:
                body = e.read(1800).decode('utf-8', 'replace')
            except Exception:
                body = ''
            # Nunca insistir em pedidos rejeitados, sobretudo HTTP 429.
            if e.code not in (500, 502, 503, 504) or attempt == len(delays):
                raise RequestFailure(e.code, url, body, e.headers.get('Retry-After', '')) from e
            print(f'HTTP {e.code} transitório no ECMWF; tentativa {attempt + 2}/3 após {delays[attempt]} s',
                  flush=True)
        except (URLError, ConnectionError, TimeoutError) as e:
            if attempt == len(delays):
                raise
            print(f'Ligação ECMWF interrompida ({type(e).__name__}); '
                  f'tentativa {attempt + 2}/3 após {delays[attempt]} s', flush=True)
        time.sleep(delays[attempt])
    raise AssertionError('Loop de tentativas terminou inesperadamente')


def iso(dt): return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def compact(dt): return dt.astimezone(timezone.utc).strftime('%Y%m%d%H%M')


def params_for(base, step, fmt='iso', layer=True):
    valid = base + timedelta(hours=step)
    values = {'base_time': iso(base) if fmt == 'iso' else compact(base),
              'valid_time': iso(valid) if fmt == 'iso' else compact(valid),
              'projection': PROJECTION}
    if layer: values['layer_name'] = LAYER
    return values


def parse_description(desc):
    # Descrição ECMWF inclui base/valid/área; não gerar metadados a partir da hora do PC
    m = re.search(r'Base\s*time\s*:\s*(.*?)\s+Valid\s*time\s*:\s*(.*?)\s*\(\s*\+(\d+)h\s*\)\s+Area\s*:\s*(.*?)\s+Channel\s*:', desc, re.I)
    if not m: raise ValueError('A descrição ECMWF não inclui Run, validade, prazo e área de forma reconhecível')
    fmt = '%a %d %b %Y %H UTC'
    bt = datetime.strptime(m.group(1).strip(), fmt).replace(tzinfo=timezone.utc)
    vt = datetime.strptime(m.group(2).strip(), fmt).replace(tzinfo=timezone.utc)
    return bt, vt, int(m.group(3)), m.group(4).strip()


# Fixed geometry derived from the stable +24..54h source chart layout.
SOURCE_SIZE = (2000, 1800)
CROP_BOX = (11, 248, 1989, 1237)
FRAME_SIZE = (1978, 989)

def crop_png(data):
    with Image.open(io.BytesIO(data)) as source:
        if source.size != SOURCE_SIZE:
            raise ValueError(f'Geometria ECMWF alterada: {source.size}; esperado {SOURCE_SIZE}')
        im = source.convert('RGB').crop(CROP_BOX)
        if im.size != FRAME_SIZE:
            raise ValueError('Dimensões de recorte inválidas')
        dest = io.BytesIO()
        im.save(dest, format='PNG', optimize=True)
    return dest.getvalue(), list(CROP_BOX), list(SOURCE_SIZE)

def geometry_valid(manifest):
    try:
        if manifest.get('crop_box') != list(CROP_BOX):
            return False
        for step in range(9,55,3):
            with Image.open(OUT / f'VIS_{step:03d}.png') as im:
                if im.size != FRAME_SIZE:
                    return False
        return True
    except (OSError, ValueError):
        return False


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base-time', help='Run em UTC YYYYMMDDHHMM; omitir para selecionar um Run com pelo menos 9 horas')
    p.add_argument('--max-frames', type=int, default=16, help='Producao exige exatamente 16 frames')
    a=p.parse_args()
    if a.max_frames != 16: p.error('Producao exige exatamente 16 frames')
    if STAGING.exists():
        import shutil
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True, exist_ok=True)
    if a.base_time:
        try: base=datetime.strptime(a.base_time,'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
        except ValueError: p.error('--base-time inválido (YYYYMMDDHHMM)')
    else:
        dt=datetime.now(timezone.utc)-timedelta(hours=9)
        base=dt.replace(hour=dt.hour-dt.hour%6,minute=0,second=0,microsecond=0)
    # Nunca tentar substituir uma série mais recente por um ciclo mais antigo.
    existing_manifest = OUT / 'manifest.json'
    if existing_manifest.exists():
        try:
            existing = json.loads(existing_manifest.read_text(encoding='utf-8'))
            existing_run = datetime.fromisoformat(existing['run_utc'].replace('Z', '+00:00'))
            if (base < existing_run or (base == existing_run and geometry_valid(existing))) and [frame.get('step_h') for frame in existing.get('frames', [])] == list(range(9, 55, 3)):
                print('Conjunto já atualizado ou mais recente: ' + iso(existing_run) + '; pedido: ' + iso(base), flush=True)
                return 0
        except (OSError, KeyError, ValueError, TypeError):
            pass
    report={'created_utc':iso(datetime.now(timezone.utc)),'product':'medium-simulated-vis',
        'requested_run_utc':iso(base),'projection':PROJECTION,'layer_name':LAYER,
        'target_steps_h':list(range(9,55,3)),'attempts':[], 'frames':[], 'completed':False,
        'stop_reason':None, 'source_credit':'© ECMWF · CC BY 4.0',
        'note':'Publicar somente apos validar todos os passos (+9 a +54 h).'}
    def log_failure(exc, *, name, step):
        record={'name':name,'step_h':step,'error':str(exc)}
        if isinstance(exc,RequestFailure):
            record.update({'http_status':exc.status,'url':exc.url,'server_response_excerpt':exc.body[:1500], 'retry_after':exc.retry_after})
        report['attempts'].append(record)
        print(f'[+{step:02d}] {name}: {exc}',flush=True)
        return record
    def query(base,step,fmt,layer):
        params=params_for(base,step,fmt,layer)
        url=API+'?'+urlencode(params)
        body,ctype=get_bytes(url)
        if 'json' not in ctype.lower(): raise ValueError(f'Resposta não é JSON: {ctype}')
        obj=json.loads(body)
        d=obj.get('data') or {};attrs=d.get('attributes') or {}
        desc=attrs.get('description') or ''
        bt,vt,actual_step,area=parse_description(desc)
        if bt!=base or vt!=base+timedelta(hours=step) or actual_step!=step:
            raise ValueError(f'Datas diferentes do pedido: {desc}')
        if not all(tok in re.sub(r'[^a-z]','',area.lower()) for tok in ('south','west','europe')):
            raise ValueError(f'Área inesperada: {area}')
        href=(d.get('link') or {}).get('href','')
        if not href: raise ValueError('Resposta JSON sem link de imagem')
        return {'run_utc':iso(bt),'valid_utc':iso(vt),'step_h':step,'area':area,'description':desc,'png_url':href,'licence':(obj.get('meta') or {}).get('licence')}, url
    try:
        # Testar primeiro o formato oficial ISO; em caso de 400, tentar UMA variante compacta.
        variants=[('iso',True),('iso',False),('compact',True)]
        chosen=None; first=None
        for fmt,layer in variants:
            try:
                first,query_url=query(base,9,fmt,layer)
                chosen=(fmt,layer)
                report['attempts'].append({'name':'probe_ok','step_h':9,'format':fmt,'layer_name_included':layer,'query_url':query_url})
                print(f'Parâmetros aceites: {fmt}; layer_name={layer}',flush=True)
                break
            except RequestFailure as exc:
                log_failure(exc,name=f'probe_{fmt}_layer_{layer}',step=9)
                if exc.status==429:
                    report['stop_reason']='Limite HTTP 429; interrompido imediatamente; aguardar período indicado pelo servidor'
                    break
                if exc.status!=400:
                    report['stop_reason']=f'Erro HTTP {exc.status}; interrompido sem insistir'
                    break
            except (ValueError,URLError,TimeoutError,OSError) as exc:
                log_failure(exc,name=f'probe_{fmt}_layer_{layer}',step=9)
                report['stop_reason']='Resposta inesperada, sem continuar pedidos';break
            time.sleep(5)
        if chosen is None:
            if not report['stop_reason']:report['stop_reason']='Nenhum dos três formatos de pedido foi aceite no +9 h'
            return 1
        seen=set()
        for step in range(9,55,3):
            try:
                result=first if step==9 else query(base,step,*chosen)[0]
                blob,ctype=get_bytes(result['png_url'],image=True)
                if not blob.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError(f'Imagem não é PNG válido: {ctype}')
                digest=hashlib.sha256(blob).hexdigest()
                if digest in seen:raise ValueError('A API devolveu PNG idêntico a outro prazo')
                seen.add(digest)
                cropped,rect,original_size=crop_png(blob)
                filename=f'VIS_{step:03d}.png'
                (STAGING/filename).write_bytes(cropped)
                result.update({'file':filename,'original_sha256':digest,'original_dimensions':original_size,'crop_box':rect,'cropped_bytes':len(cropped)})
                report['frames'].append(result)
                print(f'[+{step:02d}] OK | {result["run_utc"]} -> {result["valid_utc"]} | {result["area"]}',flush=True)
            except RequestFailure as exc:
                log_failure(exc,name='frame',step=step)
                report['stop_reason']='Limite HTTP 429: paragem imediata' if exc.status==429 else f'Erro HTTP {exc.status} no passo +{step}h'
                break
            except (ValueError,URLError,TimeoutError,OSError) as exc:
                log_failure(exc,name='frame',step=step)
                report['stop_reason']=f'Erro de verificação no +{step}h'
                break
            if step < 54:time.sleep(5)
        report['completed']=len(report['frames'])==a.max_frames
        if report['completed']:
            manifest={'product':report['product'],'projection':PROJECTION,'layer':LAYER,
                'run_utc':iso(base),'credit':'© ECMWF · CC BY 4.0',
                'crop_box':list(CROP_BOX),'width':FRAME_SIZE[0],'height':FRAME_SIZE[1],
                'frames':[{'file':r['file'],'step_h':r['step_h'],'run_utc':r['run_utc'],'valid_utc':r['valid_utc']} for r in report['frames']]}
            manifest['generated_utc'] = iso(datetime.now(timezone.utc))
            (STAGING/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'SUCESSO: {len(report["frames"])} imagens verificadas.',flush=True)
        return 0 if report['completed'] else 1
    finally:
        (STAGING/'relatorio_producao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['completed']:
            import shutil
            if OUT.exists(): shutil.rmtree(OUT)
            STAGING.rename(OUT)
        else:
            print('Conjunto incompleto: imagens antigas preservadas; nenhum commit sera efetuado.', flush=True)

if __name__=='__main__': sys.exit(main())
