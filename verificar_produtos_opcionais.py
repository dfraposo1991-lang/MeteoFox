"""Audit optional forecast coverage without treating missing data as zero."""
import json
from pathlib import Path
import numpy as np

def main():
    m=json.loads(Path("dados_meteofox_48h/ultimo_run.json").read_text())
    run=m["run"]
    out=Path("MeteoFox_48h_"+run[:10].replace("-","")+"_"+run[11:13]+"UTC")
    from datetime import datetime
    report={"run_utc":run,"products":{}}
    for product in ("visibility","ceiling","tcucb","lightning"):
        for region in (("A","B") if product in ("visibility","ceiling") else ("A",)):
            expected=list(range(9,55 if region=="B" else 94,3))
            valid=[];errors={}
            h=.1 if region=="B" else .25
            for step in expected:
                name=f"forecast_{region}_{product}_{step:03d}.json"
                try:
                    p=json.loads((out/name).read_text())
                    assert datetime.fromisoformat(p["run_utc"].replace("Z","+00:00"))==datetime.fromisoformat(run.replace("Z","+00:00")), "cycle"
                    f=p["frame"];x=np.array(f["x"]);y=np.array(f["y"]);a=np.array(f[product],dtype=float)
                    assert f["step"]==step and f["resolution"]==h,"step or resolution"
                    assert a.shape==(len(y),len(x)) and np.isfinite(a).all(),"invalid values"
                    assert len(x)>1 and len(y)>1 and np.allclose(np.diff(x),h) and np.allclose(np.diff(y),h),"grid spacing"
                    assert np.allclose([x[0],x[-1],y[0],y[-1]],[-10,-6,36.9,42.2] if region=="B" else [-40,0,25,50]),"bounds"
                    valid.append(step)
                except Exception as exc: errors[str(step)]=str(exc) or type(exc).__name__
            status="complete" if valid==expected else "partial" if valid else "unavailable"
            report["products"][region+"_"+product]={"status":status,"available":valid,"expected":expected,"errors":errors}
            print(region,product,status,len(valid),"/",len(expected),flush=True)
    (out/"optional_quality.json").write_text(json.dumps(report,indent=2))
if __name__=="__main__": main()
