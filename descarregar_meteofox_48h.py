#!/usr/bin/env python3
"""MeteoFox — descarrega um Run IFS 0.1°, 3h..48h, 4 campos por passo.

No PowerShell Windows:
  py "C:\\Users\\dfrap\\Desktop\\METEO FOX\\descarregar_meteofox_48h.py"

Acesso aos dados ECMWF Open Data (CC BY 4.0).
"""
from pathlib import Path
from datetime import datetime, timezone
import os
import json
import time

from ecmwf.opendata import Client

BASE = Path(__file__).resolve().parent
RAIZ = BASE / "dados_meteofox_48h"
RAIZ.mkdir(exist_ok=True)
PASSOS = list(range(9, 55, 3))
PARAMETROS = ["tp", "10fg", "10u", "10v"]


def descarregar():
    print("MeteoFox | ECMWF IFS 0,1° | 9 h a 54 h")
    print("Campos:", ", ".join(PARAMETROS))
    print("16 passos, um unico Run, com 3h de intervalo")
    client = Client(source="ecmwf", model="ifs", resol="0p1")

    # Primeiro passo determina o Run disponivel. Não misturar ciclos.
    temporario = RAIZ / "_primeiro_passo.grib2"
    if temporario.exists():
        temporario.unlink()
    print("\nA consultar o Run disponivel...", flush=True)
    # O GitHub Actions fixa o run confirmado no pré-teste de disponibilidade.
    # Não mudar silenciosamente para um ciclo anterior caso faltem dados.
    expected_raw = os.environ.get("ECMWF_EXPECTED_RUN_UTC")
    options = {}
    if expected_raw:
        expected = datetime.fromisoformat(expected_raw.replace("Z", "+00:00"))
        options = {"date": expected.strftime("%Y%m%d"), "time": expected.hour}
    result = client.retrieve(
        stream="oper", type="fc", levtype="sfc", step=9,
        param=PARAMETROS, target=str(temporario), **options
    )
    ciclo = result.datetime
    if isinstance(ciclo, str):
        ciclo = datetime.fromisoformat(ciclo.replace("Z", "+00:00"))
    if expected_raw:
        if ciclo.tzinfo is None:
            ciclo = ciclo.replace(tzinfo=timezone.utc)
        if ciclo.astimezone(timezone.utc) != expected:
            raise RuntimeError(f"Ciclo inesperado: pedido {expected}, recebido {ciclo}")
    pasta_run = RAIZ / ciclo.strftime("run_%Y%m%d_%H")
    pasta_run.mkdir(parents=True, exist_ok=True)
    destino = pasta_run / "step_009.grib2"
    temporario.replace(destino)
    print("Run encontrado:", ciclo, "UTC")
    print("+09 h: OK —", round(destino.stat().st_size / 1048576, 2), "MB", flush=True)

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
