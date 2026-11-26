"""Experimental direct-field availability probe for visibility and ceiling; no proxy values."""
import json
from pathlib import Path
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
import numpy as np
from eccodes import codes_grib_new_from_file,codes_get,codes_get_array,codes_release
from ecmwf.opendata import Client

def read(path,run,step,param,bounds,h):
    with path.open("rb") as f:
        while (g:=codes_grib_new_from_file(f)) is not None:
            try:
                if codes_get(g,"shortName")!=param: continue
                assert int(codes_get(g,"dataDate"))==int(run.strftime("%Y%m%d"))
                assert int(codes_get(g,"dataTime"))==run.hour*100
                assert int(codes_get(g,"endStep"))==step
                nx,ny=int(codes_get(g,"Ni")),int(codes_get(g,"Nj"))
                lat=codes_get_array(g,"latitudes").reshape(ny,nx)[:,0]
                lon=codes_get_array(g,"longitudes").reshape(ny,nx)[0,:]
                lon=np.where(lon>180,lon-360,lon)
                west,east,south,north=bounds
                ix=np.where((lon>=west-1e-6)&(lon<=east+1e-6))[0]
                iy=np.where((lat>=south-1e-6)&(lat<=north+1e-6))[0]
                ix=ix[np.argsort(lon[ix])];iy=iy[np.argsort(lat[iy])]
                x,y=lon[ix],lat[iy]
                assert len(x)>1 and len(y)>1 and np.allclose(np.diff(x),h) and np.allclose(np.diff(y),h)
                assert np.allclose([x[0],x[-1],y[0],y[-1]],bounds)
                a=codes_get_array(g,"values").reshape(ny,nx)[np.ix_(iy,ix)]
                assert np.isfinite(a).all() and (abs(a)<1e10).all()
                unit=codes_get(g,"units")
                if param in ("vis","ceil"):
                    assert unit=="m"
                    assert a.min()>=0
                    if param=="ceil": a=a*3.280839895
                elif param=="tcc":
                    assert unit in ("(0 - 1)","0-1","1","%")
                    if unit!="%": a=a*100
                    assert a.min()>=-.01 and a.max()<=100.01
                    a=np.clip(a,0,100)
                else:
                    assert unit in ("m","m of water equivalent","kg m**-2","kg m-2","mm")
                    if unit.startswith("m") and unit!="mm": a=a*1000
                return x,y,a,int(codes_get(g,"startStep"))
            finally: codes_release(g)
    raise ValueError("Missing "+param)

def main():
    m=json.loads(Path("dados_meteofox_48h/ultimo_run.json").read_text())
    run=datetime.fromisoformat(m["run"].replace("Z","+00:00"))
    out=Path("MeteoFox_48h_"+run.strftime("%Y%m%d_%HUTC"))
    for region,h,res,bounds,last in [("A",.25,"0p25",(-40,0,25,50),93),("B",.1,"0p1",(-10,-6,36.9,42.2),54)]:
        client=Client(source="ecmwf",model="ifs",resol=res)
        indexes={"visibility":[],"ceiling":[]}
        with TemporaryDirectory() as tmp:
            available=[]
            for param,product in [("vis","visibility"),("ceil","ceiling")]:
                try:
                    probe=Path(tmp)/"probe.grib2"
                    probe.unlink(missing_ok=True)
                    client.retrieve(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype="sfc",step=9,param=param,target=str(probe))
                    read(probe,run,9,param,bounds,h)
                    available.append((param,product))
                except Exception as exc:
                    print(region,product,"unavailable:",exc,flush=True)
            for step in range(9,last+1,3):
                for param,product in available:
                    
                    path=Path(tmp)/"field.grib2"
                    try:
                        path.unlink(missing_ok=True)
                        client.retrieve(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype="sfc",step=step,param=param,target=str(path))
                        x,y,a,start=read(path,run,step,param,bounds,h)
                        name=f"forecast_{region}_{product}_{step:03d}.json"
                        valid=(run+timedelta(hours=step)).isoformat()
                        frame=dict(step=step,resolution=h,valid_utc=valid,x=x.tolist(),y=y.tolist())
                        frame[product]=np.round(a,2).tolist()
                        (out/name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame=frame),separators=(",",":"),allow_nan=False))
                        indexes[product].append(dict(step=step,valid_utc=valid,file=name))
                    except Exception as exc:
                        print(region,product,step,str(exc),flush=True)

        for product,frames in indexes.items():
            (out/f"forecast_{region}_{product}_index.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=frames)))
if __name__=="__main__": main()
