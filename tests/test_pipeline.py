import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def run_py(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_sample_sites(self, path):
        rows = [
            {"domain": "www.a.com", "category": "1", "lowest_price": 40, "DR": 35, "gsc": 0, "ahrefs_traf": 12000, "lang": "GB", "country": "GB", "verified": 1, "dofollow": 1},
            {"domain": "https://a.com/blog", "category": "1", "lowest_price": 40, "DR": 35, "gsc": 0, "ahrefs_traf": 12000, "lang": "GB", "country": "GB", "verified": 1, "dofollow": 1},  # dup in same cat
            {"domain": "a.com", "category": "2", "lowest_price": 40, "DR": 35, "gsc": 0, "ahrefs_traf": 12000, "lang": "GB", "country": "GB", "verified": 1, "dofollow": 1},  # dup across cats
            {"domain": "b.com", "category": "1", "lowest_price": 120, "DR": 0, "gsc": 0, "ahrefs_traf": None, "lang": "US", "country": "US", "verified": 0, "dofollow": 1},
            {"domain": "c.com", "category": "2", "lowest_price": 80, "DR": 55, "gsc": 5000, "ahrefs_traf": 8000, "lang": "PL", "country": "PL", "verified": 0, "dofollow": 0},
        ]
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_analyze_without_map_and_dedup(self):
        sites = os.path.join(self.d, "sites.jsonl")
        out = os.path.join(self.d, "p.json")
        self._write_sample_sites(sites)

        r = run_py("analyze.py", sites, "--platform", "Demo", "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            p = json.load(f)
        # 3 unique domains globally: a.com, b.com, c.com
        self.assertEqual(p["collection"]["sample_domains"], 3)
        self.assertEqual(p["overall"]["price"]["n"], 3)
        # a.com (GB) + b.com (US) = 2/3 English = 66.7%
        self.assertEqual(p["overall"]["language"]["english_share"], 66.7)
        # traffic=0 treated as missing: a.com (12000) & c.com (8000), b.com missing => 2/3
        self.assertEqual(p["overall"]["traffic"]["n"], 2)
        self.assertAlmostEqual(p["overall"]["traffic"]["coverage"], 0.667, places=3)

    def test_counts_by_id_compare_dashboard_xlsx(self):
        sites = os.path.join(self.d, "sites.jsonl")
        counts = os.path.join(self.d, "counts.json")
        meta = os.path.join(self.d, "meta.json")
        p1 = os.path.join(self.d, "p1.json")
        p2 = os.path.join(self.d, "p2.json")
        merged = os.path.join(self.d, "merged.json")
        html = os.path.join(self.d, "dash.html")
        xlsx = os.path.join(self.d, "audit.xlsx")

        self._write_sample_sites(sites)
        with open(counts, "w", encoding="utf-8") as f:
            json.dump({
                "_total": 5000,
                "1": {"id": "1", "name": "Tech & <IT>", "total": 3000, "english": 1500, "fmt": {"link_insertion": 900}},
                "2": {"id": "2", "name": "Finance", "total": 2000, "english": 800},
            }, f)
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"collection": {"caveats": ["测试口径说明"]}}, f)

        r = run_py("analyze.py", sites, "--platform", "Plat</title>A", "--counts", counts, "--meta", meta, "-o", p1)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(p1, encoding="utf-8") as f:
            prof1 = json.load(f)
        self.assertEqual(prof1["platform"]["supply_total"], 5000)
        names = {s["name"] for s in prof1["segments"]}
        self.assertEqual(names, {"Tech & <IT>", "Finance"})

        r = run_py("analyze.py", sites, "--platform", "Plat B", "-o", p2)
        self.assertEqual(r.returncode, 0, r.stderr)

        r = run_py("make_compare.py", p1, p2, "-o", merged, "--note", "B 为抽样口径")
        self.assertEqual(r.returncode, 0, r.stderr)

        r = run_py("dashboard.py", merged, "-o", html, "--strict")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(html, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("{{DATA_JSON}}", content)
        self.assertIn("<title>Plat&lt;/title&gt;A 外链市场调查</title>", content)
        self.assertNotIn("Plat</title>A", content)

        r = run_py("export_xlsx.py", merged, "-o", xlsx)
        self.assertEqual(r.returncode, 0, r.stderr)
        with zipfile.ZipFile(xlsx) as z:
            self.assertEqual(len([n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]), 6)
            for name in z.namelist():
                ET.fromstring(z.read(name))

    def test_zero_dr_not_warned_as_missing(self):
        p = {
            "platform": {"name": "ZeroDR", "supply_total": 10},
            "collection": {"method": "sampled", "caveats": ["ok"]},
            "overall": {"price": {"med": 10}, "dr": {"med": 0}},
            "segments": [{"name": "Cat", "total": 10, "price": {"med": 10}, "dr": {"med": 0}}],
        }
        pp = os.path.join(self.d, "z.json")
        out = os.path.join(self.d, "z.html")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(p, f)
        r = run_py("dashboard.py", pp, "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("缺 `dr.med`", r.stderr)


if __name__ == "__main__":
    unittest.main()
