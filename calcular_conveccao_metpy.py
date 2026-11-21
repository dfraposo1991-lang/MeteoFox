#!/usr/bin/env python3
"""Diagnósticos termodinâmicos ECMWF via MetPy; sem extrapolar níveis ausentes.
Produz JSON apenas de previsões, não observações nem avisos operacionais.
"""
import json
import math
from pathlib import Path
import numpy as np
from metpy.calc import (mixed_layer_cape_cin, most_unstable_cape_cin,
                        mixed_parcel, lcl, most_unstable_parcel)
from metpy.units import units

SOURCE=Path("produtos_experimentais/previsao_ecmwf.json")
DEST=Path("produtos_experimentais/conveccao_termodinamica.json")

def scalar(q, unit):
    v=float(q.to(unit).magnitude)
    return round(v,1) if math.isfinite(v) else None

def calculate(rows):
    r=sorted(rows,key=lambda x:-float(x["hpa"]))
    if len(r)<8 or r[0]["hpa"]<850 or r[-1]["hpa"]>300:
        return {"status":"insufficient_levels"}
    p=np.array([x["hpa"] for x in r])*units.hPa
    t=np.array([x["temp_c"] for x in r])*units.degC
    td=np.array([min(x["dewpoint_c"],x["temp_c"]) for x in r])*units.degC
    result={"status":"ok","mlcape_jkg":None,"mlcin_jkg":None,
            "mucape_jkg":None,"mucin_jkg":None,"ml_lcl_hpa":None,"mu_origin_hpa":None,
            "method":"MetPy; mixed layer 100 hPa; most unstable search 300 hPa"}
    try:
        cape,cin=mixed_layer_cape_cin(p,t,td,depth=100*units.hPa)
        result["mlcape_jkg"]=scalar(cape,"J/kg")
        result["mlcin_jkg"]=scalar(cin,"J/kg")
        mp,mt,mtd=mixed_parcel(p,t,td,depth=100*units.hPa)
        plcl,_=lcl(mp,mt,mtd)
        result["ml_lcl_hpa"]=scalar(plcl,"hPa")
    except (ValueError,IndexError,TypeError) as exc:
        result["mixed_layer_error"]=str(exc)[:150]
    try:
        cape,cin=most_unstable_cape_cin(p,t,td,depth=300*units.hPa)
        result["mucape_jkg"]=scalar(cape,"J/kg")
        result["mucin_jkg"]=scalar(cin,"J/kg")
        mup,_,_,_=most_unstable_parcel(p,t,td,depth=300*units.hPa)
        result["mu_origin_hpa"]=scalar(mup,"hPa")
    except (ValueError,IndexError,TypeError) as exc:
        result["most_unstable_error"]=str(exc)[:150]
    if result["mlcape_jkg"] is None and result["mucape_jkg"] is None:
        result["status"]="unavailable"
    return result

def main():
    source=json.loads(SOURCE.read_text(encoding="utf-8"))
    output={"model":source["model"],"run_utc":source["run_utc"],
            "source":"ECMWF IFS Open Data / MetPy",
            "experimental":True,
            "warning":"Perfis isobáricos de resolução limitada; não constituem radiossondagens nem avisos.",
            "soundings":[]}
    for record in source["soundings"]:
        output["soundings"].append({
            "valid_utc":record["valid_utc"],
            "cities":{city:calculate(rows) for city,rows in record["cities"].items()}
        })
    DEST.parent.mkdir(parents=True,exist_ok=True)
    DEST.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    assert len(output["soundings"])==len(source["soundings"])
    print("MetPy: perfis",len(output["soundings"]),"run",output["run_utc"])
    for step in output["soundings"]:
        print(step["valid_utc"],{city:v["status"] for city,v in step["cities"].items()})

if __name__=="__main__":
    main()
