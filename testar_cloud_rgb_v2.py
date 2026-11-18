#!/usr/bin/env python3
"""Diagnóstico não intrusivo de produtos ECMWF OpenCharts.
Não presume que Cloud RGB possa ser descarregado por acesso público.
"""
import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://charts.ecmwf.int'
URLS = {
    'catalogo_geral': BASE + '/opencharts-api/v1/products/',
    'infravermelho_simulado': BASE + '/opencharts-api/v1/products/medium-simulated-ir/',
    'vapor_agua_simulado': BASE + '/opencharts-api/v1/products/medium-simulated-wv/',
    'pagina_infravermelho': BASE + '/products/medium-simulated-ir',
    'pagina_cloud_rgb_candidato': BASE + '/products/medium-simulated-cloud-rgb',
}
# Nomes exploratórios; os resultados NÃO demonstram que o produto exista.
CANDIDATES = [
    'medium-simulated-cloud-rgb', 'medium-simulated-rgb',
    'medium-cloud-rgb', 'medium-simulated-visible',
    'medium-simulated-vis',
]
for name in CANDIDATES:
    URLS['api_candidato_' + name] = BASE + '/opencharts-api/v1/products/' + name + '/'

def check(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'MeteoFox-CloudRGB-Diagnostic/2.0',
        'Accept': 'application/json,text/html,image/png,*/*',
    })
    try:
        with urllib.request.urlopen(req, timeout=18) as resp:
            body = resp.read(200_000)
            ct = resp.headers.get('Content-Type', '')
            result = {'http_status': resp.status, 'final_url': resp.geturl(), 'content_type': ct,
                      'bytes_examined': len(body)}
            if 'json' in ct:
                try:
                    obj = json.loads(body)
                    result['json_type'] = type(obj).__name__
                    result['json_keys'] = list(obj)[:35] if isinstance(obj, dict) else []
                    text = json.dumps(obj, ensure_ascii=False)
                except (ValueError, UnicodeError):
                    text = body.decode('utf-8', errors='replace')
            else:
                text = body.decode('utf-8', errors='replace')
            words = re.findall(r'[^\s"<>]{0,90}(?:cloud.?rgb|simulated.?rgb|true.?colou?r|simulated.?vis)[^\s"<>]{0,90}', text, flags=re.I)
            result['relevant_matches'] = list(dict.fromkeys(words))[:25]
            return result
    except urllib.error.HTTPError as e:
        return {'http_status': e.code, 'error': str(e), 'final_url': e.geturl()}
    except Exception as e:
        return {'error': type(e).__name__ + ': ' + str(e)}

results = {name: check(url) for name, url in URLS.items()}
found = [name for name, result in results.items() if result.get('http_status') == 200 and ('rgb' in name or result.get('relevant_matches'))]
report = {
    'tested_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
    'purpose': 'Verificar endpoints e referências a Cloud RGB; não prova descarga de PNG',
    'results': results,
    'potential_leads': found,
    'verified_cloud_rgb_png': False,
    'conclusion': 'A confirmar: uma resposta HTTP 200 ou referência RGB não basta; falta verificar um PNG atual e os direitos de utilização.',
}
Path('diagnostico_cloud_rgb_v2.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
for name, r in results.items():
    print(f'{name}: HTTP {r.get("http_status", "?")} {r.get("error", "")}', flush=True)
    if r.get('relevant_matches'):
        print('  referencias: ' + ', '.join(r['relevant_matches'][:4]), flush=True)
print('\nRelatorio: diagnostico_cloud_rgb_v2.json')
print('ATENÇÃO: nenhum PNG Cloud RGB foi validado por este diagnostico.')
