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
    "meteofox_conveccao.js", "meteofox_analysis.js", "fox-verified-skewt.html",
)
OPTIONAL = ("favicon.ico", "MeteoFox_logo_v1.svg")


def preserve_forecasts(public):
    """Choose a complete, internally consistent product, never mix cycles."""
    import json, math
    from datetime import datetime, timedelta
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from concurrent.futures import ThreadPoolExecutor
    base = "https://dfraposo1991-lang.github.io/MeteoFox/"
    def remote(name):
        try:
            with urlopen(Request(base + name, headers={"User-Agent":"MeteoFox", "Cache-Control":"no-cache"}), timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
    def dt(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    def collect(region, product, reader):
        prefix = f"forecast_{region}_{product}"
        index = reader(prefix + "_index.json")
        if index is None:
            return None
        cycle = dt(index["run_utc"])
        expected = set(range(9, 55 if region == "B" else 94, 3))
        frames = index["frames"]
        if {m["step"] for m in frames} != expected or len(frames) != len(expected):
            raise ValueError(f"{prefix}: incomplete forecast")
        resolution = .1 if region == "B" else (.5 if product == "thetae" else .25)
        def check(meta):
            step = meta["step"]
            name = f"{prefix}_{step:03d}.json"
            if meta["file"] != name:
                raise ValueError("Unexpected frame filename")
            data = reader(name)
            f = data["frame"]
            if dt(data["run_utc"]) != cycle or f["step"] != step or dt(f["valid_utc"]) != cycle + timedelta(hours=step):
                raise ValueError("Mixed forecast cycles")
            if dt(meta["valid_utc"]) != dt(f["valid_utc"]):
                raise ValueError("Invalid index validity")
            x, y = f["x"], f["y"]
            if f["resolution"] != resolution or any(len(a)<2 or any(abs(v-u-resolution)>1e-5 for u,v in zip(a,a[1:])) for a in (x,y)):
                raise ValueError("Invalid grid resolution")
            bounds = (-10,-6,36.9,42.2) if region == "B" else ((-65,25,25,65) if product == "thetae" else (-40,0,25,50))
            if any(abs(a-b)>resolution+1e-5 for a,b in zip((x[0],x[-1],y[0],y[-1]),bounds)):
                raise ValueError("Invalid grid bounds")
            fields = (product,"u","v") if product == "gust" else (product,)
            for field in fields:
                values = f[field]
                if len(values)!=len(y) or any(len(row)!=len(x) for row in values):
                    raise ValueError("Invalid field shape")
                if any(v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v)) for row in values for v in row):
                    raise ValueError("Invalid field values")
                if product != "ceiling" and not any(v is not None for row in values for v in row):
                    raise ValueError("Empty field")
            return name,data
        with ThreadPoolExecutor(max_workers=6) as pool:
            files = dict(pool.map(check, frames))
        files[prefix+"_index.json"] = index
        return cycle, files
    def local(name):
        p = public / name
        return json.loads(p.read_text()) if p.is_file() else None
    report = {}
    for product in ("rain","gust","thetae","visibility","ceiling","tcucb","lightning"):
        regions = ("A","B") if product in ("rain","gust","visibility","ceiling") else ("A",)
        chosen = {}
        for region in regions:
            prefix = f"forecast_{region}_{product}"
            candidates = []
            for origin, reader in (("new",local),("previous",remote)):
                try:
                    result = collect(region,product,reader)
                    if result:
                        candidates.append((result[0],origin,result[1]))
                except (ValueError,KeyError,TypeError,AttributeError) as exc:
                    print(f"{prefix} {origin}: {exc}")
            if candidates:
                chosen[region] = max(candidates,key=lambda v:v[0])
            elif any(public.glob(prefix+"_*.json")):
                raise RuntimeError(f"No complete valid replacement or fallback for {prefix}")
        if "A" not in chosen:
            report[product] = {"status":"unavailable"}
            continue
        # B is usable only when it matches A. Prefer a previous matching pair
        # over mixing regional cycles; an unmatched B remains archived on Pages.
        for region,(cycle,origin,files) in chosen.items():
            prefix = f"forecast_{region}_{product}"
            for p in public.glob(prefix+"_*.json"):
                p.unlink()
            for name,data in files.items():
                (public/name).write_text(json.dumps(data,separators=(",",":"),allow_nan=False))
            if region == "A":
                aggregate = public / (prefix+".json")
                if aggregate.exists():
                    aggregate.write_text(json.dumps({"run_utc":files[prefix+"_index.json"]["run_utc"],"frames":[files[m["file"]]["frame"] for m in files[prefix+"_index.json"]["frames"]]},separators=(",",":")))
        cycle,origin,_ = chosen["A"]
        report[product] = {"cycle_utc":cycle.isoformat(),"status":"retained" if origin=="previous" else "new","region_b_cycle_utc":chosen["B"][0].isoformat() if "B" in chosen else None}
        print(product,report[product])
    (public/"forecast_products_status.json").write_text(json.dumps(report,indent=2))

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
    preserve_forecasts(public)
    print(f"PASS: {len(REQUIRED)} essential MeteoFox files packaged and checked")

if __name__ == "__main__":
    main()
