#!/usr/bin/env python3
"""検出したい差から必要サンプル数を計算する。

2つの方法で出す:
  1. 経験則（OpenAI Evalsのガイド）: 差が1/3になるごとに必要件数は10倍
     30% -> ~10件, 10% -> ~100件, 3% -> ~1,000件, 1% -> ~10,000件
  2. 二項比率の検定（2標本・両側）: 統計的な必要件数（標準ライブラリのみで計算）

使い方:
  python sample_size.py --delta 0.03
  python sample_size.py --delta 0.03 --baseline 0.85 --alpha 0.05 --power 0.8
  python sample_size.py --table            # 代表的な差の一覧表
  python sample_size.py --delta 0.03 --json
"""
import argparse
import json
import math
import sys


# ---- 経験則 ----
def rule_of_thumb(delta: float) -> int:
    """差が1/3になるごとに10倍。30%で10件をアンカーにする。"""
    if delta <= 0 or delta >= 1:
        raise ValueError("delta は 0 < delta < 1 で指定してください")
    # n = 10 * (0.30 / delta) ** log10(10)/log10(3) = 10 * (0.30/delta)^2.0959
    exponent = math.log(10) / math.log(3)
    return int(round(10 * (0.30 / delta) ** exponent))


# ---- 統計的な計算（二項比率、2標本、両側） ----
def _z(p: float) -> float:
    """標準正規分布の分位点（逆CDF）。Acklamの近似。"""
    if not 0 < p < 1:
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def two_proportion_n(p1: float, delta: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """比率 p1 と p1+delta を区別するのに必要な、各群のサンプル数。"""
    # baseline から上に delta 動かせないときは下に動かす（悪化を検出する向き）
    p2 = p1 + delta if p1 + delta < 1 else p1 - delta
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("baseline と baseline±delta は (0,1) の範囲にしてください")
    z_a = _z(1 - alpha / 2)
    z_b = _z(power)
    pbar = (p1 + p2) / 2
    num = (z_a * math.sqrt(2 * pbar * (1 - pbar)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (delta ** 2)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delta", type=float, help="検出したい差（例: 0.03 = 3ポイント）")
    ap.add_argument("--baseline", type=float, default=0.85, help="現在の合格率（統計計算用、既定0.85）")
    ap.add_argument("--alpha", type=float, default=0.05, help="有意水準（既定0.05）")
    ap.add_argument("--power", type=float, default=0.8, help="検出力（既定0.8）")
    ap.add_argument("--table", action="store_true", help="代表的な差の一覧表を出す")
    ap.add_argument("--json", action="store_true", help="JSONで出力")
    args = ap.parse_args()

    if args.table or args.delta is None:
        rows = []
        for d in (0.30, 0.10, 0.05, 0.03, 0.01):
            rows.append({
                "delta": d,
                "rule_of_thumb": rule_of_thumb(d),
                "statistical_per_group": two_proportion_n(args.baseline, d, args.alpha, args.power),
            })
        if args.json:
            print(json.dumps({"baseline": args.baseline, "alpha": args.alpha, "power": args.power, "rows": rows}, ensure_ascii=False, indent=2))
        else:
            print(f"必要サンプル数の目安（baseline={args.baseline:.0%}, alpha={args.alpha}, power={args.power}）\n")
            print(f"{'検出したい差':>12} | {'経験則':>10} | {'統計（各群）':>12}")
            print("-" * 42)
            for r in rows:
                print(f"{r['delta']:>11.0%} | {r['rule_of_thumb']:>10,} | {r['statistical_per_group']:>12,}")
            print("\n経験則: 差が1/3になるごとに必要件数は10倍（OpenAI Evalsガイド）。よく引かれる「3%→約1,000件」は3.3%を丸めた値")
            print("統計: 二項比率の2標本検定。モデルAとBを比べるなら各群にこの件数が必要")
        return 0

    rot = rule_of_thumb(args.delta)
    stat = two_proportion_n(args.baseline, args.delta, args.alpha, args.power)
    result = {
        "delta": args.delta,
        "baseline": args.baseline,
        "alpha": args.alpha,
        "power": args.power,
        "rule_of_thumb": rot,
        "statistical_per_group": stat,
        "recommendation": max(rot, stat),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"検出したい差: {args.delta:.1%}")
        print(f"  経験則（差1/3→件数10倍）      : 約 {rot:,} 件")
        print(f"  統計的（baseline={args.baseline:.0%}, α={args.alpha}, power={args.power}）: 各群 {stat:,} 件")
        print(f"  推奨（大きいほう）             : {result['recommendation']:,} 件")
        print("\n注: スライスごとに閾値判定するなら、各スライスにこの件数が必要です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
