"""Uncalibrated moisture visibility proxy and conditional LCL proxy; not operational aviation forecasts."""
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
                elif param in ("tcc","lcc"):
                    assert unit in ("(0 - 1)","0-1","1","%")
                    if unit!="%": a=a*100
                    assert a.min()>=-.01 and a.max()<=100.01
                    a=np.clip(a,0,100)
                elif param in ("2t","2d"):
                    assert unit=="K" and a.min()>150 and a.max()<350
                else: raise ValueError("Unsupported field")
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
            for step in range(9,last+1,3):
                fields={}
                for params in [("2t","2d"),("lcc",)]:
                    path=Path(tmp)/"fields.grib2"
                    try:
                        path.unlink(missing_ok=True)
                        client.retrieve(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype="sfc",step=step,param=list(params),target=str(path))
                        for p in params: fields[p]=read(path,run,step,p,bounds,h)
                    except Exception as exc:
                        print(region,step,params,repr(exc),flush=True)
                if not all(p in fields for p in ("2t","2d")): continue
                x,y,t,_=fields["2t"]
                xd,yd,td,_=fields["2d"]
                if not (np.array_equal(x,xd) and np.array_equal(y,yd)): continue
                good=td<=t+0.5
                delta=np.maximum(t-td,0)
                # Empirical screening proxy, not an extinction calculation.
                # Scale from saturation to dry air; capped at 10 km.
                vis=np.clip(200*np.exp(np.minimum(delta,20)*0.8),200,10000)
                products={"visibility":(vis,good,"uncalibrated_dewpoint_depression_proxy")}
                if "lcc" in fields:
                    xl,yl,lcc,_=fields["lcc"]
                    if np.array_equal(x,xl) and np.array_equal(y,yl):
                        # Surface parcel LCL, conditional on extensive low cloud.
                        # Not a direct BKN/OVC base; no estimate elsewhere.
                        products["ceiling"]=(125*delta*3.280839895,good&(lcc>=62.5),"conditional_surface_lcl_proxy")
                valid=(run+timedelta(hours=step)).isoformat()
                for product,(a,mask,method) in products.items():
                    if not mask.any(): continue
                    name=f"forecast_{region}_{product}_{step:03d}.json"
                    frame=dict(step=step,resolution=h,valid_utc=valid,x=x.tolist(),y=y.tolist(),experimental=True,method=method)
                    frame[product]=np.where(mask,np.round(a,1),None).tolist()
                    (out/name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame=frame),separators=(",",":"),allow_nan=False))
                    indexes[product].append(dict(step=step,valid_utc=valid,file=name))
        for product,frames in indexes.items():
            (out/f"forecast_{region}_{product}_index.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=frames,experimental=True)))
if __name__=="__main__": main()
