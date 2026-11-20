import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "provenance.py")

WORKS = {
    "zztj": {"zh": "资治通鉴", "kind": "primary"},
    "wiki": {"zh": "维基百科", "kind": "web"},
    "modern": {"zh": "今人著作", "kind": "secondary"},
}


def make(tmp, works=None, baseline=None, files=None):
    src = os.path.join(tmp, "sources")
    os.makedirs(src, exist_ok=True)
    json.dump(WORKS if works is None else works, open(os.path.join(src, "works.json"), "w"))
    json.dump({"unsourced": baseline or []}, open(os.path.join(src, "baseline.json"), "w"))
    for name, data in (files or {}).items():
        json.dump(data, open(os.path.join(src, name), "w"), ensure_ascii=False)
    return src


def run(src, *args):
    p = subprocess.run([sys.executable, CLI, src, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class TestLedger(unittest.TestCase):
    def test_totals(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, baseline=["event:tang:700"],
                       files={"tang.json": {"milestone:tang:1": [{"w": "zztj", "loc": "卷1"}],
                                            "milestone:tang:2": [{"w": "modern"}]}})
            rc, out, _ = run(src, "--json")
            d = json.loads(out)
            self.assertEqual(rc, 1)
            self.assertEqual(d["totals"]["records"], 3)
            self.assertEqual(d["totals"]["cited"], 2)

    def test_primary_rate(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, baseline=[], files={"tang.json": {
                "milestone:tang:1": [{"w": "zztj", "loc": "卷1"}],
                "milestone:tang:2": [{"w": "modern"}]}})
            d = json.loads(run(src, "--json")[1])
            self.assertEqual(d["totals"]["primary_rate"], 0.5)

    def test_coverage_rate(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, baseline=["event:tang:1", "event:tang:2"], files={"tang.json": {
                "event:tang:1": [{"w": "zztj", "loc": "卷1"}]}})
            d = json.loads(run(src, "--json")[1])
            self.assertEqual(d["totals"]["coverage_rate"], 0.5)

    def test_weak_only(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "modern", "loc": "p1"}]}})
            d = json.loads(run(src, "--json")[1])
            self.assertEqual(d["totals"]["weak_only"], 1)

    def test_no_primary_finding(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "modern"}]}})
            d = json.loads(run(src, "--json")[1])
            codes = [f["code"] for f in d["findings"]]
            self.assertIn("NO_PRIMARY_SOURCE", codes)

    def test_dangling_work_is_error(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "ghost", "loc": "卷1"}]}})
            rc, out, _ = run(src, "--json")
            self.assertEqual(rc, 1)
            self.assertIn("DANGLING_WORK", [f["code"] for f in json.loads(out)["findings"]])

    def test_primary_no_locus(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "zztj", "loc": "见原书"}]}})
            d = json.loads(run(src, "--json")[1])
            self.assertIn("PRIMARY_NO_LOCUS", [f["code"] for f in d["findings"]])
            self.assertEqual(d["totals"]["primary_backed"], 0)

    def test_bad_key(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"tang:692": [{"w": "zztj", "loc": "卷1"}]}})
            d = json.loads(run(src, "--json")[1])
            self.assertIn("BAD_KEY", [f["code"] for f in d["findings"]])

    def test_missing_works_exit_2(self):
        with tempfile.TemporaryDirectory() as t:
            rc, _, err = run(os.path.join(t, "nope"))
            self.assertEqual(rc, 2)
            self.assertIn("not a directory", err)

    def test_fail_on_never(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "ghost"}]}})
            rc, _, _ = run(src, "--fail-on", "never")
            self.assertEqual(rc, 0)

    def test_duplicate_key_exit_2(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"a.json": {"milestone:tang:1": [{"w": "zztj", "loc": "x"}]},
                                 "b.json": {"milestone:tang:1": [{"w": "zztj", "loc": "x"}]}})
            rc, _, err = run(src)
            self.assertEqual(rc, 2)
            self.assertIn("duplicate citation key", err)

    def test_clean_corpus_exit_0(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "zztj", "loc": "卷1"}]}})
            rc, out, _ = run(src, "--json")
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)["findings"], [])

    def test_debt_ranking_sorted(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, baseline=["event:qing:1900"] * 1 + ["event:qing:1901"] * 1,
                       files={"tang.json": {"milestone:tang:1": [{"w": "zztj", "loc": "卷1"}]}})
            d = json.loads(run(src, "--json")[1])
            debts = [r["debt"] for r in d["by_dynasty"]]
            self.assertEqual(debts, sorted(debts, reverse=True))

    def test_json_schema_keys(self):
        with tempfile.TemporaryDirectory() as t:
            src = make(t, files={"tang.json": {"milestone:tang:1": [{"w": "zztj", "loc": "卷1"}]}})
            d = json.loads(run(src, "--json")[1])
            for k in ("totals", "by_dynasty", "finding_counts", "findings"):
                self.assertIn(k, d)
            for k in ("records", "cited", "primary_backed", "weak_only", "overstatement"):
                self.assertIn(k, d["totals"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
