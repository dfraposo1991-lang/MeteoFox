#!/usr/bin/env python3
"""Auditoria independente do Skew-T MeteoFox contra MetPy.
Executar: pip install metpy numpy; python validar_skewt_metpy.py
Requer Node.js para executar o mesmo JS do navegador.
"""
import json, math, re, subprocess
from pathlib import Path
import numpy as np
from metpy.calc import surface_based_cape_cin, lcl, parcel_profile
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
    return {'cape':float(cape.magnitude),'cin':float(cin.magnitude),
            'lcl':float(plcl.magnitude),'parcel500':float(np.interp(500,p.magnitude[::-1],profile.to('degC').magnitude[::-1]))}
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
    for sounding in data.get('soundings',[])[:3]:
        for city,rows in sounding.get('cities',{}).items():
            cases[f"ECMWF_{city}_{sounding['step_h']}h"]=rows
failures=[]
for name,rows in cases.items():
    try:
        a=meteofx(rows);b=metpy(rows)
        if a is None: raise ValueError('MeteoFox não produziu perfil')
        lcl_delta=abs(a['lcl']['p']-b['lcl'])
        parcel=a['samples']
        parcel500=min(parcel,key=lambda x:abs(x['p']-500))['t']
        parcel_delta=abs(parcel500-b['parcel500'])
        print(f"{name}: LCL Δ={lcl_delta:.1f} hPa, parcela 500 Δ={parcel_delta:.1f} °C, "
              f"CAPE MF={a['cape']} MetPy={b['cape']:.0f}, CIN MF={a['cin']} MetPy={b['cin']:.0f}")
        if lcl_delta>15 or parcel_delta>3: failures.append(f'{name}: trajetória/LCL divergente')
        if a['cape'] is not None and b['cape']>100 and abs(a['cape']-b['cape'])>max(200,.4*b['cape']):
            failures.append(f'{name}: CAPE divergente')
        if a['cin'] is not None and abs(b['cin'])>50 and abs(a['cin']-b['cin'])>max(150,.6*abs(b['cin'])):
            failures.append(f'{name}: CIN divergente')
        if any(not math.isfinite(x['t']) or not math.isfinite(x['buoy']) for x in parcel):
            failures.append(f'{name}: valores não finitos')
    except Exception as exc: failures.append(f'{name}: {exc}')
if failures:
    raise SystemExit('AUDITORIA FALHOU:\n'+'\n'.join(failures))
print('Auditoria numérica concluída. Critérios de tolerância são preliminares; não equivalem a certificação operacional.')
