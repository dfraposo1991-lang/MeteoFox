"""Testes do módulo de previsão: sem dependências meteorológicas ou rede."""
import math
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gerar_produtos_experimentais import (
    LOCATIONS, LEVELS, METEOGRAM_STEPS, SOUNDING_STEPS,
    build_surface_row, build_sounding, dewpoint_from_rh,
    parse_cycle, precipitation_interval, speed_direction,
)

CYCLE = datetime(2026,11,19,0,tzinfo=timezone.utc)


class ForecastTests(unittest.TestCase):
    def test_expected_scope(self):
        self.assertEqual(set(LOCATIONS), {"Lisboa","Porto","Beja"})
        self.assertEqual(len(METEOGRAM_STEPS),40)
        self.assertEqual(METEOGRAM_STEPS[-1],120)
        self.assertEqual(len(SOUNDING_STEPS),9)
        self.assertEqual(SOUNDING_STEPS[-1],48)
        self.assertIn(500,LEVELS)

    def test_cycle_guard(self):
        self.assertEqual(parse_cycle("2026-11-19T06:00:00Z").hour,6)
        for stamp in ("2026-11-19T09:00:00Z","2026-11-19T06:30:00Z"):
            with self.assertRaises(ValueError):parse_cycle(stamp)

    def test_precip_accumulation(self):
        self.assertEqual(precipitation_interval(1.3,None),1.3)
        self.assertEqual(precipitation_interval(5.1,1.3),3.8)
        self.assertEqual(precipitation_interval(2.0,3.0),0.0)

    def test_wind_conversion(self):
        speed,direction=speed_direction(0,-10)
        self.assertAlmostEqual(speed,19.4,places=1)
        self.assertEqual(direction,0.0)

    def test_dewpoint(self):
        self.assertAlmostEqual(dewpoint_from_rh(293.15,100),20,places=1)
        self.assertLess(dewpoint_from_rh(293.15,50),20)

    def test_surface_row(self):
        raw={"2t":(293.15,"K"),"2d":(288.15,"K"),"msl":(101325,"Pa"),
             "tcc":(0.7,"(0 - 1)"),"tp":(0.003,"m"),
             "10u":(3,"m s**-1"),"10v":(4,"m s**-1"),
             "10fg":(9,"m s**-1")}
        fields={name:({"Lisboa":value},unit) for name,(value,unit) in raw.items()}
        row,acc=build_surface_row(fields,6,CYCLE,1)
        self.assertEqual(acc,3.0)
        self.assertEqual(row["temp_c"],20.0)
        self.assertEqual(row["cloud_percent"],70.0)
        self.assertEqual(row["rain_3h_mm"],2.0)
        self.assertEqual(row["wind_kt"],9.7)
        self.assertEqual(row["step_h"],6)

    def test_sounding_schema(self):
        fields={}
        for level in LEVELS:
            for param,value,unit in (
                ("t",288.15,"K"),("r",60,"%"),("u",5,"m s**-1"),("v",1,"m s**-1"),
            ):
                fields[f"{param}@{level}"]=({name:value for name in LOCATIONS},unit)
        result=build_sounding(fields,12,CYCLE)
        self.assertEqual(len(result["cities"]),3)
        self.assertEqual(len(result["cities"]["Beja"]),10)
        self.assertEqual(result["valid_utc"],"2026-11-19T12:00:00Z")
        self.assertLess(result["cities"]["Porto"][0]["dewpoint_c"],15)


if __name__=="__main__":
    unittest.main()
