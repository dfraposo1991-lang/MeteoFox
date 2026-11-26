"""Optional native-grid cloud and snowfall products. Never fabricate missing fields."""
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
                if param=="tcc":
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
    for region,h,res,bounds,last in [("A",.25,"0p25",(-40,0,25,50),93)]:
        client=Client(source="ecmwf",model="ifs",resol=res)
        indexes={"cloud":[],"snow":[]}
        previous=None
        with TemporaryDirectory() as tmp:
            for step in range(6,last+1,3):
                for param,product in [("sf","snow"),("tcc","cloud")]:
                    if step==6 and param=="tcc": continue
                    path=Path(tmp)/"field.grib2"
                    try:
                        path.unlink(missing_ok=True)
                        client.retrieve(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype="sfc",step=step,param=param,target=str(path))
                        x,y,a,start=read(path,run,step,param,bounds,h)
                        if param=="sf":
                            prior=previous
                            previous=(step,start,a)
                            if step==6: continue
                            if start==step-3: pass
                            elif prior is not None and prior[0]==step-3 and prior[1]==start:
                                a=a-prior[2]
                            else: raise ValueError("Missing matching accumulation baseline")
                            assert a.min()>=-.05
                            a=np.maximum(a,0)
                        name=f"forecast_{region}_{product}_{step:03d}.json"
                        valid=(run+timedelta(hours=step)).isoformat()
                        frame=dict(step=step,resolution=h,valid_utc=valid,x=x.tolist(),y=y.tolist())
                        frame[product]=np.round(a,2).tolist()
                        (out/name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame=frame),separators=(",",":"),allow_nan=False))
                        indexes[product].append(dict(step=step,valid_utc=valid,file=name))
                    except Exception as exc:
                        print(region,product,step,str(exc),flush=True)
                        if param=="sf": previous=None
        for product,frames in indexes.items():
            (out/f"forecast_{region}_{product}_index.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=frames)))
if __name__=="__main__": main()
