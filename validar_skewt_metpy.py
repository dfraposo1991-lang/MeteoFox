#!/usr/bin/env python3
"""Auditoria independente do Skew-T MeteoFox contra MetPy.
Executar: pip install metpy numpy; python validar_skewt_metpy.py
Requer Node.js para executar o mesmo JS do navegador.
"""
import json, math, re, subprocess, csv, os
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from metpy.calc import surface_based_cape_cin, lcl, lfc, el, parcel_profile
from metpy.units import units

ROOT=Path(__file__).resolve().parent
html=(ROOT/'laboratorio.html').read_text(encoding='utf-8')
match=re.search(r'function thermodynamics\(group\)\{.*?(?=function fmtLevel\()',html,re.S)
if not match: raise RuntimeError('Motor termodinâmico não encontrado')
js=match.group(0)
def meteofx(rows):
    code=js+"\nconst rows="+json.dumps(rows)+";console.log(JSON.stringify(thermodynamics(rows)));"
    out=subprocess.run(['node','-e',code],capture_output=True,text=True,check=True)
    return json.loads(out.stdout)
def metpy(rows):
    r=sorted(rows,key=lambda x:-x['hpa'])
    p=np.array([x['hpa'] for x in r])*units.hPa
    t=np.array([x['temp_c'] for x in r])*units.degC
    td=np.array([x['dewpoint_c'] for x in r])*units.degC
    profile=parcel_profile(p,t[0],td[0])
    cape,cin=surface_based_cape_cin(p,t,td)
    plcl,_=lcl(p[0],t[0],td[0])
    plfc,_=lfc(p,t,td,parcel_temperature_profile=profile)
    pel,_=el(p,t,td,parcel_temperature_profile=profile)
    def pressure_or_none(q):
        v=float(q.to('hPa').magnitude)
        return v if math.isfinite(v) else None
    return {'cape':float(cape.magnitude),'cin':float(cin.magnitude),
            'lcl':float(plcl.magnitude),'lfc':pressure_or_none(plfc),'el':pressure_or_none(pel),
            'parcel500':float(np.interp(500,p.magnitude[::-1],profile.to('degC').magnitude[::-1]))}
PRESS=[1000,975,950,925,900,850,800,700,600,500,400,300,250,200]
def synthetic(kind):
    rows=[]
    for p in PRESS:
        z=7.5*math.log(1000/p)
        if kind=='stable': t=18-6*z+ (5 if p<=850 else 0);dep=8+z
        elif kind=='unstable': t=31-7.3*z;dep=2+0.5*z
        else: t=23-6*z+(8 if 850>=p>=700 else 0);dep=5+z
        rows.append({'hpa':p,'temp_c':t,'dewpoint_c':min(t,t-dep),'rh_percent':60})
    return rows
cases={k:synthetic(k) for k in ('stable','unstable','inversion')}
datafile=ROOT/'produtos_experimentais/previsao_ecmwf.json'
if datafile.exists():
    data=json.loads(datafile.read_text(encoding='utf-8'))
    for sounding in data.get('soundings',[]):
        for city,rows in sounding.get('cities',{}).items():
            cases[f"ECMWF_{city}_{sounding['step_h']}h"]=rows
failures=[]
records=[]
for name,rows in cases.items():
    try:
        a=meteofx(rows);b=metpy(rows)
        if a is None: raise ValueError('MeteoFox não produziu perfil')
        lcl_delta=abs(a['lcl']['p']-b['lcl'])
        parcel=a['samples']
        parcel500=min(parcel,key=lambda x:abs(x['p']-500))['t']
        parcel_delta=abs(parcel500-b['parcel500'])
        records.append({'perfil':name,'lcl_meteofox_hpa':round(a['lcl']['p'],2),'lcl_metpy_hpa':round(b['lcl'],2),
          'parcela500_delta_c':round(parcel_delta,3),'cape_meteofox_jkg':a['cape'],'cape_metpy_jkg':b['cape'],
          'cin_meteofox_jkg':a['cin'],'cin_metpy_jkg':b['cin'],
          'lfc_meteofox_hpa':a['lfc']['p'] if a['lfc'] else None,'lfc_metpy_hpa':b['lfc'],
          'el_meteofox_hpa':a['el']['p'] if a['el'] else None,'el_metpy_hpa':b['el'],
          'cape_completo':a['complete']})
        print(f"{name}: LCL Δ={lcl_delta:.1f} hPa, parcela 500 Δ={parcel_delta:.1f} °C, "
              f"CAPE MF={a['cape']} MetPy={b['cape']:.0f}, CIN MF={a['cin']} MetPy={b['cin']:.0f}")
        if lcl_delta>10 or parcel_delta>2: failures.append(f'{name}: trajetória/LCL divergente')
        if a['cape'] is not None and abs(a['cape']-b['cape'])>max(150,.3*abs(b['cape'])):
            failures.append(f'{name}: CAPE divergente')
        if a['cin'] is not None and abs(a['cin']-b['cin'])>max(100,.5*abs(b['cin'])):
            failures.append(f'{name}: CIN divergente')
        if a['cape'] is not None and (a['cape']<0 or a['lfc'] is None or a['el'] is None): failures.append(f'{name}: CAPE sem LFC/EL')
        # Divergências de LFC/EL são reportadas; não falham automaticamente quando
        # a escolha entre múltiplos cruzamentos difere entre algoritmos.
        if a['lfc'] and b['lfc'] and abs(a['lfc']['p']-b['lfc'])>75:
            print(f"AVISO {name}: LFC diverge {abs(a['lfc']['p']-b['lfc']):.0f} hPa")
        if a['el'] and b['el'] and abs(a['el']['p']-b['el'])>75:
            print(f"AVISO {name}: EL diverge {abs(a['el']['p']-b['el']):.0f} hPa")
        if a['cin'] is not None and a['cin']>0: failures.append(f'{name}: CIN positivo')
        if any(not math.isfinite(x['t']) or not math.isfinite(x['buoy']) for x in parcel):
            failures.append(f'{name}: valores não finitos')
    except Exception as exc: failures.append(f'{name}: {exc}')
report_dir=ROOT/'auditoria_skewt'
report_dir.mkdir(exist_ok=True)
if records:
    with (report_dir/'comparacao_metpy.csv').open('w',newline='',encoding='utf-8') as out:
        writer=csv.DictWriter(out,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'profiles_tested':len(records),
         'profiles_expected':len(cases),'failures':failures,
         'max_lcl_delta_hpa':max((abs(r['lcl_meteofox_hpa']-r['lcl_metpy_hpa']) for r in records),default=None),
         'max_parcel500_delta_c':max((r['parcela500_delta_c'] for r in records),default=None),
         'note':'Aprovação dentro de tolerâncias preliminares; não é certificação operacional.'}
(report_dir/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('Relatórios guardados em auditoria_skewt/comparacao_metpy.csv e resumo.json')
if failures:
    raise SystemExit('AUDITORIA FALHOU:\n'+'\n'.join(failures))
print('Auditoria numérica concluída. Critérios de tolerância são preliminares; não equivalem a certificação operacional.')
