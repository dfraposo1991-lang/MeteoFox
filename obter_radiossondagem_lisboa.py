#!/usr/bin/env python3
"""Importa radiossondagens REAIS 12Z de Lisboa (08579), nunca dados simulados."""
import csv
import io
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "produtos_experimentais" / "radiossondagem_lisboa.json"
BASE = "https://weather.uwyo.edu/wsgi/sounding"
STATION = "08579"
KNOTS_PER_MS = 1.9438444924

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def dewpoint_from_rh(t, rh):
    rh = min(100.0, max(0.1, rh))
    gamma = math.log(rh / 100.0) + 17.625 * t / (243.04 + t)
    return 243.04 * gamma / (17.625 - gamma)

def parse_csv(raw):
    lines = raw.lstrip("\ufeff").splitlines()
    header_index = next((i for i, line in enumerate(lines) if "pressure_hPa" in line and "temperature_C" in line), None)
    if header_index is None:
        raise ValueError("Resposta sem cabeçalho CSV de radiossondagem")
    reader = csv.DictReader(lines[header_index:])
    if not {"pressure_hPa", "temperature_C", "relative humidity_%", "wind direction_degree", "wind speed_m/s"}.issubset(reader.fieldnames or []):
        raise ValueError("Colunas necessárias em falta")
    levels = []
    for row in reader:
        p = number(row.get("pressure_hPa"))
        t = number(row.get("temperature_C"))
        rh = number(row.get("relative humidity_%"))
        direction = number(row.get("wind direction_degree"))
        speed = number(row.get("wind speed_m/s"))
        height = number(row.get("geopotential height_m"))
        if (p is None or t is None or rh is None or direction is None or speed is None
                or not 100 <= p <= 1050 or not -110 <= t <= 60 or not 0 <= rh <= 110
                or not 0 <= direction <= 360 or not 0 <= speed <= 150):
            continue
        td = dewpoint_from_rh(t, rh)
        if td > t + 0.1:
            continue
        levels.append({"hpa": round(p, 2), "temp_c": round(t, 2),
                       "dewpoint_c": round(td, 2), "rh_percent": round(rh, 1),
                       "wind_kt": round(speed * KNOTS_PER_MS, 2) if speed is not None and 0 <= speed <= 150 else None,
                       "wind_dir_deg": round(direction, 1) if direction is not None and 0 <= direction <= 360 else None,
                       "height_m": height})
    levels.sort(key=lambda x: -x["hpa"])
    unique = []
    for row in levels:
        if not unique or unique[-1]["hpa"] - row["hpa"] >= 0.15:
            unique.append(row)
    if len(unique) < 8 or unique[0]["hpa"] < 850 or unique[-1]["hpa"] > 300:
        raise ValueError(f"Perfil insuficiente: {len(unique)} níveis, superfície/topo inadequados")
    return unique

def get_sounding(day):
    nominal = day.strftime("%Y-%m-%dT12:00:00Z")
    errors = []
    for format_name in ("FM35", "BUFR"):
        query = urlencode({"datetime": day.strftime("%Y-%m-%d 12:00:00"), "id": STATION,
                           "type": "TEXT:CSV", "src": format_name})
        url = BASE + "?" + query
        try:
            request = Request(url, headers={"User-Agent": "MeteoFox/1.0 (meteorological verification)"})
            with urlopen(request, timeout=35) as response:
                raw = response.read(3_000_000).decode("utf-8", errors="replace")
            levels = parse_csv(raw)
            return {"valid_utc": nominal, "station": STATION, "levels": levels,
            "source_url": url, "source": "University of Wyoming, " + format_name,
            "dewpoint_method": "Calculado a partir de T e HR observadas (Magnus)"}
        except Exception as exc:
            errors.append(f"{format_name}: {exc} ({url})")
    raise ValueError("; ".join(errors))

def main():
    now = datetime.now(timezone.utc)
    # A sondagem 12Z do próprio dia pode demorar a ser publicada.
    days = [(now - timedelta(days=i)).date() for i in range(0, 10)]
    previous = {}
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    found = {x["valid_utc"]: x for x in previous.get("soundings", []) if isinstance(x, dict) and "valid_utc" in x}
    for day in days:
        key = day.strftime("%Y-%m-%dT12:00:00Z")
        if datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=12) > now:
            continue
        try:
            sounding = get_sounding(day)
            found[key] = sounding
            print(f"OBSERVADO {key}: {len(sounding['levels'])} níveis")
        except Exception as exc:
            print(f"INDISPONÍVEL {key}: {exc}", flush=True)
    soundings = sorted(found.values(), key=lambda x: x["valid_utc"], reverse=True)[:14]
    if not soundings:
        raise SystemExit("Nenhuma radiossondagem real disponível nos últimos 10 dias para 08579. Verificar se a estação publica TEMP/BUFR no arquivo Wyoming; não criar dados fictícios.")
    payload = {"station": STATION, "name": "Lisboa / Gago Coutinho",
               "updated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "University of Wyoming radiosonde archive, TEMP FM35",
               "soundings": soundings}
    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Guardadas {len(soundings)} sondagens reais.")

if __name__ == "__main__":
    main()
