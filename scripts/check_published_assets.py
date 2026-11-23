#!/usr/bin/env python3
"""Post-deployment smoke check for public MeteoFox static assets."""
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import time
import sys

BASE = "https://dfraposo1991-lang.github.io/MeteoFox/"
FILES = (
    "index.html", "mapa.html", "meteofox-logo.png",
    "MeteoFox_icon_v1_solid.svg", "meteofox-favicon-32.png",
    "meteofox_satelite.js", "meteofox_fog_mask.js",
    "laboratorio.html", "meteofox_analysis.js",
)
def check(name):
    req = Request(BASE + name + "?health=" + str(int(time.time())),
                  headers={"Cache-Control": "no-cache", "User-Agent": "MeteoFox-pages-smoke/1.0"})
    with urlopen(req, timeout=20) as response:
        data = response.read(1_000_000)
        if response.status != 200 or len(data) < 100:
            raise RuntimeError(f"{name}: empty or HTTP {response.status}")
        if name.endswith(".png") and not data.startswith(bytes((137,80,78,71,13,10,26,10))):
            raise RuntimeError(f"{name}: invalid PNG")
        if name.endswith(".svg") and b"<svg" not in data[:5000]:
            raise RuntimeError(f"{name}: invalid SVG")
        if name == "laboratorio.html" and b"meteofox_analysis.js" not in data:
            raise RuntimeError("laboratorio.html: Fox Analysis reference missing")
        if name == "meteofox_analysis.js" and b"MeteoFoxAnalysis" not in data:
            raise RuntimeError("meteofox_analysis.js: Fox Analysis code missing")
        if name.endswith(".js") and b"<html" in data[:200].lower():
            raise RuntimeError(f"{name}: HTML returned instead of JS")
        return len(data)

def main():
    failures = {}
    for attempt in range(6):
        failures = {}
        for name in FILES:
            try:
                size = check(name)
                print(f"OK {name}: {size} bytes", flush=True)
            except (HTTPError, URLError, OSError, RuntimeError) as exc:
                failures[name] = str(exc)
        if not failures:
            print("PASS: public MeteoFox assets accessible", flush=True)
            return 0
        print(f"Attempt {attempt + 1}/6: {failures}", flush=True)
        if attempt < 5:
            time.sleep(15)
    print("FAIL: public site missing essential resources", failures, file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
