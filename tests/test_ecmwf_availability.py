"""Testes offline do pré-controlo de disponibilidade ECMWF (sem chamadas de rede)."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verificar_ecmwf_48h import STEPS, PARAMETERS, cycle_ready, expected_cycle, normalize_date

UTC = timezone.utc


class ECMWFPreflightTests(unittest.TestCase):
    def test_scheduler_windows(self):
        examples = [
            ("2026-11-19T02:39:00Z", "2026-11-18T12:00:00Z"),
            ("2026-11-19T02:40:00Z", "2026-11-18T18:00:00Z"),
            ("2026-11-19T09:45:00Z", "2026-11-19T00:00:00Z"),
            ("2026-11-19T14:40:00Z", "2026-11-19T06:00:00Z"),
            ("2026-11-19T21:45:00Z", "2026-11-19T12:00:00Z"),
            ("2026-11-20T00:05:00Z", "2026-11-19T12:00:00Z"),
        ]
        for now, expected in examples:
            with self.subTest(now=now):
                self.assertEqual(expected_cycle(normalize_date_for_test(now)),
                                 normalize_date_for_test(expected))

    def test_complete_run_requires_all_sixteen_steps(self):
        expected = datetime(2026, 11, 19, 0, tzinfo=UTC)
        class FakeClient:
            def __init__(self, stale=None):
                self.calls = []
                self.stale = stale
            def latest(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["step"] == self.stale:
                    return expected - timedelta(hours=6)
                return expected
        client = FakeClient()
        self.assertTrue(cycle_ready(client, expected))
        self.assertEqual([x["step"] for x in client.calls], list(STEPS))
        self.assertTrue(all(x["param"] == list(PARAMETERS) and x["levtype"] == "sfc"
                            and x["stream"] == "oper" for x in client.calls))
        self.assertFalse(cycle_ready(FakeClient(stale=27), expected))

    def test_normalize_date(self):
        self.assertEqual(normalize_date("2026-11-19T06:00:00Z"),
                         datetime(2026, 11, 19, 6, tzinfo=UTC))
        self.assertEqual(normalize_date(datetime(2026, 11, 19, 12)),
                         datetime(2026, 11, 19, 12, tzinfo=UTC))

    def test_production_workflow_keeps_satellite_and_map(self):
        yaml = (Path(__file__).resolve().parents[1] /
                ".github/workflows/meteofox_ecmwf.yml").read_text()
        for schedule in ("40 2 * * *", "45 9 * * *", "40 14 * * *", "45 21 * * *"):
            self.assertIn(schedule, yaml)
        self.assertIn("verificar_ecmwf_48h.py --tries 10 --interval 600", yaml)
        self.assertIn('"mapa.html", "meteofox_satelite.js"', yaml)
        download = (Path(__file__).resolve().parents[1] /
                    "descarregar_meteofox_48h.py").read_text()
        self.assertIn('ECMWF_EXPECTED_RUN_UTC', download)
        self.assertIn("Ciclo inesperado:", download)


def normalize_date_for_test(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    unittest.main()
