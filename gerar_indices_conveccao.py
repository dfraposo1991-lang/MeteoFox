"""Experimental environmental convection indices, not cloud or lightning forecasts."""
import json
from pathlib import Path
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
import numpy as np
from eccodes import codes_grib_new_from_file,codes_get,codes_get_array,codes_release
from ecmwf.opendata import Client

def read(path,run,step):
    fields={}
    with path.open("rb") as f:
        while (g:=codes_grib_new_from_file(f)) is not None:
            try:
                p=codes_get(g,"shortName")
                if p not in ("mucape","r","t"): continue
                assert int(codes_get(g,"dataDate"))==int(run.strftime("%Y%m%d"))
                assert int(codes_get(g,"dataTime"))==run.hour*100 and int(codes_get(g,"endStep"))==step
                if p=="r": assert int(codes_get(g,"level"))==700 and codes_get(g,"units")=="%"
                if p=="t": assert int(codes_get(g,"level"))==500 and codes_get(g,"units")=="K"
                if p=="mucape": assert codes_get(g,"units") in ("J kg**-1","J kg-1","J/kg")
                nx,ny=int(codes_get(g,"Ni")),int(codes_get(g,"Nj"))
                lat=codes_get_array(g,"latitudes").reshape(ny,nx)[:,0]
                lon=codes_get_array(g,"longitudes").reshape(ny,nx)[0,:]
                lon=np.where(lon>180,lon-360,lon)
                ix=np.where((lon>=-40)&(lon<=0))[0];iy=np.where((lat>=25)&(lat<=50))[0]
                ix=ix[np.argsort(lon[ix])];iy=iy[np.argsort(lat[iy])]
                x,y=lon[ix],lat[iy]
                assert len(x)==161 and len(y)==101 and np.allclose(np.diff(x),.25) and np.allclose(np.diff(y),.25)
                a=codes_get_array(g,"values").reshape(ny,nx)[np.ix_(iy,ix)]
                assert np.isfinite(a).all() and (abs(a)<1e8).all()
                fields[p]=(x,y,a)
            finally: codes_release(g)
    return fields

def main():
    m=json.loads(Path("dados_meteofox_48h/ultimo_run.json").read_text())
    run=datetime.fromisoformat(m["run"].replace("Z","+00:00"))
    out=Path("MeteoFox_48h_"+run.strftime("%Y%m%d_%HUTC"))
    client=Client(source="ecmwf",model="ifs",resol="0p25")
    indexes={"tcucb":[],"lightning":[]}
    with TemporaryDirectory() as tmp:
        for step in range(9,94,3):
            try:
                fields={}
                for lev,param,level in [("sfc","mucape",None),("pl","r",700),("pl","t",500)]:
                    path=Path(tmp)/"field.grib2";path.unlink(missing_ok=True)
                    args=dict(date=run.strftime("%Y%m%d"),time=run.hour,stream="oper",type="fc",levtype=lev,step=step,param=param,target=str(path))
                    if level: args["levelist"]=level
                    client.retrieve(**args)
                    fields.update(read(path,run,step))
                x,y,cape=fields["mucape"]
                for p in ("r","t"):
                    assert np.array_equal(x,fields[p][0]) and np.array_equal(y,fields[p][1])
                rh=fields["r"][2];temp=fields["t"][2]
                if not (cape.min()>=-1 and rh.min()>=0 and rh.max()<=110 and temp.min()>150 and temp.max()<330):
                    raise ValueError(f"Physical range: CAPE {cape.min()}..{cape.max()}, RH {rh.min()}..{rh.max()}, T {temp.min()}..{temp.max()}")
                # Heuristic environmental scores, not parcel depth, cloud occurrence or flash density.
                moist=np.clip((rh-35)/40,0,1)
                buoy=np.clip(cape/1500,0,1)
                cold=np.clip((263.15-temp)/15,0,1)
                scores={"tcucb":100*buoy*moist,"lightning":100*buoy*moist*cold}
                for product,a in scores.items():
                    name=f"forecast_A_{product}_{step:03d}.json"
                    valid=(run+timedelta(hours=step)).isoformat()
                    frame=dict(step=step,resolution=.25,valid_utc=valid,x=x.tolist(),y=y.tolist(),experimental=True)
                    frame[product]=np.round(a,1).tolist()
                    (out/name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame=frame),separators=(",",":"),allow_nan=False))
                    indexes[product].append(dict(step=step,valid_utc=valid,file=name))
            except Exception as exc:
                import traceback
                print("Convection",step,repr(exc),flush=True)
                traceback.print_exc()
    for product,frames in indexes.items():
        (out/f"forecast_A_{product}_index.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=frames,experimental=True)))
if __name__=="__main__": main()
