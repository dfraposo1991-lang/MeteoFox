#!/usr/bin/env python3
"""MeteoFox: confirmar os 16 passos do ciclo IFS 0,1° antes de produzir cartas.

Não descarrega ficheiros GRIB nem publica o site. Cada execução verifica a
data/hora devolvida pelo cliente ECMWF para todos os prazos solicitados.
A verificação do conteúdo GRIB continua a acontecer no descarregamento real.
"""
import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time

STEPS = tuple(range(3, 49, 3))
PARAMETERS = ("tp", "10fg", "10u", "10v")
UTC = timezone.utc

# Horários UTC de início da VERIFICAÇÃO, tendo em conta a latência do IFS 0p1.
# Chave = hora:minuto de início; valor = hora UTC do run esperado.
CHECKS = (("02:40", 18), ("09:45", 0), ("14:40", 6), ("21:45", 12))


def expected_cycle(now):
    """Determina o ciclo correspondente à última janela diária de verificação."""
    now = now.astimezone(UTC)
    minute = now.hour * 60 + now.minute
    if minute >= 21 * 60 + 45:
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    if minute >= 14 * 60 + 40:
        return now.replace(hour=6, minute=0, second=0, microsecond=0)
    if minute >= 9 * 60 + 45:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if minute >= 2 * 60 + 40:
        return (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)


def normalize_date(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def cycle_ready(client, expected):
    """False se qualquer um dos 16 prazos ainda aponta para outro ciclo."""
    for step in STEPS:
        result = client.latest(stream="oper", type="fc", levtype="sfc",
                               step=step, param=list(PARAMETERS))
        found = normalize_date(result)
        print(f"  +{step:02d} h: último run {found:%Y-%m-%d %HZ}", flush=True)
        if found != expected:
            return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tries", type=int, default=10)
    parser.add_argument("--interval", type=int, default=600, help="segundos entre verificações")
    parser.add_argument("--cycle", help="YYYY-MM-DDTHH:MM:SSZ; apenas utilização manual")
    args = parser.parse_args()
    if args.tries < 1 or args.interval < 0:
        parser.error("tries deve ser >=1 e interval >=0")
    expected = normalize_date(args.cycle) if args.cycle else expected_cycle(datetime.now(UTC))
    if expected.hour not in (0, 6, 12, 18):
        parser.error("ciclo inválido")
    print(f"MeteoFox: aguardar o ciclo IFS 0p1 {expected.isoformat()} (16 passos)", flush=True)

    from ecmwf.opendata import Client
    client = Client(source="ecmwf", model="ifs", resol="0p1")
    for attempt in range(1, args.tries + 1):
        print(f"Verificação {attempt}/{args.tries} em {datetime.now(UTC):%H:%M:%S} UTC", flush=True)
        try:
            ready = cycle_ready(client, expected)
        except Exception as exc:
            ready = False
            print(f"  ECMWF ainda indisponível ou erro de ligação: {exc}", flush=True)
        if ready:
            value = expected.strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"CONFIRMADO: 16 passos do ciclo {value}. Pode iniciar a produção.", flush=True)
            env_file = os.getenv("GITHUB_ENV")
            if env_file:
                with Path(env_file).open("a", encoding="utf-8") as handle:
                    handle.write(f"ECMWF_EXPECTED_RUN_UTC={value}\n")
            return 0
        if attempt < args.tries:
            time.sleep(args.interval)

    print("Novo ciclo incompleto. Manter o site publicado e não gerar mapas novos.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
