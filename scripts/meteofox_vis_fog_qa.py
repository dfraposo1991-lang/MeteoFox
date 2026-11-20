#!/usr/bin/env python3
"""MeteoFox | Avaliação visual VIS / FOG Auto com imagens reais da EUMETSAT.

Gera contacto GeoColour / Fog / híbrido atual / mistura ideal para três
horários do mesmo dia (quando os produtos têm imagens válidas).
Não altera o site, não recorre a imagens fictícias e nunca publica os
resultados como observações operacionais.
"""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json
import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageStat

WMS = "https://view.eumetsat.int/geoserver/wms"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "relatorios" / "vis_fog"
BBOX = (-18.0, 32.0, 8.0, 49.0)  # lonmin, latmin, lonmax, latmax
W, H = 480, 320
SAT_OPACITY = 0.8
SAMPLES = ("12:00", "17:00", "19:00")
URL_HEADERS = {"User-Agent": "MeteoFox-visual-QA/1.0"}

def fetch_image(layer, utc):
    params = urlencode({
        "service": "WMS", "version": "1.1.1", "request": "GetMap",
        "layers": layer, "styles": "", "format": "image/png",
        "transparent": "true", "srs": "EPSG:4326",
        "bbox": ",".join(map(str, BBOX)), "width": W, "height": H,
        "time": utc,
    })
    with urlopen(Request(WMS + "?" + params, headers=URL_HEADERS), timeout=55) as res:
        raw = res.read(2_000_001)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 5000:
        raise ValueError(f"Camada {layer} devolveu conteúdo inválido")
    image = Image.open(BytesIO(raw)).convert("RGBA")
    if image.size != (W,H): raise ValueError(f"Dimensões inválidas: {image.size}")
    stat = ImageStat.Stat(image.convert("RGB"))
    if max(stat.stddev) < 4: raise ValueError(f"Imagem demasiado uniforme: {layer}")
    return image

def solar(date):
    day = date.timetuple().tm_yday
    hour = date.hour + date.minute/60 + date.second/3600
    gamma = 2*math.pi/365*(day-1+(hour-12)/24)
    eq = 229.18*(.000075+.001868*math.cos(gamma)-.032077*math.sin(gamma)-
                 .014615*math.cos(2*gamma)-.040849*math.sin(2*gamma))
    dec = (.006918-.399912*math.cos(gamma)+.070257*math.sin(gamma)-
           .006758*math.cos(2*gamma)+.000907*math.sin(2*gamma)-
           .002697*math.cos(3*gamma)+.00148*math.sin(3*gamma))
    return hour*60+eq, dec

def fog_weight(lat, lon, state):
    minutes, dec = state
    lt=math.radians(lat)
    ha=math.radians((minutes+4*lon)/4-180)
    dot=math.sin(lt)*math.sin(dec)+math.cos(lt)*math.cos(dec)*math.cos(ha)
    alt=math.degrees(math.asin(max(-1,min(1,dot))))
    t=max(0,min(1,(3-alt)/9))
    return t*t*(3-2*t)

def build_mask(utc):
    state=solar(utc)
    alpha=Image.new("L",(W,H))
    pix=alpha.load()
    lon0,lat0,lon1,lat1=BBOX
    for y in range(H):
        lat=lat1-(y+.5)*(lat1-lat0)/H
        for x in range(W):
            lon=lon0+(x+.5)*(lon1-lon0)/W
            pix[x,y]=round(255*fog_weight(lat,lon,state))
    return alpha

