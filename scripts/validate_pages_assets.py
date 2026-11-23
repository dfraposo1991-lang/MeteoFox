#!/usr/bin/env python3
"""Shared MeteoFox Pages asset guard. Fails closed before deployment."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "index.html", "mapa.html", "space-weather.html", "laboratorio.html",
    "meteofox-logo.png", "MeteoFox_icon_v1_solid.svg",
    "meteofox-favicon-32.png", "meteofox_satelite.js",
    "meteofox_fog_mask.js", "meteofox_ru_aviation.js",
    "meteofox_meteograma.js", "meteofox_meteograma.css",
    "meteofox_keyboard.js", "fox_verified.js", "fox_verified.css",
    "meteofox_conveccao.js", "fox-verified-skewt.html",
)
OPTIONAL = ("favicon.ico", "MeteoFox_logo_v1.svg")

def main():
    public = Path(sys.argv[1] if len(sys.argv) > 1 else "public")
    public.mkdir(parents=True, exist_ok=True)
    import shutil
    for name in REQUIRED:
        source = ROOT / name
        if not source.is_file() or source.stat().st_size < 100:
            raise RuntimeError(f"Required source missing/empty: {name}")
        # Shared package guarantees identical assets in both deploy workflows.
        shutil.copy2(source, public / name)
    for name in OPTIONAL:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, public / name)
    for page in ("index.html", "mapa.html"):
        html = (public / page).read_text(encoding="utf-8")
        for asset in ("MeteoFox_icon_v1_solid.svg", "meteofox-favicon-32.png"):
            if asset not in html:
                raise RuntimeError(f"{page} does not reference {asset}")
    map_html = (public / "mapa.html").read_text(encoding="utf-8")
    if "meteofox_satelite.js" not in map_html:
        raise RuntimeError("mapa.html does not reference satellite JS")
    for asset in REQUIRED:
        if not (public / asset).is_file():
            raise RuntimeError(f"Missing in Pages package: {asset}")
    print(f"PASS: {len(REQUIRED)} essential MeteoFox files packaged and checked")

if __name__ == "__main__":
    main()
