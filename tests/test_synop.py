import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

# Load only pure decoder functions, without starting the HTTP server.
tree = ast.parse(Path("server.py").read_text())
names = {"precip_groups", "accumulate"}
scope = {"re": re, "timedelta": timedelta}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), "server.py", "exec"), scope)
decode = scope["precip_groups"]
accumulate = scope["accumulate"]

class SynopTests(unittest.TestCase):
    def test_section_one(self):
        self.assertEqual(decode("AAXX 24121 08540 11470 32905 60051=")[0]["mm"], 5)
    def test_section_three(self):
        self.assertEqual(decode("AAXX 24121 08540 21470 32905 333 60051=")[0]["hours"], 6)
    def test_trace(self):
        self.assertTrue(decode("AAXX 24121 08540 11470 32905 69901=")[0]["trace"])
    def test_contiguous(self):
        end = datetime(2026,11,24,12,tzinfo=timezone.utc)
        p = {"hours":1,"mm":2,"trace":False,"method":"reported"}
        records = [(end-timedelta(hours=i),p) for i in range(6)]
        self.assertEqual(accumulate(records)["6"]["mm"],12)
        self.assertNotIn("6",accumulate(records[:-1]))
    def test_direct_priority(self):
        end = datetime(2026,11,24,12,tzinfo=timezone.utc)
        p = {"hours":6,"mm":0,"trace":False,"method":"reported"}
        self.assertEqual(accumulate([(end,p)])["6"]["mm"],0)
