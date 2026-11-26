#!/usr/bin/env python3
"""MeteoFox | 48h de chuva (3h) e rajadas | preserva as cartas aprovadas.

Ubuntu/WSL, pasta METEO FOX:
  python3 gerar_meteofox_48h.py

Requer, na mesma pasta:
  mapa_chuva_meteofox_v15_16W_6W_run.py
  mapa_rajadas_meteofox_v4.py
  dados_meteofox_48h/ultimo_run.json e GRIB2 descarregados

Cria pasta de resultados com 32 PNG e uma página HTML animada.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import html
import numpy as np
from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release

BASE = Path(__file__).resolve().parent
DATOS = BASE / "dados_meteofox_48h"
MANIFESTO = DATOS / "ultimo_run.json"
FONTE_CHUVA = BASE / "mapa_chuva_meteofox_v15_16W_6W_run.py"
FONTE_RAJADAS = BASE / "mapa_rajadas_meteofox_v4.py"
CAMPOS = {"tp", "10fg", "10u", "10v"}
CONV_KT = 1.9438444924406


def carregar_modulo(path, name):
    if not path.exists():
        raise FileNotFoundError(f"Falta o script aprovado: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRIB_QUALITY = []


def ler_passo(path, bounds=(-40, 0, 25, 50)):
    west, east, south, north = bounds
    dados = {}
    inventory = []
    with path.open("rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                name = str(codes_get(gid, "shortName"))
                inventory.append((name, str(codes_get(gid, "paramId")), str(codes_get(gid, "stepRange"))))
                if name not in CAMPOS:
                    continue
                unit = str(codes_get(gid, "units"))
                nx = int(codes_get(gid, "Ni"))
                ny = int(codes_get(gid, "Nj"))
                step = int(codes_get(gid, "step"))
                date = str(codes_get(gid, "dataDate"))
                hour = int(codes_get(gid, "dataTime"))
                # As grelhas globais são recortadas antes de qualquer desenho.
                lat = codes_get_array(gid, "latitudes").reshape(ny, nx)
                lon = codes_get_array(gid, "longitudes").reshape(ny, nx)
                val = codes_get_array(gid, "values").reshape(ny, nx)
                lon = np.where(lon > 180, lon-360, lon)
                # Selecionar colunas individualmente: o domínio cruza Greenwich.
                rows = np.flatnonzero((lat[:,0] >= south-1e-6) & (lat[:,0] <= north+1e-6))
                cols = np.flatnonzero((lon[0,:] >= west-1e-6) & (lon[0,:] <= east+1e-6))
                rows = rows[np.argsort(lat[rows,0])]
                cols = cols[np.argsort(lon[0,cols])]
                if len(rows)<2 or len(cols)<2:
                    raise RuntimeError(f"Domínio regional fora do GRIB: {name}")
                x = lon[0,cols].copy()
                y = lat[rows,0].copy()
                data = val[np.ix_(rows,cols)].astype(float).copy()
                if not (np.all(np.diff(x)>0) and np.all(np.diff(y)>0)):
                    raise RuntimeError("Grelha regional não monotónica")
                cycle = datetime.strptime(
                    f"{date}{hour:04d}", "%Y%m%d%H%M"
                ).replace(tzinfo=timezone.utc)
                if name == "tp":
                    if unit == "m":
                        data *= 1000.0
                    elif unit not in ("mm", "kg m**-2", "kg m-2"):
                        raise ValueError(f"Unidade inesperada para tp: {unit}")
                elif unit not in ("m s**-1", "m s-1", "m/s", "m s^-1"):
                    raise ValueError(f"Unidade inesperada para {name}: {unit}")
                GRIB_QUALITY.append({"file":path.name,"field":name,"cycle":cycle.isoformat(),"step":step,
                    "nx":nx,"ny":ny,"points":nx*ny,"dx":float(np.median(np.diff(x))),"dy":float(np.median(np.diff(y))),
                    "nonfinite":int(np.count_nonzero(~np.isfinite(data))),"unit":unit})
                dados[name] = {
                    "x": x, "y": y, "value": data,
                    "cycle": cycle, "step": step
                }
            finally:
                codes_release(gid)

    missing = CAMPOS - dados.keys()
    if missing:
        print(f"Inventário GRIB {path.name}: {inventory}", flush=True)
        if not (path.stem.endswith("_025") and missing == {"10fg"}):
            raise RuntimeError(f"Faltam parâmetros em {path.name}: {sorted(missing)}")
        print(f"Rajadas indisponíveis em {path.name}; sem substituição", flush=True)
    first = dados["tp"]
    for n, d in dados.items():
        if d["cycle"] != first["cycle"] or d["step"] != first["step"]:
            raise RuntimeError(f"Ciclo e prazo diferentes: {n} em {path.name}")
        if not (np.array_equal(d["x"], first["x"]) and
                np.array_equal(d["y"], first["y"])):
            raise RuntimeError(f"Grelha diferente em {n}: {path.name}")
    return dados


def quality_report(run, regional, local, inventory):
    result = {"run_utc": run.isoformat(), "grib": inventory, "regions": {}, "overlap": [], "warnings": []}
    for region, frames, last, spacing in (("A", regional, 93, .25), ("B", local, 54, .1)):
        summary = {"expected_steps": list(range(9,last+1,3)), "fields": {}, "grids": []}
        for field in ("rain","gust","u","v"):
            summary["fields"][field] = {"available": [f["step"] for f in frames if f[field] is not None],
                "missing": [s for s in summary["expected_steps"] if not any(f["step"] == s and f[field] is not None for f in frames)]}
        for f in frames:
            x,y = np.asarray(f["x"]),np.asarray(f["y"])
            valid = bool(np.allclose(np.diff(x),spacing) and np.allclose(np.diff(y),spacing))
            summary["grids"].append({"step":f["step"],"nx":len(x),"ny":len(y),"points":len(x)*len(y),"spacing_valid":valid})
            if not valid: result["warnings"].append(f"Região {region} +{f['step']}h: resolução inesperada")
        for field, status in summary["fields"].items():
            if status["missing"]: result["warnings"].append(f"Região {region}: {field} indisponível em {status['missing']}")
        result["regions"][region] = summary
    by_step = {f["step"]:f for f in regional}
    for b in local:
        a = by_step.get(b["step"])
        if a is None: continue
        ax,ay,bx,by = map(np.asarray,(a["x"],a["y"],b["x"],b["y"]))
        if bx[0]<ax[0] or bx[-1]>ax[-1] or by[0]<ay[0] or by[-1]>ay[-1]: continue
        for field in ("rain","gust","u","v"):
            if a[field] is None or b[field] is None: continue
            coarse = np.asarray(a[field]); fine = np.asarray(b[field])
            interpolated = np.array([np.interp(bx,ax,row) for row in coarse])
            interpolated = np.array([np.interp(by,ay,col) for col in interpolated.T]).T
            diff = fine-interpolated
            edge = np.ones(diff.shape,dtype=bool); edge[1:-1,1:-1]=False
            result["overlap"].append({"step":b["step"],"field":field,"bias":float(diff.mean()),"mae":float(np.abs(diff).mean()),"max_abs":float(np.abs(diff).max()),"boundary_mae":float(np.abs(diff[edge]).mean())})
    return result


def criar_html(run, steps, output):
    run_iso = datetime.strptime(run, '%d/%m/%Y %H:%M').replace(tzinfo=timezone.utc).isoformat().replace('+00:00','Z')
    names = json.dumps([f"{v:03d}" for v in steps])
    values = json.dumps([int(s) for s in steps])
    content = r'''<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MeteoFox | Chuva e Rajadas</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#111f2c;color:#edf4fb;font-family:Inter,Arial,Helvetica,sans-serif}
header{padding:17px 22px 5px}h1{font-size:23px;margin:0 0 6px}p{margin:0;color:#9cb6ca;font-size:13px}
main{padding:15px 20px 25px}.controls{display:flex;align-items:center;gap:13px;flex-wrap:wrap;padding:14px 0}
button{border:1px solid #547389;background:#27465d;color:white;padding:9px 16px;border-radius:7px;cursor:pointer}
button:hover{background:#3b6481}input[type=range]{flex:1;min-width:140px;accent-color:#4aafd6}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.image-wrap{background:#fff}
.times{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0;padding:8px 12px;min-height:30px;color:#52677a;font:400 11px/1.5 Inter,Arial,sans-serif;background:#fff;border:0;box-shadow:none}
.times span{padding:0;background:none;border:0;box-shadow:none;text-shadow:none}
.times span:last-child{text-align:right}
.panel{background:#fff;border-radius:6px;overflow:hidden}.panel h2{background:#213a50;color:white;margin:0;padding:8px 12px;font-size:15px}
.panel img{display:block;width:100%;height:auto}.foot{padding:14px 0;color:#91adc0;font-size:12px}
@media(max-width:850px){.panels{grid-template-columns:1fr}main{padding:10px}}
</style></head><body>
<header><h1>MeteoFox · ECMWF IFS · Chuva e Rajadas</h1>
<p>ECMWF IFS Open Data (CC BY 4.0)</p></header>
<main><div class="controls"><button id="play">▶ Reproduzir</button>
<button id="previous">◀</button><button id="next">▶</button><input id="position" type="range" min="0" value="0"></div>
<div class="panels"><div class="panel"><h2>Precipitação em 3 horas · mm</h2><div class="image-wrap"><div class="times"><span class="run"></span><span class="valid"></span></div><img id="rain" alt="Precipitação ECMWF"></div></div>
<div class="panel"><h2>Rajadas máximas · kt</h2><div class="image-wrap"><div class="times"><span class="run"></span><span class="valid"></span></div><img id="wind" alt="Rajadas ECMWF"></div></div></div>
<div class="foot">Use a linha temporal para consultar cada passo. Os vetores mostram a direção do vento a 10 m, não a direção das rajadas.</div></main>
<script>
const files = FILES_PLACEHOLDER, hours = HOURS_PLACEHOLDER;
const rain=document.getElementById('rain'),wind=document.getElementById('wind');
const slider=document.getElementById('position'),play=document.getElementById('play');
const cycle=Date.parse(RUN_ISO_PLACEHOLDER);
const formatUTC=value=>new Intl.DateTimeFormat('pt-PT',{timeZone:'UTC',weekday:'long',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value))+' UTC';
let n=0,timer=null;slider.max=hours.length-1;
function render(){let s=files[n];rain.src='chuva_'+s+'.png';wind.src='rajadas_'+s+'.png';
slider.value=n;document.querySelectorAll('.times').forEach(el=>{el.querySelector('.run').textContent='run ECMWF '+formatUTC(cycle);el.querySelector('.valid').textContent='válido '+formatUTC(cycle+hours[n]*3600000);});}
function stop(){if(timer){clearInterval(timer);timer=null;}play.textContent='▶ Reproduzir';}
function step(dir){n=(n+dir+hours.length)%hours.length;render();}
play.addEventListener('click',()=>{if(timer){stop();return;}play.textContent='⏸ Pausar';
timer=setInterval(()=>step(1),1100);});
slider.addEventListener('input',()=>{n=Number(slider.value);render();});
document.getElementById('previous').addEventListener('click',()=>step(-1));
document.getElementById('next').addEventListener('click',()=>step(1));
render();
</script></body></html>'''
    content = (content.replace("FILES_PLACEHOLDER", names)
                     .replace("HOURS_PLACEHOLDER", values)
                     .replace("RUN_ISO_PLACEHOLDER", json.dumps(run_iso)))
    (output / "MeteoFox_animacao_48h.html").write_text(content, encoding="utf-8")


def main():
    if not MANIFESTO.exists():
        raise FileNotFoundError("Primeiro executa descarregar_meteofox_48h.py no PowerShell.")
    manifest = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    run = datetime.strptime(manifest["run"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    run_folder = DATOS / manifest["pasta"]
    steps = [int(v) for v in manifest["passos"]]
    def path(p):
        return run_folder / f"step_{p:03d}_025.grib2"
    absent = [p for p in steps if not path(p).exists()]
    if absent:
        raise FileNotFoundError(f"Faltam os GRIB2 dos passos {absent}. Repete o descarregamento.")

    rain_module = carregar_modulo(FONTE_CHUVA, "meteofx_chuva_aprovada")
    wind_module = carregar_modulo(FONTE_RAJADAS, "meteofx_rajadas_aprovadas")
    out = BASE / f"MeteoFox_48h_{run:%Y%m%d_%H}UTC"
    out.mkdir(exist_ok=True)
    previous = ler_passo(path(6))["tp"]
    if previous["cycle"] != run or previous["step"] != 6:
        raise RuntimeError("Acumulado +6h inválido")
    interactive = []

    print(f"Run ECMWF: {run} | {len(steps)} passos")
    for step in steps:
        print(f"Passo +{step:02d} h: a ler GRIB2...", flush=True)
        grib_file = path(step)
        data = ler_passo(grib_file)
        current = data["tp"]
        if current["cycle"] != run or current["step"] != step:
            raise RuntimeError(f"Run ou passo diferente dentro de {grib_file.name}")
        for n in ("10fg", "10u", "10v"):
            if n not in data and n == "10fg" and step > 54:
                continue
            if data[n]["cycle"] != run or data[n]["step"] != step:
                raise RuntimeError(f"Diferenca de Run/passo em {grib_file.name} ({n})")

        # ECMWF operacional tp acumula desde o inicio do Run.
        # Diferença consecutiva = precipitação em cada intervalo de 3 h.
        if previous is None:
            rain_3h = np.maximum(current["value"], 0)
        else:
            if not (np.array_equal(current["x"], previous["x"]) and
                    np.array_equal(current["y"], previous["y"])):
                raise RuntimeError("Grelha da precipitação alterou entre passos")
            rain_3h = np.maximum(current["value"] - previous["value"], 0)
        # Primeiro prazo sem acumulado anterior: não rotular como 3h.
        interactive.append(dict(step=step, resolution=0.25, valid_utc=(run+timedelta(hours=step)).isoformat(),
            x=current["x"].tolist(), y=current["y"].tolist(),
            rain=np.round(rain_3h,2).tolist() if previous is not None else None,
            gust=np.round(data["10fg"]["value"]*CONV_KT,2).tolist() if "10fg" in data else None,
            u=np.round(data["10u"]["value"],2).tolist(), v=np.round(data["10v"]["value"],2).tolist()))
        previous = current
        if step > 54:
            continue
        # Preservar exatamente o recorte das cartas aprovadas.
        ix = np.flatnonzero((current["x"] >= -16.15) & (current["x"] <= -5.85))
        iy = np.flatnonzero((current["y"] >= 34.35) & (current["y"] <= 45.15))
        data = {k: dict(d, x=d["x"][ix], y=d["y"][iy], value=d["value"][np.ix_(iy,ix)]) for k,d in data.items()}
        current = data["tp"]
        rain_3h = (current["value"] if step==9 else rain_3h[np.ix_(iy,ix)])

        # Injetar dados processados nas funções originais aprovadas:
        # cores, tamanho das cartas, vetores, etiquetas e coordenadas ficam iguais.
        rain_module.FICHEIRO_GRIB = grib_file
        rain_module.SAIDA = out / f"chuva_{step:03d}.png"
        rain_module.ler_grib = lambda _path, c=current, mm=rain_3h: (
            c["x"], c["y"], mm, c["cycle"],
            c["cycle"] + timedelta(hours=c["step"]), c["step"]
        )
        rain_module.criar_mapa()

        wind_module.GRIB = grib_file
        wind_module.OUTPUT = out / f"rajadas_{step:03d}.png"
        wind_module.read_fields = lambda _path, all_data=data: {
            k: all_data[k] for k in ("10fg", "10u", "10v")
        }
        wind_module.make_map()
        del data

    (out / "forecast_grid.json").write_text(json.dumps(dict(run_utc=run.isoformat(),frames=interactive),allow_nan=False,separators=(",",":")),encoding="utf-8")
    # Separate products while retaining the legacy file for older clients.
    for product, fields in (("rain", ("rain",)), ("gust", ("gust", "u", "v"))):
        keys = ("step", "resolution", "valid_utc", "x", "y") + fields
        payload = dict(run_utc=run.isoformat(), frames=[{k: frame[k] for k in keys} for frame in interactive])
        (out / f"forecast_A_{product}.json").write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        index = dict(run_utc=payload["run_utc"], frames=[])
        for frame in payload["frames"]:
            name = f"forecast_A_{product}_{frame['step']:03d}.json"
            (out / name).write_text(json.dumps(dict(run_utc=payload["run_utc"], frame=frame), allow_nan=False, separators=(",", ":")), encoding="utf-8")
            index["frames"].append(dict(step=frame["step"], valid_utc=frame["valid_utc"], file=name))
        (out / f"forecast_A_{product}_index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    # Region B: separate same-cycle frames, never interpolate coarse data.
    local = []
    previous_b = None
    for step in range(6,55,3):
        try:
            data_b = ler_passo(run_folder / f"step_{step:03d}_01.grib2", (-10,-6,36.9,42.2))
            c = data_b["tp"]
            if c["cycle"] != run or c["step"] != step or not np.allclose(np.diff(c["x"]), .1) or not np.allclose(np.diff(c["y"]), .1):
                raise RuntimeError("Ciclo, prazo ou resolução B inválidos")
            if step >= 9 and previous_b is not None and previous_b["step"] == step-3:
                if not (np.array_equal(c["x"],previous_b["x"]) and np.array_equal(c["y"],previous_b["y"])):
                    raise RuntimeError("Grelha B alterada")
                local.append(dict(step=step,resolution=.1,valid_utc=(run+timedelta(hours=step)).isoformat(),
                    x=c["x"].tolist(),y=c["y"].tolist(),
                    rain=np.round(np.maximum(c["value"]-previous_b["value"],0),2).tolist(),
                    gust=np.round(data_b["10fg"]["value"]*CONV_KT,2).tolist(),
                    u=np.round(data_b["10u"]["value"],2).tolist(),v=np.round(data_b["10v"]["value"],2).tolist()))
            previous_b = c
        except Exception as exc:
            previous_b = None
            print(f"Região B +{step}h: {exc}",flush=True)
    for product, fields in (("rain",("rain",)),("gust",("gust","u","v"))):
        index = dict(run_utc=run.isoformat(),frames=[])
        for frame in local:
            name = f"forecast_B_{product}_{frame['step']:03d}.json"
            keys = ("step","resolution","valid_utc","x","y")+fields
            (out / name).write_text(json.dumps(dict(run_utc=run.isoformat(),frame={k:frame[k] for k in keys}),allow_nan=False,separators=(",",":")),encoding="utf-8")
            index["frames"].append(dict(step=frame["step"],valid_utc=frame["valid_utc"],file=name))
        (out / f"forecast_B_{product}_index.json").write_text(json.dumps(index,separators=(",",":")),encoding="utf-8")
    quality = quality_report(run, interactive, local, GRIB_QUALITY)
    (out / "ecmwf_quality.json").write_text(json.dumps(quality,allow_nan=False,indent=2),encoding="utf-8")
    print("ECMWF QUALITY:", json.dumps({"run":quality["run_utc"],"warnings":quality["warnings"]}),flush=True)
    criar_html(run.strftime("%d/%m/%Y %H:%M"), [p for p in steps if p<=54], out)
    print("\nCONCLUÍDO")
    print("Ficheiros PNG:", len([p for p in steps if p<=54]) * 2)
    print("Abrir no navegador:", out / "MeteoFox_animacao_48h.html")


if __name__ == "__main__":
    main()