def preview(geo, fog, mask):
    # Browser actual: GeoColour opacity .8, Fog opacity .8*solar mask.
    backdrop=Image.new("RGBA",(W,H),(12,33,51,255))
    geo_layer=geo.copy()
    geo_layer.putalpha(geo.getchannel("A").point(lambda a: round(a*SAT_OPACITY)))
    shown=Image.alpha_composite(backdrop,geo_layer)
    fog_alpha=fog.getchannel("A")
    mix=Image.eval(mask,lambda a:round(a*SAT_OPACITY))
    from PIL import ImageChops
    fog_layer=fog.copy()
    fog_layer.putalpha(ImageChops.multiply(fog_alpha,mix))
    shown=Image.alpha_composite(shown,fog_layer)
    # Comparator: physically intuitive crossfade before a common opacity.
    ideal=Image.composite(fog,geo,mask)
    ideal.putalpha(Image.eval(ideal.getchannel("A"),lambda a:round(a*SAT_OPACITY)))
    ideal=Image.alpha_composite(backdrop,ideal)
    # Measure RGB difference of the two approaches.
    import PIL.ImageChops as Chops
    diff=ImageStat.Stat(Chops.difference(shown.convert("RGB"),ideal.convert("RGB")))
    return shown.convert("RGB"),ideal.convert("RGB"),sum(diff.mean)/3

def label_panel(im,label,weight):
    panel=Image.new("RGB",(W,H+32),(17,35,52))
    panel.paste(im.convert("RGB"),(0,32))
    draw=ImageDraw.Draw(panel)
    draw.text((9,9),label,fill=(255,255,255))
    return panel

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Use reference date of confirmed GeoColour WMS frames, never future hours.
    data=json.loads((ROOT/"data"/"satellite_times.json").read_text())
    dates=[datetime.fromisoformat(t.replace("Z","+00:00")) for t in data.get("times_utc",[])]
    if not dates: raise ValueError("Faltam horários Meteosat confirmados")
    day=max(dates).date()
    latest=max(dates)
    report={
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "source":"EUMETSAT WMS rgb_geocolour and rgb_fog",
        "wms_bbox":BBOX, "size":[W,H],
        "alpha":SAT_OPACITY,
        "samples":[], "limitations":[
            "Hybrid/browser screenshot is approximated over a uniform dark backdrop, not a live map capture",
            "WMS RGB imagery may differ from acquisition-second time; UTC WMS TIME is identical",
            "Reported ideal hybrid is a reference comparator, not the current browser renderer"
        ]
    }
    sheets=[]
    for hour in SAMPLES:
        dt=datetime.fromisoformat(f"{day}T{hour}:00+00:00")
        item={"requested_utc":dt.isoformat().replace("+00:00","Z"),"ok":False}
        if dt>latest:
            item["reason"]="Instant later than last confirmed GeoColour timestamp"
            report["samples"].append(item);continue
        try:
            geo=fetch_image("mtg_fd:rgb_geocolour",item["requested_utc"])
            fog=fetch_image("mtg_fd:rgb_fog",item["requested_utc"])
            mask=build_mask(dt)
            hybrid,ideal,diff=preview(geo,fog,mask)
            mask_avg=ImageStat.Stat(mask).mean[0]/255
            item.update(ok=True,mean_fog_weight=round(mask_avg,3),
                mean_rgb_difference_actual_vs_ideal=round(diff,2),
                geo_alpha_mean=round(ImageStat.Stat(geo.getchannel("A")).mean[0]/255,3),
                fog_alpha_mean=round(ImageStat.Stat(fog.getchannel("A")).mean[0]/255,3))
            row=Image.new("RGB",(W*4,H+32),(17,35,52))
            for i,(name,im) in enumerate([
                ("GeoColour",geo),("Fog RGB",fog),
                ("VIS / FOG Auto - atual",hybrid),("Mistura ideal - referência",ideal)]):
                row.paste(label_panel(im,name,mask_avg),(i*W,0))
            sheets.append((hour,row))
        except Exception as err:
            item["reason"]=str(err)[:280]
        report["samples"].append(item)
        print(json.dumps(item,ensure_ascii=False),flush=True)
    if sheets:
        board=Image.new("RGB",(W*4,(H+32)*len(sheets)),(17,35,52))
        for i,(_,row) in enumerate(sheets):board.paste(row,(0,(H+32)*i))
        board.save(OUT/"comparacao_vis_fog.png",optimize=True)
    (OUT/"avaliacao.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    if len(sheets)<2:raise SystemExit("Faltam pelo menos duas amostras válidas para avaliação visual")
    print("Avaliação visual criada:",OUT/"comparacao_vis_fog.png")

if __name__=="__main__":
    main()
