#!/usr/bin/env python3
"""Produtos experimentais MeteoFox ECMWF: meteograma Lisboa 120h e Skew-T 3 cidades.

Processo ISOLADO: nunca modifica index.html, mapa.html, satélite ou os 32 PNG.
Obtenção ECMWF IFS Open Data 0p25 de um ÚNICO ciclo, mais leve que 0p1.
Saída: produtos_experimentais/previsao_ecmwf.json (só após validação total).
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import tempfile

LOCATIONS = {
    "Lisboa": (38.72, -9.14),
    "Porto": (41.15, -8.61),
    "Beja": (38.02, -7.86),
}
LEVELS = (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200)
METEOGRAM_STEPS = tuple(range(3, 121, 3))
SOUNDING_STEPS = (0, 6, 12, 18, 24, 30, 36, 42, 48)
SURFACE_PARAMS = ("2t", "2d", "msl", "tcc", "tp", "10u", "10v", "10fg")
PRESSURE_PARAMS = ("t", "r", "u", "v")
KT = 1.9438444924406
UTC = timezone.utc


def kelvin_c(k):
    return round(float(k) - 273.15, 2)


def dewpoint_from_rh(t_kelvin, relative_humidity):
    """Ponto de orvalho aproximado por Magnus, T em K, RH em %."""
    t_c = float(t_kelvin) - 273.15
    rh = max(0.01, min(100.0, float(relative_humidity)))
    a, b = 17.625, 243.04
    gamma = math.log(rh / 100.0) + a * t_c / (b + t_c)
    return round(b * gamma / (a - gamma), 2)


def speed_direction(u, v):
    u, v = float(u), float(v)
    speed = math.hypot(u, v) * KT
    direction = (math.degrees(math.atan2(-u, -v)) + 360) % 360
    return round(speed, 1), round(direction)


def precipitation_interval(total_mm, previous_mm):
    if previous_mm is None:
        return round(max(0.0, total_mm), 2)
    # Diferença entre acumulados do mesmo ciclo: jamais misturar runs.
    return round(max(0.0, total_mm - previous_mm), 2)


def parse_cycle(text):
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    if dt.hour not in (0, 6, 12, 18) or any((dt.minute, dt.second, dt.microsecond)):
        raise ValueError("Ciclo UTC inválido")
    return dt


def extract_grib(path, expected_step, expected_cycle, expected_params, locations):
    """Seleciona apenas o ponto de grelha mais próximo de cada localidade."""
    from eccodes import (
        codes_get, codes_grib_find_nearest, codes_grib_new_from_file,
        codes_release,
    )
    found = {}
    with path.open("rb") as stream:
        while True:
            gid = codes_grib_new_from_file(stream)
            if gid is None:
                break
            try:
                param = str(codes_get(gid, "shortName"))
                if param not in expected_params:
                    continue
                step = int(codes_get(gid, "endStep"))
                date = str(codes_get(gid, "dataDate"))
                time = int(codes_get(gid, "dataTime"))
                cycle = datetime.strptime(f"{date}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=UTC)
                if step != expected_step or cycle != expected_cycle:
                    raise ValueError(f"GRIB inesperado: {param} passo {step}, ciclo {cycle}")
                level = int(codes_get(gid, "level")) if any("@" in k for k in expected_params[param]) else None
                key = f"{param}@{level}" if level is not None else param
                if key not in expected_params[param]:
                    continue
                units = str(codes_get(gid, "units"))
                result = {}
                for name, (lat, lon) in locations.items():
                    nearest = codes_grib_find_nearest(gid, lat, lon)
                    hit = nearest[0] if isinstance(nearest, list) else nearest
                    result[name] = float(hit.value)
                found[key] = (result, units)
            finally:
                codes_release(gid)
    required = {key for keys in expected_params.values() for key in keys}
    missing = required.difference(found)
    if missing:
        raise ValueError(f"GRIB incompleto em {path.name}: {sorted(missing)}")
    return found


def checked_value(data, key, location, allowed_units):
    values, units = data[key]
    if units not in allowed_units:
        raise ValueError(f"Unidade inesperada {key}: {units}")
    val = float(values[location])
    if not math.isfinite(val) or abs(val) > 1e20:
        raise ValueError(f"Dado não finito {key} {location}")
    return val


def build_surface_row(data, step, cycle, prev_tp):
    loc = "Lisboa"
    temp = kelvin_c(checked_value(data, "2t", loc, {"K"}))
    dew = kelvin_c(checked_value(data, "2d", loc, {"K"}))
    msl = checked_value(data, "msl", loc, {"Pa"})
    cloud = checked_value(data, "tcc", loc, {"(0 - 1)", "0-1", "1", "%"})
    cloud_units = data["tcc"][1]
    if cloud_units != "%":
        cloud *= 100
    tp = checked_value(data, "tp", loc, {"m", "mm", "kg m**-2", "kg m-2"})
    if data["tp"][1] == "m":
        tp *= 1000
    u = checked_value(data, "10u", loc, {"m s**-1", "m s-1", "m/s", "m s^-1"})
    v = checked_value(data, "10v", loc, {"m s**-1", "m s-1", "m/s", "m s^-1"})
    gust = checked_value(data, "10fg", loc, {"m s**-1", "m s-1", "m/s", "m s^-1"})
    wind_kt, direction = speed_direction(u, v)
    row = {
        "step_h": step,
        "valid_utc": (cycle + timedelta(hours=step)).isoformat().replace("+00:00", "Z"),
        "temp_c": temp, "dewpoint_c": dew, "pressure_hpa": round(msl / 100, 1),
        "cloud_percent": round(min(100, max(0, cloud)), 1),
        "rain_3h_mm": precipitation_interval(tp, prev_tp),
        "wind_kt": wind_kt, "wind_dir_deg": direction,
        "gust_kt": round(gust * KT, 1),
    }
    return row, tp


def build_sounding(data, step, cycle):
    by_city = {}
    for name in LOCATIONS:
        layers = []
        for level in LEVELS:
            t = checked_value(data, f"t@{level}", name, {"K"})
            rh = checked_value(data, f"r@{level}", name, {"%"})
            u = checked_value(data, f"u@{level}", name, {"m s**-1", "m s-1", "m/s", "m s^-1"})
            v = checked_value(data, f"v@{level}", name, {"m s**-1", "m s-1", "m/s", "m s^-1"})
            wind, direction = speed_direction(u, v)
            layers.append({"hpa": level, "temp_c": kelvin_c(t),
                           "dewpoint_c": dewpoint_from_rh(t, rh),
                           "rh_percent": round(rh, 1), "wind_kt": wind,
                           "wind_dir_deg": direction})
        by_city[name] = layers
    return {
        "step_h": step,
        "valid_utc": (cycle + timedelta(hours=step)).isoformat().replace("+00:00", "Z"),
        "cities": by_city,
    }


def request(client, cycle, step, params, target, levtype="sfc", levels=None):
    kwargs = {
        "date": cycle.strftime("%Y%m%d"), "time": cycle.hour,
        "stream": "oper", "type": "fc", "levtype": levtype, "step": step,
        "param": list(params), "target": str(target),
    }
    if levels:
        kwargs["levelist"] = list(levels)
    target.unlink(missing_ok=True)
    client.retrieve(**kwargs)
    if not target.exists() or target.stat().st_size < 1000:
        raise RuntimeError(f"Descarregamento incompleto: {levtype} +{step}")


def produce(cycle, output):
    from ecmwf.opendata import Client
    client = Client(source="ecmwf", model="ifs", resol="0p25")
    surface_required = {p: {p} for p in SURFACE_PARAMS}
    level_required = {p: {f"{p}@{level}" for level in LEVELS} for p in PRESSURE_PARAMS}
    result = {
        "model": "ECMWF IFS Open Data", "resolution": "0p25",
        "run_utc": cycle.isoformat().replace("+00:00", "Z"),
        "license": "ECMWF Open Data, CC BY 4.0",
        "locations": {n: {"latitude": lat, "longitude": lon} for n, (lat, lon) in LOCATIONS.items()},
        "meteogram_lisboa": [], "soundings": [],
    }
    with tempfile.TemporaryDirectory(prefix="meteofx_experimental_") as temp:
        scratch = Path(temp)
        previous = None
        for step in METEOGRAM_STEPS:
            print(f"ECMWF +{step:03d} h | superfície", flush=True)
            path = scratch / "surface.grib2"
            request(client, cycle, step, SURFACE_PARAMS, path)
            fields = extract_grib(path, step, cycle, surface_required, {"Lisboa": LOCATIONS["Lisboa"]})
            row, previous = build_surface_row(fields, step, cycle, previous)
            result["meteogram_lisboa"].append(row)
            if step in SOUNDING_STEPS:
                print(f"ECMWF +{step:03d} h | 10 níveis de pressão", flush=True)
                path = scratch / "pressure.grib2"
                request(client, cycle, step, PRESSURE_PARAMS, path, levtype="pl", levels=LEVELS)
                fields = extract_grib(path, step, cycle, level_required, LOCATIONS)
                result["soundings"].append(build_sounding(fields, step, cycle))
        # Sondagem inicial +0, sem precisar de alterar os 40 passos do meteograma.
        step = 0
        path = scratch / "pressure.grib2"
        request(client, cycle, step, PRESSURE_PARAMS, path, levtype="pl", levels=LEVELS)
        fields = extract_grib(path, step, cycle, level_required, LOCATIONS)
        result["soundings"].insert(0, build_sounding(fields, step, cycle))
    if len(result["meteogram_lisboa"]) != 40 or len(result["soundings"]) != len(SOUNDING_STEPS):
        raise RuntimeError("Produtos experimentais incompletos: a saída anterior será preservada")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_out = output.with_suffix(".tmp")
    temp_out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    temp_out.replace(output)
    print(f"CONCLUÍDO: {output} | 40 pontos meteograma, 9 horas de sondagem")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", required=True, help="Ciclo fixo YYYY-MM-DDTHH:MM:SSZ")
    parser.add_argument("--output", default="produtos_experimentais/previsao_ecmwf.json")
    args = parser.parse_args()
    produce(parse_cycle(args.cycle), Path(args.output))


if __name__ == "__main__":
    main()
