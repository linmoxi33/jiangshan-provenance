#!/usr/bin/env python3
"""Primary-source provenance ledger for the jiangshan-map citation corpus.

Reads data/sources/*.json offline. Separates "has any citation" from
"has a primary-source citation with a usable locus", which the upstream
coverage counter does not do.
"""
import argparse, json, os, sys, glob

KINDS = {"primary", "secondary", "dataset", "web"}
REC_TYPES = {"milestone", "event", "journey", "person"}


def die(msg):
    print("error: " + msg, file=sys.stderr)
    return 2


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{path}: {e}")


def usable_loc(loc):
    if not isinstance(loc, str):
        return False
    s = loc.strip()
    if len(s) < 2:
        return False
    bad = {"见原书", "原书", "同上", "待补", "tbd", "todo", "n/a", "?"}
    return s.lower() not in bad


def parse_key(key):
    parts = key.split(":")
    if len(parts) < 2 or parts[0] not in REC_TYPES:
        return None
    rtype = parts[0]
    dynasty = parts[1] if rtype in ("milestone", "event") else "*"
    return rtype, dynasty


def audit(src_dir):
    works_path = os.path.join(src_dir, "works.json")
    baseline_path = os.path.join(src_dir, "baseline.json")
    if not os.path.isdir(src_dir):
        raise ValueError(f"not a directory: {src_dir}")
    if not os.path.isfile(works_path):
        raise ValueError(f"missing works.json in {src_dir}")
    works = load(works_path)
    if not isinstance(works, dict):
        raise ValueError("works.json must be an object")
    baseline = load(baseline_path) if os.path.isfile(baseline_path) else {}
    if isinstance(baseline, dict):
        unsourced = set(baseline.get("unsourced", []))
    elif isinstance(baseline, list):
        unsourced = set(baseline)
    else:
        raise ValueError("baseline.json must be an object with 'unsourced' or a list")

    citations = {}
    for path in sorted(glob.glob(os.path.join(src_dir, "*.json"))):
        name = os.path.basename(path)
        if name in ("works.json", "baseline.json"):
            continue
        data = load(path)
        if not isinstance(data, dict):
            raise ValueError(f"{name}: top level must be an object")
        for key, refs in data.items():
            if key in citations:
                raise ValueError(f"duplicate citation key {key} in {name}")
            citations[key] = (name, refs)

    findings = []
    recs = {}
    for key in sorted(set(citations) | unsourced):
        parsed = parse_key(key)
        if parsed is None:
            findings.append({"code": "BAD_KEY", "severity": "error", "key": key,
                             "detail": "key is not <milestone|event|journey|person>:..."})
            continue
        rtype, dynasty = parsed
        recs.setdefault((rtype, dynasty), {"records": 0, "cited": 0, "primary": 0,
                                           "weak": 0, "uncited": 0})
        r = recs[(rtype, dynasty)]
        r["records"] += 1
        if key not in citations:
            r["uncited"] += 1
            continue
        fname, refs = citations[key]
        r["cited"] += 1
        if not isinstance(refs, list) or not refs:
            findings.append({"code": "EMPTY_CITATION", "severity": "error", "key": key,
                             "detail": f"{fname}: citation list is empty"})
            r["weak"] += 1
            continue
        has_primary = False
        for ref in refs:
            if not isinstance(ref, dict):
                findings.append({"code": "BAD_REF", "severity": "error", "key": key,
                                 "detail": f"{fname}: reference is not an object"})
                continue
            w = ref.get("w")
            if w not in works:
                findings.append({"code": "DANGLING_WORK", "severity": "error", "key": key,
                                 "detail": f"{fname}: unknown work id {w!r}"})
                continue
            kind = works[w].get("kind")
            if kind not in KINDS:
                findings.append({"code": "UNKNOWN_KIND", "severity": "warning", "key": key,
                                 "detail": f"{fname}: work {w!r} kind {kind!r}"})
                continue
            if kind == "primary":
                if usable_loc(ref.get("loc")):
                    has_primary = True
                else:
                    findings.append({"code": "PRIMARY_NO_LOCUS", "severity": "warning", "key": key,
                                     "detail": f"{fname}: primary work {w!r} has no usable locus"})
        if has_primary:
            r["primary"] += 1
        else:
            r["weak"] += 1
            findings.append({"code": "NO_PRIMARY_SOURCE", "severity": "warning", "key": key,
                             "detail": f"{fname}: cited, but no primary work with a usable locus"})

    by_dynasty = []
    for (rtype, dynasty), r in sorted(recs.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        covered = r["primary"] / r["records"] if r["records"] else 0.0
        by_dynasty.append({
            "type": rtype, "dynasty": dynasty,
            "records": r["records"], "cited": r["cited"], "uncited": r["uncited"],
            "primary_backed": r["primary"], "weak_only": r["weak"],
            "primary_rate": round(covered, 4),
            "debt": r["records"] - r["primary"],
        })
    by_dynasty.sort(key=lambda x: (-x["debt"], x["type"], x["dynasty"]))

    totals = {
        "records": sum(r["records"] for r in recs.values()),
        "cited": sum(r["cited"] for r in recs.values()),
        "uncited": sum(r["uncited"] for r in recs.values()),
        "primary_backed": sum(r["primary"] for r in recs.values()),
        "weak_only": sum(r["weak"] for r in recs.values()),
        "works": len(works),
        "primary_works": sum(1 for w in works.values() if w.get("kind") == "primary"),
        "citation_files": len({citations[k][0] for k in citations}),
    }
    totals["coverage_rate"] = round(totals["cited"] / totals["records"], 4) if totals["records"] else 0.0
    totals["primary_rate"] = round(totals["primary_backed"] / totals["records"], 4) if totals["records"] else 0.0
    totals["overstatement"] = round(totals["coverage_rate"] - totals["primary_rate"], 4)

    counts = {}
    for f in findings:
        counts[f["code"]] = counts.get(f["code"], 0) + 1
    report = {"src": src_dir, "totals": totals,
              "by_dynasty": by_dynasty, "finding_counts": counts,
              "findings": findings}
    return report


def has_severity(report, sev):
    order = {"info": 0, "warning": 1, "error": 2}
    want = order[sev]
    return any(order.get(f["severity"], 0) >= want for f in report["findings"])


def main(argv=None):
    p = argparse.ArgumentParser(prog="provenance.py")
    p.add_argument("src", nargs="?", help="path to jiangshan-map data/sources")
    p.add_argument("--json", action="store_true", help="machine-readable report")
    p.add_argument("--fail-on", choices=["error", "warning", "never"], default="warning")
    p.add_argument("--top", type=int, default=10, help="dynasties to print")
    a = p.parse_args(argv)
    if not a.src:
        return die("missing data/sources path")
    try:
        report = audit(a.src)
    except ValueError as e:
        return die(str(e))
    t = report["totals"]
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"records={t['records']} cited={t['cited']} primary={t['primary_backed']} "
              f"coverage={t['coverage_rate']:.2%} primary_rate={t['primary_rate']:.2%}")
        print(f"overstatement={t['overstatement']:.2%} weak_only={t['weak_only']} "
              f"primary_works={t['primary_works']}/{t['works']}")
        print("debt ranking:")
        for row in report["by_dynasty"][:a.top]:
            print(f"  {row['type']:<9} {row['dynasty']:<8} debt={row['debt']:<4} "
                  f"primary={row['primary_backed']}/{row['records']}")
        if report["finding_counts"]:
            print("findings: " + ", ".join(f"{k}={v}" for k, v in sorted(report["finding_counts"].items())))
    if a.fail_on == "never":
        return 0
    return 1 if has_severity(report, a.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
