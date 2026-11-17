#!/usr/bin/env python3
"""MeteoFox — descarrega um Run IFS 0.1°, 3h..48h, 4 campos por passo.

No PowerShell Windows:
  py "C:\\Users\\dfrap\\Desktop\\METEO FOX\\descarregar_meteofox_48h.py"

Acesso aos dados ECMWF Open Data (CC BY 4.0).
"""
from pathlib import Path
from datetime import datetime
import json
import time

from ecmwf.opendata import Client

BASE = Path(__file__).resolve().parent
RAIZ = BASE / "dados_meteofox_48h"
RAIZ.mkdir(exist_ok=True)
PASSOS = list(range(3, 49, 3))
PARAMETROS = ["tp", "10fg", "10u", "10v"]


def descarregar():
    print("MeteoFox | ECMWF IFS 0,1° | 3 h a 48 h")
    print("Campos:", ", ".join(PARAMETROS))
    print("16 passos, um unico Run, com 3h de intervalo")
    client = Client(source="ecmwf", model="ifs", resol="0p1")

    # Primeiro passo determina o Run disponivel. Não misturar ciclos.
    temporario = RAIZ / "_primeiro_passo.grib2"
    if temporario.exists():
        temporario.unlink()
    print("\nA consultar o Run disponivel...", flush=True)
    result = client.retrieve(
        stream="oper", type="fc", levtype="sfc", step=3,
        param=PARAMETROS, target=str(temporario)
    )
    ciclo = result.datetime
    if isinstance(ciclo, str):
        ciclo = datetime.fromisoformat(ciclo.replace("Z", "+00:00"))
    pasta_run = RAIZ / ciclo.strftime("run_%Y%m%d_%H")
    pasta_run.mkdir(parents=True, exist_ok=True)
    destino = pasta_run / "step_003.grib2"
    temporario.replace(destino)
    print("Run encontrado:", ciclo, "UTC")
    print("+03 h: OK —", round(destino.stat().st_size / 1048576, 2), "MB", flush=True)

    # Manifesto é gravado no inicio (e atualizado) para retomar downloads.
    manifesto = {
        "modelo": "ECMWF IFS", "resolucao": "0p1",
        "run": ciclo.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pasta": pasta_run.name,
        "passos": PASSOS,
        "parametros": PARAMETROS,
        "licenca": "ECMWF IFS Open Data, CC BY 4.0",
    }
    (RAIZ / "ultimo_run.json").write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    falhas = []
    for passo in PASSOS[1:]:
        destino = pasta_run / f"step_{passo:03d}.grib2"
        if destino.exists() and destino.stat().st_size > 100000:
            print(f"+{passo:02d} h: já descarregado")
            continue
        temporario = pasta_run / f"step_{passo:03d}.part"
        print(f"+{passo:02d} h: a descarregar...", flush=True)
        ok = False
        for tentativa in range(1, 4):
            try:
                if temporario.exists():
                    temporario.unlink()
                client.retrieve(
                    date=ciclo.strftime("%Y%m%d"),
                    time=ciclo.hour,
                    stream="oper", type="fc", levtype="sfc",
                    step=passo, param=PARAMETROS, target=str(temporario),
                )
                if not temporario.exists() or temporario.stat().st_size < 100000:
                    raise RuntimeError("GRIB vazio ou incompleto")
                temporario.replace(destino)
                print(f"+{passo:02d} h: OK — {destino.stat().st_size/1048576:.1f} MB", flush=True)
                ok = True
                break
            except Exception as exc:
                print(f"  Tentativa {tentativa}/3: {exc}", flush=True)
                if tentativa < 3:
                    time.sleep(4)
        if not ok:
            falhas.append(passo)

    print("\nDiretorio:", pasta_run)
    if falhas:
        print("ATENÇÃO: falharam os passos", falhas)
        print("Volta a executar este programa para tentar novamente.")
    else:
        print("Todos os 16 passos descarregados!")
        print("Agora, no Ubuntu: python3 gerar_meteofox_48h.py")


if __name__ == "__main__":
    descarregar()
