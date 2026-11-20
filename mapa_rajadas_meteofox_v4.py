#!/usr/bin/env python3
"""MeteoFox: carta de rajadas ECMWF IFS no estilo da chuva v15 aprovada.

Usa ECMWF GRIB2 com:
  - 10fg (rajada maxima dos desde o processamento anterior), m/s -> kt
  - 10u, 10v (componentes do vento a 10 m), direcao das setas

Executar no Ubuntu/WSL na mesma pasta do GRIB2:
  python3 mapa_rajadas_meteofox_v3.py

Exige: ecCodes, NumPy, Matplotlib e Cartopy.
A fonte dos dados e ECMWF IFS Open Data, licenca CC BY 4.0.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FixedLocator
from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter

WEST, EAST = -16.0, -6.0
SOUTH, NORTH = 34.5, 45.0
KNOTS_PER_MS = 1.9438444924406
PASTA = Path(__file__).resolve().parent
GRIB = PASTA / "ecmwf_rajadas_vento_atual.grib2"
OUTPUT = PASTA / "mapa_rajadas_meteofox_v4.png"

def read_fields(file_path):
    campos = {}
    with file_path.open("rb") as handle:
        while True:
            gid = codes_grib_new_from_file(handle)
            if gid is None:
                break
            try:
                name = str(codes_get(gid, "shortName"))
                units = str(codes_get(gid, "units"))
                ni = int(codes_get(gid, "Ni"))
                nj = int(codes_get(gid, "Nj"))
                step = int(codes_get(gid, "step"))
                date = str(codes_get(gid, "dataDate"))
                time = int(codes_get(gid, "dataTime"))
                lat = codes_get_array(gid, "latitudes").reshape(nj, ni)
                lon = codes_get_array(gid, "longitudes").reshape(nj, ni)
                val = codes_get_array(gid, "values").reshape(nj, ni)
            finally:
                codes_release(gid)

            if name not in {"10fg", "10u", "10v"}:
                continue

            lon = np.where(lon > 180, lon-360, lon)
            selection = (
                (lon >= WEST-.15) & (lon <= EAST+.15) &
                (lat >= SOUTH-.15) & (lat <= NORTH+.15)
            )
            rr, cc = np.where(selection)
            if rr.size == 0:
                continue
            r0, r1, c0, c1 = rr.min(), rr.max(), cc.min(), cc.max()
            xs = lon[r0, c0:c1+1].copy()
            ys = lat[r0:r1+1, c0].copy()
            data = val[r0:r1+1, c0:c1+1].astype(float).copy()
            if ys[0] > ys[-1]:
                ys, data = ys[::-1], data[::-1, :]
            if xs[0] > xs[-1]:
                xs, data = xs[::-1], data[:, ::-1]
            if units not in ("m s**-1", "m s-1", "m/s", "m s^-1"):
                raise ValueError(f"Unidade inesperada em {name}: {units}")
            cycle = datetime.strptime(f"{date}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
            campos[name] = dict(
                x=xs, y=ys, value=data, step=step, cycle=cycle
            )

    required = {"10fg", "10u", "10v"}
    missing = required - campos.keys()
    if missing:
        raise RuntimeError(
            "Faltam campos no GRIB2: " + ", ".join(sorted(missing)) +
            ". Verifica o descarregamento (10fg, 10u, 10v)."
        )

    first = campos["10fg"]
    for name in ("10u", "10v"):
        other = campos[name]
        if other["step"] != first["step"] or other["cycle"] != first["cycle"]:
            raise RuntimeError("As variaveis pertencem a ciclos ou horizontes diferentes.")
        if not (np.array_equal(first["x"], other["x"]) and
                np.array_equal(first["y"], other["y"])):
            raise RuntimeError("Grelhas das variaveis nao coincidem.")

    return campos

_DIAS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def legenda_utc(data):
    """Dia da semana, dia/mês e hora UTC, sem ano."""
    return f"{_DIAS_PT[data.weekday()]}, {data:%d/%m}, {data:%H:%M} UTC"


def make_map():
    if not GRIB.exists():
        raise FileNotFoundError(
            f"Nao encontrei {GRIB.name} em {PASTA}. Primeiro descarrega os dados."
        )
    fields = read_fields(GRIB)
    data = fields["10fg"]
    x, y = data["x"], data["y"]
    gust_kt = np.maximum(data["value"], 0) * KNOTS_PER_MS
    u, v = fields["10u"]["value"], fields["10v"]["value"]

    # Escala de rajadas em nos (kt); esquema de cores ajustado
    # para ficar muito proximo da tua imagem de referencia.
    levels = [0, 5, 8, 10, 12, 14, 15, 16, 17, 18, 19, 20,
              21, 22, 23, 24, 25, 26, 28, 30, 32, 34, 36,
              38, 40, 45, 50, 55, 60, 70, 80, 90, 100]
    colors = [
        "#ECECEC",  # 0-5
        "#D7E7EE",  # 5-8
        "#B9D4E4",  # 8-10
        "#A4C6DA",  # 10-12
        "#7FB3D7",  # 12-14
        "#4CA3DC",  # 14-15
        "#B5D9B8",  # 15-16
        "#8FD58F",  # 16-17
        "#57D84B",  # 17-18
        "#24C914",  # 18-19
        "#F2EDC6",  # 19-20
        "#EEE7B0",  # 20-21
        "#E7DEA1",  # 21-22
        "#E4D88B",  # 22-23
        "#E9D061",  # 23-24
        "#E9C542",  # 24-25
        "#F0BB1E",  # 25-26
        "#F2D5D5",  # 26-28
        "#E9A1A1",  # 28-30
        "#EE7272",  # 30-32
        "#FF4B4B",  # 32-34
        "#FF2020",  # 34-36
        "#D3B5E1",  # 36-38
        "#C08ED4",  # 38-40
        "#A567B6",  # 40-45
        "#82428F",  # 45-50
        "#C59A46",  # 50-55
        "#B3822C",  # 55-60
        "#996200",  # 60-70
        "#7F5200",  # 70-80
        "#B6B6B6",  # 80-90
        "#9E9E9E",  # 90-100
    ]
    cmap = ListedColormap(colors, name="MeteoFox_rajadas_ref")
    cmap.set_over("#7C7C7C")
    norm = BoundaryNorm(levels, cmap.N)

    crs = ccrs.PlateCarree()
    fig = plt.figure(figsize=(9.7, 10.0), facecolor="white")
    ax = fig.add_axes([0.025, 0.035, 0.85, 0.865], projection=crs)
    ax.set_extent([WEST, EAST, SOUTH, NORTH], crs=crs)
    ax.set_facecolor("#FFFFFF")
    ax.add_feature(cfeature.LAND.with_scale("10m"), facecolor="#FCFCFC",
                   edgecolor="none", zorder=0)
    ax.add_feature(cfeature.OCEAN.with_scale("10m"), facecolor="#FFFFFF",
                   edgecolor="none", zorder=0)

    field = ax.contourf(x, y, gust_kt, levels=levels, norm=norm,
                        cmap=cmap, extend="max", antialiased=True,
                        transform=crs, zorder=2)

    # Vetores orientados pela direcao REAL de deslocamento do vento medio.
    # Normalizacao a comprimento constante: NAO representam intensidade,
    # apenas direcao. A intensidade das rajadas e dada pelas cores.
    skip = 13   # aprox. 1 seta por 1,3 graus em cada direcao
    X, Y = np.meshgrid(x[::skip], y[::skip])
    U = u[::skip, ::skip]
    V = v[::skip, ::skip]
    speed = np.hypot(U, V)
    unit_u = np.divide(U, speed, out=np.zeros_like(U), where=speed > .3)
    unit_v = np.divide(V, speed, out=np.zeros_like(V), where=speed > .3)
    arrows = speed > .3
    ax.quiver(X[arrows], Y[arrows], unit_u[arrows], unit_v[arrows],
              color="#172B3D", pivot="middle", width=.0026,
              headwidth=3.5, headlength=4.2, headaxislength=3.8,
              scale=18, scale_units="width", angles="uv",
              transform=crs, zorder=4)

    ax.coastlines(resolution="10m", linewidth=.8, color="#141414", zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("10m"), linewidth=.6,
                   edgecolor="#252525", zorder=5)

    lon_ticks = np.arange(-16, -5.99, 2)
    lat_ticks = np.arange(35, 46, 2.5)
    ax.set_xticks(lon_ticks, crs=crs)
    ax.set_yticks(lat_ticks, crs=crs)
    ax.xaxis.set_major_formatter(LongitudeFormatter(number_format=".1f", degree_symbol="°"))
    ax.yaxis.set_major_formatter(LatitudeFormatter(number_format=".1f", degree_symbol="°"))
    ax.tick_params(axis="both", which="major", labelsize=9, length=2,
                   colors="#222222", top=True, labeltop=True,
                   bottom=True, labelbottom=True,
                   left=True, labelleft=True, right=True, labelright=True,
                   pad=3)
    ax.gridlines(crs=crs, xlocs=FixedLocator(lon_ticks),
                 ylocs=FixedLocator(lat_ticks), linewidth=.45,
                 color="#777777", linestyle=":", alpha=.45, zorder=3)
    for spine in ax.spines.values():
        spine.set_linewidth(1.15)
        spine.set_edgecolor("#111111")

    cax = fig.add_axes([0.912, 0.13, 0.026, 0.70])
    bar = fig.colorbar(field, cax=cax, orientation="vertical",
                       ticks=levels, spacing="uniform", extendrect=True)
    bar.ax.tick_params(labelsize=9, length=2)
    bar.outline.set_linewidth(.7)
    cax.set_title("kt", fontsize=10, pad=6)

    cycle, step = data["cycle"], data["step"]
    valid = cycle + timedelta(hours=step)
    fig.text(.455, .972, "Rajadas maximas 10 m [kt] | ECMWF IFS",
             ha="center", va="top", fontsize=15, color="#222222")
    # Run e validade são mostrados exclusivamente sob a imagem no portal.
    # Evitar texto duplicado dentro da carta PNG.
    fig.savefig(OUTPUT, dpi=165, facecolor="white", pad_inches=.01)
    plt.close(fig)
    print("Mapa criado:", OUTPUT)
    print("Run:", cycle, "| Validade:", valid)
    print("Rajadas maximas desde processamento anterior (kt); setas: direcao do vento a 10m")
    print("Maximo no dominio:", round(float(np.nanmax(gust_kt)), 1), "kt")
    print("Fonte: ECMWF IFS Open Data (CC BY 4.0)")

if __name__ == "__main__":
    make_map()
