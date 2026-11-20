#!/usr/bin/env python3
# MeteoFox — carta de precipitação ECMWF, estilo meteorológico clássico.
# Versão baseada na v15, limitada entre 16°W e 6°W e com margens mínimas.
# Executar no Ubuntu/WSL, na pasta com ecmwf_precipitacao.grib2:
#   python3 mapa_chuva_meteofox_v15_16W_6W.py
#
# Dependências:
#   sudo apt install -y libeccodes-tools python3-eccodes python3-numpy python3-matplotlib python3-cartopy
#
# Precipitação <= 0,2 mm: NÃO representada.
# Fonte: ECMWF IFS Open Data — CC BY 4.0.

from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import FixedLocator
from eccodes import (
    codes_grib_new_from_file, codes_get, codes_get_array, codes_release
)
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter

# Área: Portugal continental + Atlântico próximo até 16°W.
OESTE, ESTE = -16.0, -6.0
SUL, NORTE = 34.5, 45.0
LIMIAR_MM = 0.2

PASTA = Path(__file__).resolve().parent
FICHEIRO_GRIB = PASTA / "ecmwf_precipitacao.grib2"
SAIDA = PASTA / "mapa_chuva_meteofox_v15_16W_6W_run.png"


def ler_grib(caminho):
    with caminho.open("rb") as f:
        gid = codes_grib_new_from_file(f)
        if gid is None:
            raise RuntimeError("O ficheiro GRIB2 não contém mensagens.")
        try:
            variavel = codes_get(gid, "shortName")
            unidade = codes_get(gid, "units")
            ni = int(codes_get(gid, "Ni"))
            nj = int(codes_get(gid, "Nj"))
            passo = int(codes_get(gid, "step"))
            dia = str(codes_get(gid, "dataDate"))
            hora = int(codes_get(gid, "dataTime"))

            latitudes = codes_get_array(gid, "latitudes").reshape(nj, ni)
            longitudes = codes_get_array(gid, "longitudes").reshape(nj, ni)
            dados = codes_get_array(gid, "values").reshape(nj, ni)
        finally:
            codes_release(gid)

    if variavel != "tp":
        raise ValueError(f"Era esperada a variável 'tp', não '{variavel}'.")

    if unidade == "m":
        dados = dados * 1000.0
    elif unidade not in ("mm", "kg m**-2", "kg m-2"):
        raise ValueError(f"Unidade inesperada: {unidade}. Verifica o GRIB.")

    longitudes = np.where(longitudes > 180, longitudes - 360, longitudes)

    selecao = (
        (longitudes >= OESTE - 0.1) &
        (longitudes <= ESTE + 0.1) &
        (latitudes >= SUL - 0.1) &
        (latitudes <= NORTE + 0.1)
    )
    linhas, colunas = np.where(selecao)
    if len(linhas) == 0:
        raise RuntimeError("Área geográfica não encontrada no GRIB.")

    a, b = int(linhas.min()), int(linhas.max())
    c, d = int(colunas.min()), int(colunas.max())
    lats = latitudes[a:b+1, c].copy()
    lons = longitudes[a, c:d+1].copy()
    chuva = np.maximum(dados[a:b+1, c:d+1].astype(float), 0.0)

    if lats[0] > lats[-1]:
        lats = lats[::-1]
        chuva = chuva[::-1, :]
    if lons[0] > lons[-1]:
        lons = lons[::-1]
        chuva = chuva[:, ::-1]

    ciclo = datetime.strptime(
        f"{dia}{hora:04d}", "%Y%m%d%H%M"
    ).replace(tzinfo=timezone.utc)
    validade = ciclo + timedelta(hours=passo)
    return lons, lats, chuva, ciclo, validade, passo



_DIAS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def legenda_utc(data):
    """Data da validade e do run, em UTC e sem ano."""
    return f"{_DIAS_PT[data.weekday()]}, {data:%d/%m}, {data:%H:%M} UTC"


