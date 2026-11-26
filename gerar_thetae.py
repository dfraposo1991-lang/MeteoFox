"""Optional same-cycle ECMWF theta-e product; native 0.25°, sampled at 0.5°."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
from ecmwf.opendata import Client

def main():
    base=Path("dados_meteofox_48h")
    m=json.loads((base/"ultimo_run.json").read_text())
    run=datetime.fromisoformat(m["run"].replace("Z","+00:00"))
    out=Path("MeteoFox_48h_"+run.strftime("%Y%m%d_%HUTC"))
    client=Client(source="ecmwf",model="ifs",resol="0p25")
    frames=[]
    for step in range(9,94,3):
        path=base/m["pasta"]/f"thetae_{step:03d}.grib2"
        try:
            client.retrieve(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype="pl",levelist=850,step=step,param=["t","q"],target=str(path))
            fields={}
            with path.open("rb") as f:
                while (g:=codes_grib_new_from_file(f)) is not None:
                    try:
                        name=codes_get(g,"shortName")
                        if name not in ("t","q"): continue
                        assert int(codes_get(g,"level"))==850 and int(codes_get(g,"step"))==step
                        assert int(codes_get(g,"dataDate"))==int(run.strftime("%Y%m%d")) and int(codes_get(g,"dataTime"))==run.hour*100
                        nx,ny=int(codes_get(g,"Ni")),int(codes_get(g,"Nj"))
                        lat=codes_get_array(g,"latitudes").reshape(ny,nx)[:,0]
                        lon=codes_get_array(g,"longitudes").reshape(ny,nx)[0,:]
                        lon=np.where(lon>180,lon-360,lon)
                        assert np.allclose(np.abs(np.diff(lat)),.25)
                        ix=np.where((lon>=-40)&(lon<=0)&np.isclose(lon*2,np.round(lon*2)))[0]
                        iy=np.where((lat>=25)&(lat<=50)&np.isclose(lat*2,np.round(lat*2)))[0]
                        ix=ix[np.argsort(lon[ix])];iy=iy[np.argsort(lat[iy])]
                        x,y=lon[ix],lat[iy]
                        assert len(x)==81 and len(y)==51 and np.allclose(np.diff(x),.5) and np.allclose(np.diff(y),.5)
                        fields[name]=(x,y,codes_get_array(g,"values").reshape(ny,nx)[np.ix_(iy,ix)])
                    finally: codes_release(g)
            x,y,t=fields["t"]; xx,yy,q=fields["q"]
            assert np.array_equal(x,xx) and np.array_equal(y,yy)
            # Bolton (1980), pressure in hPa, mixing ratio kg/kg.
            valid=np.isfinite(t)&np.isfinite(q)&(t>150)&(t<350)&(q>=0)&(q<.1)
            r=np.clip(q,1e-10,.099)/(1-np.clip(q,1e-10,.099))
            e=850*r/(.622+r)
            log=np.log(e/6.112);td=243.5*log/(17.67-log)+273.15
            tl=1/(1/(td-56)+np.log(t/td)/800)+56
            theta=t*(1000/(850-e))**.2854*(t/tl)**(.28*r)*np.exp((3036/tl-1.78)*r*(1+.448*r))
            values=np.where(valid,theta,np.nan)
            frame=dict(step=step,resolution=.5,source_resolution=.25,valid_utc=(run+timedelta(hours=step)).isoformat(),x=x.tolist(),y=y.tolist(),thetae=[[round(float(v),2) if np.isfinite(v) else None for v in row] for row in values])
            name=f"forecast_A_thetae_{step:03d}.json"
            (out/name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame=frame),allow_nan=False))
            frames.append(dict(step=step,valid_utc=frame["valid_utc"],file=name))
        except Exception as exc: print(f"Theta-E +{step}: {exc}",flush=True)
        finally: path.unlink(missing_ok=True)
    (out/"forecast_A_thetae_index.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=frames)))
if __name__=="__main__": main()
