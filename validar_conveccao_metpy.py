#!/usr/bin/env python3
"""Auditoria cinemática independente: JS MeteoFox versus MetPy.
Testa perfis sintéticos controlados e recusa resultados sem cobertura vertical.
"""
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from metpy.calc import bunkers_storm_motion, bulk_shear, storm_relative_helicity
from metpy.units import units

ROOT = Path(__file__).resolve().parent
MODULE = ROOT / "meteofox_conveccao.js"
OUT = ROOT / "auditoria_skewt" / "conveccao_metpy.json"
KT = 0.514444444

def run_js(rows, samples):
    code = """
const fs=require('fs'),vm=require('vm');
const ctx={window:{},document:{getElementById:()=>null},console};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const result=ctx.window.MeteoFoxSevere.analyze(JSON.parse(process.argv[2]),{samples:JSON.parse(process.argv[3])});
console.log(JSON.stringify(result));
"""
    proc = subprocess.run(["node", "-e", code, str(MODULE), json.dumps(rows), json.dumps(samples)],
                          capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)

def make_profile(name, max_height=7500):
    heights = np.arange(0, max_height+1, 250, dtype=float)
    if name == "veering":
        u = 3 + .0030*heights + 3*np.sin(heights/2300)
        v = -5 + .0018*heights
    elif name == "backing":
        u = 14 - .0021*heights
        v = -8 + .0032*heights + 2*np.cos(heights/1800)
    elif name == "straight":
        u = 2 + .004*heights
        v = np.full_like(heights, -7)
    else:
        raise ValueError(name)
    p = 1000*np.exp(-heights/8100)
    rows = []
    for z, pressure, uu, vv in zip(heights, p, u, v):
        speed = math.hypot(uu, vv)/KT
        direction = (math.degrees(math.atan2(-uu, -vv))+360)%360
        rows.append({"hpa":float(pressure),"wind_kt":speed,"wind_dir_deg":direction})
    samples = [{"p":float(pressure),"z":float(z)} for pressure,z in zip(p,heights)]
    return heights,p,u,v,rows,samples

def reference(heights,p,u,v):
    h=heights*units.meter
    pressure=p*units.hPa
    uu=u*units("m/s")
    vv=v*units("m/s")
    right,left,_=bunkers_storm_motion(pressure,uu,vv,h)
    out={}
    for km in (1,3,6):
        du,dv=bulk_shear(pressure,uu,vv,height=h,depth=km*units.km)
        out[f"shear{km}"]=float(np.hypot(du.to("m/s").magnitude,dv.to("m/s").magnitude)/KT)
    for km in (1,3):
        positive,negative,total=storm_relative_helicity(h,uu,vv,depth=km*units.km,
                                                         storm_u=right[0],storm_v=right[1])
        out[f"srh{km}"]=float(total.to("meter**2/second**2").magnitude)
    out["right"]=tuple(float(v.to("m/s").magnitude) for v in right)
    out["left"]=tuple(float(v.to("m/s").magnitude) for v in left)
    return out

def main():
    failures=[]
    results=[]
    for name in ("veering","backing","straight"):
        heights,p,u,v,rows,samples=make_profile(name)
        actual=run_js(rows,samples)
        expected=reference(heights,p,u,v)
        deltas={}
        for key in ("shear1","shear3","shear6","srh1","srh3"):
            delta=abs(actual[key]-expected[key]) if actual.get(key) is not None else float("inf")
            deltas[key]=delta
            tol=0.2 if key.startswith("shear") else 2.0
            if delta>tol:failures.append(f"{name}: {key}: diferença {delta:.3f} > {tol}")
        for side in ("right","left"):
            v=actual.get("motionRight") if side=="right" else None
            if side=="left":
                # O módulo expõe direção/velocidade para ambos os movimentos.
                motion=actual.get("left")
                if motion:
                    rad=math.radians(motion["dir"])
                    v={"u":math.sin(rad)*motion["speed"]*KT,"v":math.cos(rad)*motion["speed"]*KT}
            if not v:
                failures.append(f"{name}: Bunkers {side} indisponível")
                continue
            delta=math.hypot(v["u"]-expected[side][0],v["v"]-expected[side][1])
            deltas["bunkers_"+side]=delta
            if delta>0.12:failures.append(f"{name}: Bunkers {side}: diferença {delta:.3f} m/s")
        results.append({"profile":name,"deltas":deltas})
    heights,p,u,v,rows,samples=make_profile("veering",max_height=4000)
    truncated=run_js(rows,samples)
    for key in ("shear6","srh1","srh3","right","left"):
        if truncated.get(key) is not None:failures.append(f"Perfil truncado: {key} devia estar indisponível")
    results.append({"profile":"truncated_4km","shear6":truncated.get("shear6"),"bunkers":truncated.get("right")})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"generated_utc":datetime.now(timezone.utc).isoformat(),
                               "reference":"MetPy","profiles":results,"failures":failures},indent=2)+"\n")
    print(json.dumps({"profiles":results,"failures":failures},ensure_ascii=False,indent=2))
    if failures:raise SystemExit("Auditoria cinemática falhou")
    print("Auditoria cinemática passou dentro das tolerâncias de teste; não equivale a certificação operacional.")

if __name__=="__main__":
    main()