def criar_mapa():
    if not FICHEIRO_GRIB.exists():
        raise FileNotFoundError(
            f"Não encontrei {FICHEIRO_GRIB.name} na pasta {PASTA}"
        )

    lons, lats, chuva, ciclo, validade, passo = ler_grib(FICHEIRO_GRIB)

    limites = [0.2, 0.5, 1, 2, 3, 4, 5, 7, 10, 15, 20, 50]
    cores = [
        "#48D0EF",
        "#17BCCC",
        "#19AA80",
        "#21A54A",
        "#57B913",
        "#9AD90B",
        "#DBF000",
        "#FFE324",
        "#FF9D1C",
        "#EF482C",
        "#C8131C",
    ]
    cmap = ListedColormap(cores, name="MeteoFox_precipitacao")
    cmap.set_over("#710A0C")
    norm = BoundaryNorm(limites, ncolors=cmap.N)

    proj = ccrs.PlateCarree()
    # Figura mais compacta para reduzir margens brancas mantendo o estilo v15.
    fig = plt.figure(figsize=(9.7, 10.0), facecolor="white")

    # Área cartográfica mais ampla.
    ax = fig.add_axes([0.025, 0.035, 0.85, 0.865], projection=proj)
    ax.set_extent([OESTE, ESTE, SUL, NORTE], crs=proj)
    ax.set_facecolor("#FFFFFF")
    ax.add_feature(
        cfeature.LAND.with_scale("10m"),
        facecolor="#FCFCFC", edgecolor="none", zorder=0
    )
    ax.add_feature(
        cfeature.OCEAN.with_scale("10m"),
        facecolor="#FFFFFF", edgecolor="none", zorder=0
    )

    campo = ax.contourf(
        lons, lats, chuva,
        levels=limites,
        cmap=cmap,
        norm=norm,
        extend="max",
        antialiased=True,
        transform=proj,
        zorder=2
    )

    ax.coastlines(resolution="10m", linewidth=0.8, color="#111111", zorder=4)
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        linewidth=0.6, edgecolor="#252525", zorder=4
    )

    xticks = np.array([-16.0, -14.0, -12.0, -10.0, -8.0, -6.0])
    yticks = np.arange(35, 46, 2.5)
    ax.set_xticks(xticks, crs=proj)
    ax.set_yticks(yticks, crs=proj)
    ax.xaxis.set_major_formatter(
        LongitudeFormatter(number_format=".1f", degree_symbol="°")
    )
    ax.yaxis.set_major_formatter(
        LatitudeFormatter(number_format=".1f", degree_symbol="°")
    )
    ax.tick_params(
        axis="both", which="major",
        labelsize=9, length=2, colors="#222222",
        top=True, labeltop=True, bottom=True, labelbottom=True,
        left=True, labelleft=True, right=True, labelright=True,
        pad=3
    )
    ax.gridlines(
        crs=proj, xlocs=FixedLocator(xticks),
        ylocs=FixedLocator(yticks),
        linewidth=0.45, color="#777777", linestyle=":", alpha=0.45,
        zorder=3
    )
    for spine in ax.spines.values():
        spine.set_linewidth(1.15)
        spine.set_edgecolor("#111111")

    barra_eixo = fig.add_axes([0.912, 0.13, 0.026, 0.70])
    barra = fig.colorbar(
        campo, cax=barra_eixo, orientation="vertical",
        ticks=[0.2, 0.5, 1, 2, 3, 4, 5, 7, 10, 15, 20, 50],
        spacing="uniform",
        extendrect=True
    )
    barra.ax.set_yticklabels(
        ["0,2", "0,5", "1", "2", "3", "4", "5", "7", "10", "15", "20", "50"]
    )
    barra.ax.tick_params(labelsize=9, length=2)
    barra.outline.set_linewidth(0.7)
    barra_eixo.set_title("mm", fontsize=10, pad=6)

    fig.text(
        0.47, 0.975, "Precipitação acumulada [mm] | ECMWF IFS",
        ha="center", va="top", fontsize=15, color="#222222"
    )
    # Run e validade aparecem uma única vez na faixa branca superior do portal.
    fig.savefig(SAIDA, dpi=165, facecolor="white", pad_inches=0.01)
    plt.close(fig)

    print("Mapa criado:", SAIDA)
    print("Resolução ECMWF: 0,1°")
    print(f"Domínio: de {OESTE:.1f}° a {ESTE:.1f}° de longitude | acumulado até +{passo} h | valores <= {LIMIAR_MM} mm não representados")
    print("Fonte: ECMWF IFS Open Data (CC BY 4.0)")


if __name__ == "__main__":
    criar_mapa()
