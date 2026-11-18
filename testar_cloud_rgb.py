#!/usr/bin/env python3
"""Diagnóstico não invasivo: catálogo OpenCharts e PNG Cloud RGB do ECMWF."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = 'https://charts.ecmwf.int/opencharts-api/v1/products/'
OUT = Path('diagnostico_cloud_rgb')
OUT.mkdir(exist_ok=True)
HEADERS = {'User-Agent': 'MeteoFox-CloudRGB-Diagnostic/1.0', 'Accept': 'application/json'}
TERMS = ('cloud rgb', 'cloud-rgb', 'cloud_rgb', 'cloudrgb', 'rgb cloud', 'rgb-cloud', 'rgb_cloud')

def fetch(url, *, max_bytes=25_000_000, accept=None):
    hdrs = dict(HEADERS)
    if accept:
        hdrs['Accept'] = accept
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=45) as response:
        final_url = response.url
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RuntimeError('Resposta excede o limite de segurança')
        return body, response.headers.get('Content-Type', ''), final_url

def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def diagnostic():
    report = {'tested_utc': datetime.now(timezone.utc).isoformat(), 'catalogue_url': API,
              'status': 'nao_confirmado', 'candidates': [], 'warnings': [], 'downloaded_png': None}
    try:
        raw, ct, _ = fetch(API, max_bytes=12_000_000)
        catalogue = json.loads(raw)
        if isinstance(catalogue, dict):
            products = catalogue.get('results') or catalogue.get('products') or catalogue.get('data')
        else:
            products = catalogue
        if not isinstance(products, list):
            raise ValueError('Estrutura inesperada do catálogo: ' + type(products).__name__)
        report['product_count'] = len(products)
        matches = []
        for p in products:
            if not isinstance(p, dict):
                continue
            name = str(p.get('name', ''))
            title = str(p.get('title', ''))
            description = str(p.get('description', ''))
            field = f'{name} {title} {description}'.lower()
            # Apenas identificar explicitamente Cloud RGB, não True Colour ou IR genérico.
            score = 3 if any(t in field for t in TERMS) else (1 if ('satellit' in field or 'simulat' in field or 'rgb' in field) else 0)
            if score:
                matches.append({'name': name, 'title': title, 'description': description[:300],
                                'product_url': p.get('product-url') or urllib.parse.urljoin(API, urllib.parse.quote(name) + '/'),
                                'cloud_rgb_explicit': score == 3})
        report['candidates'] = matches
        dump('catalogo_candidatos.json', matches)
        definite = [x for x in matches if x['cloud_rgb_explicit']]
        if not definite:
            report['status'] = 'cloud_rgb_nao_identificado_no_catalogo_publico'
            report['warnings'].append('A ausência no catálogo não prova que o produto não exista ou não possa ser licenciado.')
            return report
        for item in definite[:8]:
            url = item['product_url']
            if not (isinstance(url, str) and url.startswith('https://charts.ecmwf.int/')):
                item['error'] = 'URL de produto não permitida'; continue
            try:
                raw, ct, final_url = fetch(url, max_bytes=3_000_000)
                payload = json.loads(raw)
                dump('produto_' + re.sub(r'[^a-zA-Z0-9_-]', '_', item['name'])[:80] + '.json', payload)
                data = payload.get('data', {})
                link = data.get('link', {}).get('href')
                attrs = data.get('attributes', {})
                item['attributes'] = attrs
                item['license'] = payload.get('meta', {}).get('license')
                item['image_url'] = link
                if not isinstance(link, str) or not link.startswith('https://charts.ecmwf.int/'):
                    item['error'] = 'API não devolveu link de imagem HTTPS no domínio ECMWF'; continue
                content, ctype, _ = fetch(link, max_bytes=15_000_000, accept='image/png')
                if content[:8] != b'\x89PNG\r\n\x1a\n':
                    item['error'] = 'Resposta recebida não é PNG válido (assinatura incorreta)'; continue
                filename = 'cloud_rgb_teste.png'
                (OUT / filename).write_bytes(content)
                report['downloaded_png'] = filename
                report['status'] = 'png_cloud_rgb_descarregado_requer_validacao_visual'
                report['png_bytes'] = len(content)
                report['selected_product'] = item['name']
                report['product_attributes'] = attrs
                report['license'] = item.get('license')
                break
            except (urllib.error.URLError, ValueError, KeyError, RuntimeError, OSError) as exc:
                item['error'] = str(exc)[:400]
        if report['downloaded_png'] is None:
            report['status'] = 'produto_encontrado_mas_png_nao_descarregado'
        return report
    except Exception as exc:
        report['status'] = 'erro_consulta_api'
        report['warnings'].append(f'{type(exc).__name__}: {str(exc)[:500]}')
        return report

if __name__ == '__main__':
    result = diagnostic()
    dump('resultado.json', result)
    print('\n=== METEOFOX: DIAGNÓSTICO CLOUD RGB ECMWF ===')
    print('Estado:', result['status'])
    print('Produtos no catálogo:', result.get('product_count', 'não determinado'))
    print('Candidatos:', len(result['candidates']))
    for p in result['candidates'][:25]:
        print(' -', p['name'], '|', p['title'], '| Cloud RGB explícito:', p['cloud_rgb_explicit'])
    if result.get('selected_product'):
        print('Produto:', result['selected_product'])
        print('Metadados:', result.get('product_attributes'))
        print('Imagem:', result.get('downloaded_png'))
    for warning in result.get('warnings', []):
        print('Aviso:', warning)
    print('Relatório completo: diagnostico_cloud_rgb/resultado.json')
    # Não falhar o workflow por ausência de produto: relatório é a fonte da decisão.
