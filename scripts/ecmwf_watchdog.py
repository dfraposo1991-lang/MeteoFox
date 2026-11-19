#!/usr/bin/env python3
"""Vigia ECMWF MeteoFox. Deteta ciclos sem workflow iniciado e recupera uma vez.

Sem pacotes externos: usa apenas GitHub REST, GITHUB_TOKEN do próprio workflow.
Cada janela cron tem uma correspondência fixa para o ciclo ECMWF (UTC).
A verificação deve acontecer depois de 70+ minutos de tolerância.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import sys
import urllib.error
import urllib.request

UTC = timezone.utc
# (hora, minuto da verificação ECMWF original, ciclo de referência)
WINDOWS = ((2, 40, 18), (9, 45, 0), (14, 40, 6), (21, 45, 12))
GRACE = timedelta(minutes=70)
MAX_AGE = timedelta(hours=3)


def latest_window(now: datetime):
    """Devolve (hora nominal, ciclo) da janela mais recente em UTC."""
    now = now.astimezone(UTC)
    windows = []
    for offset in (0, -1):
        date = now.date() + timedelta(days=offset)
        for hour, minute, cycle_hour in WINDOWS:
            nominal = datetime(date.year, date.month, date.day, hour, minute, tzinfo=UTC)
            if nominal > now:
                continue
            cycle_date = date - timedelta(days=1) if (hour == 2) else date
            cycle = datetime(cycle_date.year, cycle_date.month, cycle_date.day,
                             cycle_hour, tzinfo=UTC)
            windows.append((nominal, cycle))
    return max(windows, key=lambda pair: pair[0])


def evaluate(now: datetime, runs: list[dict]):
    """Decide sem executar efeitos: fora da janela, coberto ou recuperar."""
    nominal, cycle = latest_window(now)
    elapsed = now - nominal
    cycle_text = cycle.strftime("%Y-%m-%dT%H:%M:%SZ")
    if elapsed < GRACE or elapsed > MAX_AGE:
        return ("outside", nominal, cycle_text, None)
    # Uma execução agendada ou manual já iniciada desde esta janela basta.
    # Nunca lançar uma segunda enquanto a primeira está em curso/na fila,
    # mesmo que demore a publicar.
    for run in runs:
        if run.get("event") not in ("schedule", "workflow_dispatch"):
            continue
        if run.get("head_branch") != "main":
            continue
        created_raw = run.get("created_at") or ""
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if nominal - timedelta(minutes=2) <= created <= now:
            return ("covered", nominal, cycle_text, run)
    return ("recover", nominal, cycle_text, None)


def request_json(url: str, token: str, method="GET", payload=None):
    headers = {"Accept": "application/vnd.github+json",
               "Authorization": f"Bearer {token}",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "MeteoFox-ECMWF-Watchdog"}
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as reply:
        return reply.status, reply.read()


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    now = datetime.now(UTC)
    base = f"https://api.github.com/repos/{repo}"
    status, raw = request_json(
        base + "/actions/workflows/meteofox_ecmwf.yml/runs?per_page=100", token)
    assert status == 200, "GitHub API não devolveu 200"
    runs = json.loads(raw)["workflow_runs"]
    decision, nominal, cycle, matched = evaluate(now, runs)
    print(f"Janela ECMWF {nominal.isoformat()} | ciclo {cycle}", flush=True)
    print(f"Vigia: {decision}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### MeteoFox — controlo do agendamento ECMWF\n")
            f.write(f"- Janela nominal: `{nominal:%Y-%m-%d %H:%M} UTC`\n")
            f.write(f"- Ciclo esperado: `{cycle}`\n")
            f.write(f"- Decisão: **{decision}**\n")
    if decision == "covered":
        delay = (datetime.fromisoformat(matched["created_at"].replace("Z", "+00:00"))
                 - nominal).total_seconds() / 60
        print(f"Execução #{matched['id']} ({matched['status']}) | desvio {delay:+.1f} minutos")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"- Execução existente: [#{matched['id']}]({matched['html_url']})"
                        f" | atraso {delay:+.1f} minutos | estado `{matched['status']}`\n")
    elif decision == "recover":
        # GitHub devolve HTTP 204 quando o despacho foi aceite.
        status, _ = request_json(
            base + "/actions/workflows/meteofox_ecmwf.yml/dispatches",
            token, method="POST",
            payload={"ref": "main", "inputs": {"cycle": cycle}})
        if status != 204:
            raise RuntimeError(f"Despacho de recuperação rejeitado (HTTP {status})")
        print(f"RECUPERAÇÃO DISPARADA: ciclo {cycle}", flush=True)
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"- **Recuperação acionada** para o ciclo `{cycle}`\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
