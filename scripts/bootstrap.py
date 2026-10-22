#!/usr/bin/env python3
"""既存の評価スコアをブートストラップして、結果のブレ幅（信頼区間）を出す。

信頼区間の幅が「検出したい差」より広ければ、評価セットの件数が足りていない。

入力: CSV または JSONL。各行に score（0/1 または数値）、任意で slice 列。
  score,slice
  1,standard
  0,edge
  ...

使い方:
  python bootstrap.py results.csv
  python bootstrap.py results.jsonl --score-key passed --slice-key slice
  python bootstrap.py results.csv --delta 0.03     # 検出したい差と比較して判定
  python bootstrap.py a.csv --compare b.csv        # 2つのスコア列の差の信頼区間
"""
import argparse
import csv
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def load(path: str, score_key: str, slice_key: str):
    p = Path(path)
    rows = []
    if p.suffix == ".jsonl":
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    elif p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("results", [])
    else:
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        v = r.get(score_key)
        if v is None:
            continue
        if isinstance(v, bool):
            v = 1.0 if v else 0.0
        elif isinstance(v, str):
            vl = v.strip().lower()
            v = 1.0 if vl in ("true", "pass", "passed", "1", "yes") else 0.0 if vl in ("false", "fail", "failed", "0", "no") else float(vl)
        out.append((float(v), r.get(slice_key, "all") if slice_key else "all"))
    return out


def bootstrap_ci(values, n_iter=2000, ci=0.95, seed=0):
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_iter):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((1 - ci) / 2 * n_iter)]
    hi = means[int((1 + ci) / 2 * n_iter) - 1]
    return sum(values) / n, lo, hi, statistics.pstdev(means)


def report(name, values, delta, n_iter, ci):
    mean, lo, hi, sd = bootstrap_ci(values, n_iter, ci)
    width = hi - lo
    verdict = ""
    if delta is not None:
        verdict = "  ✅ 十分" if width <= delta else f"  ⚠️ 不足（区間幅 {width:.1%} > 検出したい差 {delta:.1%}）"
    print(f"{name:<24} n={len(values):>6,}  mean={mean:.3f}  {int(ci*100)}%CI=[{lo:.3f}, {hi:.3f}]  幅={width:.3f}{verdict}")
    return {"name": name, "n": len(values), "mean": mean, "ci_low": lo, "ci_high": hi, "ci_width": width, "sufficient": None if delta is None else width <= delta}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--score-key", default="score")
    ap.add_argument("--slice-key", default="slice")
    ap.add_argument("--delta", type=float, help="検出したい差。指定すると十分/不足を判定")
    ap.add_argument("--compare", help="もう1つのスコアファイル。2つの差の信頼区間を出す")
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--ci", type=float, default=0.95)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = load(args.path, args.score_key, args.slice_key)
    if not data:
        print("スコアが読めませんでした。--score-key を確認してください", file=sys.stderr)
        return 1

    results = []
    print(f"ブートストラップ（{args.iters}回, CI={args.ci:.0%}）\n")
    results.append(report("ALL", [v for v, _ in data], args.delta, args.iters, args.ci))

    by_slice = defaultdict(list)
    for v, s in data:
        by_slice[s].append(v)
    if len(by_slice) > 1:
        print()
        for s, vals in sorted(by_slice.items()):
            results.append(report(f"slice={s}", vals, args.delta, args.iters, args.ci))

    if args.compare:
        other = [v for v, _ in load(args.compare, args.score_key, args.slice_key)]
        a = [v for v, _ in data]
        rng = random.Random(0)
        diffs = []
        for _ in range(args.iters):
            ma = sum(a[rng.randrange(len(a))] for _ in range(len(a))) / len(a)
            mb = sum(other[rng.randrange(len(other))] for _ in range(len(other))) / len(other)
            diffs.append(ma - mb)
        diffs.sort()
        lo = diffs[int((1 - args.ci) / 2 * args.iters)]
        hi = diffs[int((1 + args.ci) / 2 * args.iters) - 1]
        sig = "区間が0を跨がない → 差は有意" if lo > 0 or hi < 0 else "区間が0を跨ぐ → 差は有意ではない（件数不足の可能性）"
        print(f"\n差（{Path(args.path).name} − {Path(args.compare).name}）: {int(args.ci*100)}%CI=[{lo:+.3f}, {hi:+.3f}]  {sig}")
        results.append({"name": "diff", "ci_low": lo, "ci_high": hi, "significant": lo > 0 or hi < 0})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
