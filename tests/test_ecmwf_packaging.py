"""Tests ECMWF workflow's separated map and site packaging without network/deployment."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/meteofox_ecmwf.yml").read_text())
RUN = "2026-11-19T06:00:00Z"
FOLDER = "MeteoFox_48h_20261119_06UTC"


def python_in(name):
    steps = [s for job in WORKFLOW["jobs"].values() for s in job["steps"]]
    step = next(s for s in steps if s.get("name") == name)
    match = re.search(r"(?:python3|\.venv/bin/python) - <<'PY'\n(.*?)\n\s+PY(?:\n|$)", step["run"], re.S)
    if not match:
        raise AssertionError(f"Inline Python is missing from {name}")
    return textwrap.dedent(match.group(1))


class PackagingTests(unittest.TestCase):
    def test_stage_structure(self):
        jobs = WORKFLOW["jobs"]
        self.assertEqual(jobs["preparar"]["needs"], "gerar")
        self.assertEqual(jobs["publicar"]["needs"], "preparar")
        self.assertNotIn("deploy-pages", " ".join(str(x) for x in jobs["gerar"]["steps"]))
        self.assertNotIn("deploy-pages", " ".join(str(x) for x in jobs["preparar"]["steps"]))
        self.assertTrue(any(x.get("uses","").startswith("actions/cache@") for x in jobs["gerar"]["steps"]))
        self.assertTrue(any(x.get("uses","").startswith("actions/download-artifact@") for x in jobs["preparar"]["steps"]))

    def sandbox(self):
        tmp = tempfile.TemporaryDirectory()
        work = Path(tmp.name)
        source = work / FOLDER
        source.mkdir()
        data = work / "dados_meteofox_48h"
        data.mkdir()
        (data / "ultimo_run.json").write_text(json.dumps({"run": RUN}), encoding="utf-8")
        for step in range(3, 49, 3):
            for kind in ("chuva", "rajadas"):
                (source / f"{kind}_{step:03d}.png").write_bytes(b"PNG" * 5000)
        (source / "MeteoFox_animacao_48h.html").write_bytes(b"<html>" + b"."*2000)
        for name in ("index.html", "mapa.html", "meteofox_satelite.js",
                     "meteofox_meteograma.js", "meteofox_meteograma.css",
                     "meteofox_keyboard.js", "laboratorio.html"):
            shutil.copy2(ROOT / name, work / name)
        lab = work / "produtos_experimentais"
        lab.mkdir()
        shutil.copy2(ROOT / "produtos_experimentais/previsao_ecmwf.json",
                     lab / "previsao_ecmwf.json")
        return tmp, work

    def invoke(self, script, work, should_pass):
        result = subprocess.run(["python3", "-c", script], cwd=work,
                                capture_output=True, text=True)
        if should_pass:
            self.assertEqual(result.returncode,0,result.stderr)
        else:
            self.assertNotEqual(result.returncode,0,result.stdout)

    def test_separation_and_validation(self):
        tmp, work = self.sandbox()
        with tmp:
            package = python_in("Guardar 32 cartas e animação como artefacto independente")
            prepare = python_in("Montar o site com cartas validadas e interface atual")
            self.invoke(package,work,True)
            self.assertEqual(len(list((work/"mapas_ecmwf").glob("*.png"))),32)
            self.invoke(prepare,work,True)
            output=work/"public"
            self.assertEqual(len(list(output.glob("*.png"))),32)
            self.assertTrue((output/"laboratorio.html").is_file())
            self.assertTrue((output/"mapa.html").is_file())
            self.assertTrue((output/"MeteoFox_animacao_48h.html").is_file())
            self.assertEqual((work/"mapas_ecmwf/cycle.txt").read_text().strip(),RUN)

    def test_incomplete_package_never_passes(self):
        tmp, work = self.sandbox()
        with tmp:
            package = python_in("Guardar 32 cartas e animação como artefacto independente")
            prepare = python_in("Montar o site com cartas validadas e interface atual")
            (work/FOLDER/"chuva_003.png").unlink()
            self.invoke(package,work,False)
            (work/"mapas_ecmwf").mkdir(exist_ok=True)
            (work/"mapas_ecmwf/cycle.txt").write_text(RUN)
            self.invoke(prepare,work,False)

if __name__=="__main__":
    unittest.main()
