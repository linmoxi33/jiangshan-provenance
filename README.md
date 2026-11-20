# jiangshan-provenance — primary-source debt ledger for the 江山时序 atlas

**Why now:** the atlas has 1,496 historical records but its coverage counter treats
"linked to Wikipedia" and "cited to 《资治通鉴》卷191" as the same thing. This tool
splits those two numbers and ranks where a real primary source buys the most trust.

Upstream: https://github.com/DeanChensj/jiangshan-map

## What the upstream is, and what it does not do

[`DeanChensj/jiangshan-map`](https://github.com/DeanChensj/jiangshan-map) is an interactive
historical atlas of China (403 BCE – present, 8.4k stars). Its citations live in
`data/sources/*.json`, keyed like `event:tang:626`, with a `works.json` registry that tags
each book `primary` / `secondary` / `dataset` / `web`.

The upstream CI auditor (`scripts/audit_sources.js`) verifies key validity, known work ids,
the baseline ratchet, and canonical formatting. Its coverage report counts **any** reference
as sourced; the maintainer's pinned issue reports one global number
([#309](https://github.com/DeanChensj/jiangshan-map/issues/309): 1,457 records, 285 cited).
`loc` is optional in the upstream schema (`{ w, loc?, note?, url? }`), so a record can claim a
primary work while giving no chapter at all, and nothing reports it. No upstream output
separates primary-source-backed records from records backed only by a web page or a modern
retelling.

## What this tool does

Offline, zero-dependency Python CLI over an existing `data/sources/` checkout:

- reconstructs the record universe from `baseline.json` + citation files;
- computes **coverage** (any citation) and **primary coverage** (a `primary` work with a
  usable `loc`), plus the gap between them;
- emits a per-dynasty/per-type **debt ranking** (records minus primary-backed);
- flags `DANGLING_WORK`, `PRIMARY_NO_LOCUS`, `NO_PRIMARY_SOURCE`, `UNKNOWN_KIND`,
  `EMPTY_CITATION`, `BAD_REF`, `BAD_KEY`;
- exit codes: `0` clean, `1` findings at/above `--fail-on`, `2` usage/input error.

It does **not** verify that a chapter number is historically correct, fetch any URL, or
replace human proofreading. It measures provenance *shape*, not truth.

## Install / usage

Requires Python 3.8+, no packages.

```bash
# offline smoke test with the bundled fixture (no network, no packages)
python3 bin/provenance.py examples/in --json | diff - examples/out/expected.json && echo OK

# against a real atlas checkout (optional)
git clone --depth=1 --filter=blob:none --sparse git@github.com:DeanChensj/jiangshan-map.git jsmap
cd jsmap && git sparse-checkout set data/sources && cd ..
python3 bin/provenance.py jsmap/data/sources
python3 bin/provenance.py jsmap/data/sources --json > report.json
```

Exit-code table:

| code | meaning |
| --- | --- |
| 0 | no findings at or above `--fail-on` |
| 1 | findings present (default threshold: warning) |
| 2 | bad path, missing/invalid `works.json`, duplicate key, malformed JSON |

`--fail-on error|warning|never` and `--top N` are supported.

### Real run on upstream `main` (2026-11-20, commit from sparse clone)

```
records=1496 cited=383 primary=372 coverage=25.60% primary_rate=24.87%
overstatement=0.73% weak_only=11 primary_works=40/43
debt ranking:
  person    *        debt=124  primary=20/144
  event     tang     debt=65   primary=41/106
  event     qing     debt=64   primary=0/64
  event     nansong  debt=59   primary=0/59
  event     beisong  debt=57   primary=0/57
```

11 cited records have only a secondary/web work: that is the part the upstream coverage
number does not show. Numbers above come from the command in the previous section, not
from an estimate.

## Limits

- The universe is `baseline.json ∪ citation keys`; records deleted upstream can leave stale
  baseline keys (hence 1,496 vs the issue's 1,457). This tool cannot detect orphans without
  executing the atlas JS.
- `loc` usability is a shape check (non-empty, not "见原书"/"TBD"/"?"); it cannot tell whether
  the chapter is the right one.
- No network access, by design: core logic, tests and examples are offline.

## 本轮创新

First provenance ledger that separates "cited" from "cited to a primary source with a locus"
for a real 1,496-record historical atlas, and ranks the 1,113-record debt by dynasty/type.
Unlike `scripts/audit_sources.js` (key/format/ratchet) it measures kind-weighted depth and
found 11 records whose only support is secondary or web, plus 40/43 works are primary while
several dynasties (qing, nansong, beisong) have **zero** primary-backed events.

## 与同类项目的差异

`gh search repos "historical atlas provenance"` returned no mature competitor; the only
code hit for `data/sources/works.json` is the upstream repo itself. The upstream auditor is
the closest tool and is complementary: it gates structural validity, this gates source depth.
