"""Testes sem rede para a auditoria independente de qualidade."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from meteofox_quality import audit, STEPS, METEOGRAM_STEPS, LEVELS

RUN = "2026-11-20T06:00:00Z"
BASE = datetime(2026, 11, 20, 6, tzinfo=timezone.utc)
NOW = BASE + timedelta(hours=10)


def at(hours):
    return (BASE + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def sample():
    maps = {
        "cycle_utc": RUN,
        "images": {f"{kind}_{step:03d}.png": "test" for kind in ("chuva", "rajadas") for step in STEPS},
    }
    vis = {
        "run_utc": RUN, "projection": "opencharts_south_west_europe",
        "frames": [{"file": f"VIS_{s:03d}.png", "step_h": s, "run_utc": RUN,
                    "valid_utc": at(s)} for s in STEPS],
    }
    surface = [{"step_h": s, "valid_utc": at(s), "temp_c": 20,
                "dewpoint_c": 12, "pressure_hpa": 1020, "cloud_percent": 50,
                "rain_3h_mm": 0.5, "wind_kt": 10, "gust_kt": 20,
                "wind_dir_deg": 180} for s in METEOGRAM_STEPS]
    profile = [{"hpa": h, "temp_c": 10 - (1000-h)/15, "dewpoint_c": 4 - (1000-h)/15,
                "rh_percent": 80, "wind_kt": 35, "wind_dir_deg": 270} for h in LEVELS]
    lab = {
        "run_utc": RUN, "meteogram_lisboa": surface,
        "soundings": [{"step_h": s, "valid_utc": at(s),
                       "cities": {city: copy.deepcopy(profile) for city in ("Lisboa", "Porto", "Beja")}}
                      for s in STEPS],
    }
    return maps, vis, lab


class QualityTests(unittest.TestCase):
    def test_complete_run_is_valid(self):
        self.assertEqual(audit(*sample(), now=NOW)["status"], "OK")

    def test_missing_ecmwf_frame_is_error(self):
        items = sample()
        del items[0]["images"]["chuva_027.png"]
        self.assertEqual(audit(*items, now=NOW)["status"], "ERRO")

    def test_mixed_vis_validity_is_error(self):
        items = sample()
        items[1]["frames"][4]["valid_utc"] = at(120)
        self.assertTrue(any("validade" in e for e in audit(*items, now=NOW)["errors"]))

    def test_mixed_runs_are_warning_only(self):
        items = sample()
        items[1]["run_utc"] = "2026-11-20T00:00:00Z"
        for frame in items[1]["frames"]:
            frame["run_utc"] = items[1]["run_utc"]
            frame["valid_utc"] = (BASE + timedelta(hours=frame["step_h"] - 6)).isoformat().replace("+00:00", "Z")
        result = audit(*items, now=NOW)
        self.assertEqual(result["status"], "AVISO")

    def test_implausible_precipitation_is_error(self):
        items = sample()
        items[2]["meteogram_lisboa"][0]["rain_3h_mm"] = -10
        self.assertEqual(audit(*items, now=NOW)["status"], "ERRO")

    def test_humidity_over_100_not_instant_failure(self):
        # ECMWF pode apresentar ligeira supersaturação nos perfis.
        items = sample()
        items[2]["soundings"][0]["cities"]["Porto"][0]["rh_percent"] = 109
        self.assertEqual(audit(*items, now=NOW)["status"], "OK")

    def test_bad_pressure_levels_are_error(self):
        items = sample()
        items[2]["soundings"][0]["cities"]["Porto"][0]["hpa"] = 990
        self.assertEqual(audit(*items, now=NOW)["status"], "ERRO")

    def test_stale_run_triggers_warning(self):
        self.assertEqual(audit(*sample(), now=NOW + timedelta(hours=20))["status"], "AVISO")


if __name__ == "__main__":
    unittest.main()
