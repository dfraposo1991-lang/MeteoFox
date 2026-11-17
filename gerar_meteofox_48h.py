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


def ler_passo(path):
    dados = {}
    with path.open("rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                name = str(codes_get(gid, "shortName"))
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
                selected = (
                    (lon >= -16.15) & (lon <= -5.85) &
                    (lat >= 34.35) & (lat <= 45.15)
                )
                rr, cc = np.where(selected)
                if not len(rr):
                    raise RuntimeError(f"Domínio 16W-6W fora do GRIB: {name}")
                r0, r1 = int(rr.min()), int(rr.max())
                c0, c1 = int(cc.min()), int(cc.max())
                x = lon[r0, c0:c1+1].copy()
                y = lat[r0:r1+1, c0].copy()
                data = val[r0:r1+1, c0:c1+1].astype(float).copy()
                if y[0] > y[-1]:
                    y, data = y[::-1], data[::-1, :]
                if x[0] > x[-1]:
                    x, data = x[::-1], data[:, ::-1]
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
                dados[name] = {
                    "x": x, "y": y, "value": data,
                    "cycle": cycle, "step": step
                }
            finally:
                codes_release(gid)

    missing = CAMPOS - dados.keys()
    if missing:
        raise RuntimeError(f"Faltam parâmetros em {path.name}: {sorted(missing)}")
    first = dados["tp"]
    for n, d in dados.items():
        if d["cycle"] != first["cycle"] or d["step"] != first["step"]:
            raise RuntimeError(f"Ciclo e prazo diferentes: {n} em {path.name}")
        if not (np.array_equal(d["x"], first["x"]) and
                np.array_equal(d["y"], first["y"])):
            raise RuntimeError(f"Grelha diferente em {n}: {path.name}")
    return dados


def criar_html(run, steps, output):
    run_h = html.escape(run)
    names = json.dumps([f"{v:03d}" for v in steps])
    values = json.dumps([int(s) for s in steps])
    content = r'''<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MeteoFox | Chuva e Rajadas</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#111f2c;color:#edf4fb;font-family:Arial,Helvetica,sans-serif}
header{padding:17px 22px 5px}h1{font-size:23px;margin:0 0 6px}p{margin:0;color:#9cb6ca;font-size:13px}
main{padding:15px 20px 25px}.controls{display:flex;align-items:center;gap:13px;flex-wrap:wrap;padding:14px 0}
button{border:1px solid #547389;background:#27465d;color:white;padding:9px 16px;border-radius:7px;cursor:pointer}
button:hover{background:#3b6481}input[type=range]{flex:1;min-width:140px;accent-color:#4aafd6}
.time{font-weight:700;color:#fff;min-width:130px}.panels{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{background:#fff;border-radius:6px;overflow:hidden}.panel h2{background:#213a50;color:white;margin:0;padding:8px 12px;font-size:15px}
.panel img{display:block;width:100%;height:auto}.foot{padding:14px 0;color:#91adc0;font-size:12px}
@media(max-width:850px){.panels{grid-template-columns:1fr}main{padding:10px}}
</style></head><body>
<header><h1>MeteoFox · ECMWF IFS · Chuva e Rajadas</h1>
<p>Run: RUN_PLACEHOLDER UTC · previsões de 3 em 3 h até +48 h · ECMWF IFS Open Data (CC BY 4.0)</p></header>
<main><div class="controls"><button id="play">▶ Reproduzir</button>
<button id="previous">◀</button><input id="position" type="range" min="0" value="0"><button id="next">▶</button>
<span id="time" class="time">+03 h</span></div>
<div class="panels"><div class="panel"><h2>Precipitação em 3 horas · mm</h2><img id="rain" alt="Precipitação ECMWF"></div>
<div class="panel"><h2>Rajadas máximas · kt</h2><img id="wind" alt="Rajadas ECMWF"></div></div>
<div class="foot">Use a linha temporal para consultar cada passo. Os vetores mostram a direção do vento a 10 m, não a direção das rajadas.</div></main>
<script>
const files = FILES_PLACEHOLDER, hours = HOURS_PLACEHOLDER;
const rain=document.getElementById('rain'),wind=document.getElementById('wind');
const slider=document.getElementById('position'),time=document.getElementById('time'),play=document.getElementById('play');
let n=0,timer=null;slider.max=hours.length-1;
function render(){let s=files[n];rain.src='chuva_'+s+'.png';wind.src='rajadas_'+s+'.png';
slider.value=n;time.textContent='+'+String(hours[n]).padStart(2,'0')+' h';}
function stop(){if(timer){clearInterval(timer);timer=null;}play.textContent='▶ Reproduzir';}
function step(dir){n=(n+dir+hours.length)%hours.length;render();}
play.addEventListener('click',()=>{if(timer){stop();return;}play.textContent='⏸ Pausar';
timer=setInterval(()=>step(1),1100);});
slider.addEventListener('input',()=>{n=Number(slider.value);render();});
document.getElementById('previous').addEventListener('click',()=>step(-1));
document.getElementById('next').addEventListener('click',()=>step(1));
render();
</script></body></html>'''
    content = (content.replace("RUN_PLACEHOLDER", run_h)
                     .replace("FILES_PLACEHOLDER", names)
                     .replace("HOURS_PLACEHOLDER", values))
    (output / "MeteoFox_animacao_48h.html").write_text(content, encoding="utf-8")


def main():
    if not MANIFESTO.exists():
        raise FileNotFoundError("Primeiro executa descarregar_meteofox_48h.py no PowerShell.")
    manifest = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    run = datetime.strptime(manifest["run"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    run_folder = DATOS / manifest["pasta"]
    steps = [int(v) for v in manifest["passos"]]
    absent = [p for p in steps if not (run_folder / f"step_{p:03d}.grib2").exists()]
    if absent:
        raise FileNotFoundError(f"Faltam os GRIB2 dos passos {absent}. Repete o descarregamento.")

    rain_module = carregar_modulo(FONTE_CHUVA, "meteofx_chuva_aprovada")
    wind_module = carregar_modulo(FONTE_RAJADAS, "meteofx_rajadas_aprovadas")
    out = BASE / f"MeteoFox_48h_{run:%Y%m%d_%H}UTC"
    out.mkdir(exist_ok=True)
    previous = None

    print(f"Run ECMWF: {run} | {len(steps)} passos")
    for step in steps:
        print(f"Passo +{step:02d} h: a ler GRIB2...", flush=True)
        grib_file = run_folder / f"step_{step:03d}.grib2"
        data = ler_passo(grib_file)
        current = data["tp"]
        if current["cycle"] != run or current["step"] != step:
            raise RuntimeError(f"Run ou passo diferente dentro de {grib_file.name}")
        for n in ("10fg", "10u", "10v"):
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
        previous = current

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

    criar_html(run.strftime("%d/%m/%Y %H:%M"), steps, out)
    print("\nCONCLUÍDO")
    print("Ficheiros PNG:", len(steps) * 2)
    print("Abrir no navegador:", out / "MeteoFox_animacao_48h.html")


if __name__ == "__main__":
    main()
