#!/usr/bin/env python3
"""Auditoria independente MeteoFox: valida metadados e plausibilidade, nunca publica.

Usa apenas a biblioteca padrão. A saída JSON permite diagnosticar avisos sem
interferir com os processos ECMWF; anomalias críticas fazem falhar só esta auditoria.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

STEPS = list(range(9, 55, 3))
METEOGRAM_STEPS = list(range(3, 91, 3))
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200]
CITIES = {"Lisboa", "Porto", "Beja"}
BASE = "https://dfraposo1991-lang.github.io/MeteoFox/"
VIS = "https://raw.githubusercontent.com/dfraposo1991-lang/MeteoFox/main/data/satellite_vis/manifest.json"
LAB = "https://raw.githubusercontent.com/dfraposo1991-lang/MeteoFox/main/produtos_experimentais/previsao_ecmwf.json"


def utc(value):
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.utcoffset() is None:
        raise ValueError(f"Timestamp sem fuso UTC: {value}")
    return date.astimezone(timezone.utc)


def same_time(a, b):
    return utc(a) == utc(b)


def numeric(row, field, lo, hi, errors, source):
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        errors.append(f"{source}: {field} fora dos limites amplos [{lo},{hi}]: {value}")
        return None
    return value


def step_series(rows, steps, cycle, source, errors):
    if not isinstance(rows, list) or len(rows) != len(steps):
        errors.append(f"{source}: esperado {len(steps)} prazos, obtidos {len(rows) if isinstance(rows,list) else 'invalidos'}")
        return []
    for idx, (row, step) in enumerate(zip(rows, steps)):
        if not isinstance(row, dict):
            errors.append(f"{source}[{idx}]: linha inválida")
            continue
        if row.get("step_h") != step:
            errors.append(f"{source}[{idx}]: prazo {row.get('step_h')}, esperado {step}")
        try:
            valid = utc(row["valid_utc"])
            if valid != cycle + timedelta(hours=step):
                errors.append(f"{source}[{idx}]: data de validade não corresponde ao run +{step}h")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{source}[{idx}]: validade UTC inválida")
    return rows


def audit(maps, vis, lab, now=None):
    now = now or datetime.now(timezone.utc)
    errors, warnings = [], []
    cycles = {}
    # Cartas publicadas: 16 chuva + 16 rajadas, todas do mesmo ciclo.
    try:
        cycle = utc(maps["cycle_utc"])
        cycles["cartas"] = cycle.isoformat()
        files = set(maps["images"])
        expected = {f"{kind}_{step:03d}.png" for kind in ("chuva", "rajadas") for step in STEPS}
        if files != expected:
            errors.append(f"Cartas: {len(files & expected)}/32 ficheiros esperados; faltam {sorted(expected-files)}; extra {sorted(files-expected)}")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Manifesto cartas inválido: {exc}")
    # Satélite VIS: run comum, 16 prazos e validade UTC verificável.
    try:
        cycle = utc(vis["run_utc"])
        cycles["vis"] = cycle.isoformat()
        frames = step_series(vis["frames"], STEPS, cycle, "VIS", errors)
        for idx, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            if frame.get("file") != f"VIS_{STEPS[idx]:03d}.png":
                errors.append(f"VIS[{idx}]: ficheiro inesperado")
            try:
                if utc(frame["run_utc"]) != cycle:
                    errors.append(f"VIS[{idx}]: mistura de runs")
            except (KeyError, ValueError, TypeError):
                errors.append(f"VIS[{idx}]: run inválido")
        if vis.get("projection") != "opencharts_south_west_europe":
            errors.append("VIS: projeção inesperada")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Manifesto VIS inválido: {exc}")
    # Laboratório: meteograma superfície 3-90h e Skew-T 9-54h para três cidades.
    try:
        cycle = utc(lab["run_utc"])
        cycles["laboratorio"] = cycle.isoformat()
        for idx, row in enumerate(step_series(lab["meteogram_lisboa"], METEOGRAM_STEPS, cycle, "meteograma", errors)):
            label = f"meteograma[{idx}]"
            if not isinstance(row, dict):
                continue
            numeric(row, "temp_c", -85, 65, errors, label)
            numeric(row, "dewpoint_c", -105, 65, errors, label)
            numeric(row, "pressure_hpa", 850, 1100, errors, label)
            numeric(row, "cloud_percent", 0, 105, errors, label)
            numeric(row, "rain_3h_mm", 0, 500, errors, label)
            wind = numeric(row, "wind_kt", 0, 250, errors, label)
            gust = numeric(row, "gust_kt", 0, 300, errors, label)
            numeric(row, "wind_dir_deg", 0, 360, errors, label)
            if wind is not None and gust is not None and gust + 3 < wind:
                warnings.append(f"{label}: rajada inferior ao vento médio (verificar amostragem)")
            if isinstance(row.get("dewpoint_c"), (int, float)) and isinstance(row.get("temp_c"), (int, float)):
                if row["dewpoint_c"] > row["temp_c"] + 2:
                    warnings.append(f"{label}: ponto de orvalho acima da temperatura")
        for idx, sounding in enumerate(step_series(lab["soundings"], STEPS, cycle, "sondagens", errors)):
            if not isinstance(sounding, dict):
                continue
            cities = sounding.get("cities")
            if not isinstance(cities, dict) or set(cities) != CITIES:
                errors.append(f"sondagens[{idx}]: cidades incompletas")
                continue
            for city, levels in cities.items():
                source = f"sondagens[{idx}].{city}"
                if not isinstance(levels, list) or [p.get("hpa") for p in levels if isinstance(p, dict)] != LEVELS:
                    errors.append(f"{source}: níveis isobáricos incorretos")
                    continue
                for level in levels:
                    for field, lo, hi in [
                        ("temp_c", -120, 65), ("dewpoint_c", -140, 65),
                        ("rh_percent", 0, 125), ("wind_kt", 0, 300),
                        ("wind_dir_deg", 0, 360)]:
                        numeric(level, field, lo, hi, errors, f"{source}.{level['hpa']}hPa")
    except (KeyError, ValueError, TypeError) as exc:
        errors.append(f"Laboratório inválido: {exc}")
    # A publicação do VIS e laboratório pode ocorrer minutos depois das cartas;
    # runs diferentes são avisos, não falhas do modelo.
    distinct = set(cycles.values())
    if len(distinct) > 1:
        warnings.append("Produtos usam runs diferentes: " + json.dumps(cycles, ensure_ascii=False))
    for name, timestamp in cycles.items():
        age = (now - utc(timestamp)).total_seconds() / 3600
        if age > 24:
            warnings.append(f"{name}: run com {age:.1f} h de idade")
        if age < -1:
            errors.append(f"{name}: run no futuro ({age:.1f} h)")
    return {"status": "ERRO" if errors else "AVISO" if warnings else "OK",
            "checked_utc": now.isoformat(), "runs": cycles,
            "errors": errors, "warnings": warnings}


def fetch_json(url):
    req = Request(url, headers={"User-Agent": "MeteoFox-Quality-Audit/1.0", "Cache-Control": "no-cache"})
    with urlopen(req, timeout=35) as res:
        if res.status != 200:
            raise RuntimeError(f"HTTP {res.status}: {url}")
        return json.load(res)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="relatorios/qualidade_meteofox.json")
    parser.add_argument("--local", action="store_true", help="Dados disponíveis no checkout, para testes isolados")
    opts = parser.parse_args()
    try:
        if opts.local:
            data = [
                json.loads(Path(p).read_text()) for p in (
                    "meteofox_ecmwf_manifest.json",
                    "data/satellite_vis/manifest.json",
                    "produtos_experimentais/previsao_ecmwf.json")]
        else:
            data = [fetch_json(BASE+"meteofox_ecmwf_manifest.json"),
                    fetch_json(VIS), fetch_json(LAB)]
        result = audit(*data)
    except Exception as exc:
        result = {"status": "ERRO", "checked_utc": datetime.now(timezone.utc).isoformat(),
                  "errors": [f"Não foi possível consultar os produtos: {exc}"], "warnings": [], "runs": {}}
    path = Path(opts.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "ERRO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
