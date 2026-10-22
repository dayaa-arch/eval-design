#!/usr/bin/env python3
"""LLM-as-a-Judge の校正: 人手採点との一致度とバイアスを診断する。

入力: CSV または JSONL。各行に human, judge（スコア）、任意で length（出力の文字数）、
      pair 用に judge_swapped（AB順を入れ替えたときのジャッジ結果）。
  human,judge,length
  1,1,120
  0,1,480
  ...

出力:
  - カテゴリ採点（値の種類が少ない）: Cohen's κ、一致率
  - 順序/連続採点: Spearman ρ、Pearson r
  - 長さバイアス: judge と length の相関 vs human と length の相関
  - 位置バイアス: judge と judge_swapped の不一致率

使い方:
  python judge_calibration.py labeled.csv
  python judge_calibration.py labeled.jsonl --human-key human_score --judge-key llm_score
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path


def load(path):
    p = Path(path)
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if p.suffix == ".json":
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else d.get("results", [])
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def tonum(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in ("true", "pass", "passed", "yes"):
        return 1.0
    if s in ("false", "fail", "failed", "no"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def cohen_kappa(a, b):
    n = len(a)
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, po


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(x, y):
    return pearson(rank(x), rank(y))


def interpret_kappa(k):
    if k < 0.2:
        return "ほぼ一致なし → 不採用。ルーブリックから見直す"
    if k < 0.4:
        return "弱い一致 → 不採用。few-shot例の追加とルーブリック修正"
    if k < 0.6:
        return "中程度 → 要改善。CIゲートには使わず参考値に留める"
    if k < 0.8:
        return "良好 → 採用可。人間のスポットチェック5〜10%を継続"
    return "非常に良好 → 採用可"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--human-key", default="human")
    ap.add_argument("--judge-key", default="judge")
    ap.add_argument("--length-key", default="length")
    ap.add_argument("--swapped-key", default="judge_swapped")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = load(args.path)
    pairs = [(tonum(r.get(args.human_key)), tonum(r.get(args.judge_key)), r) for r in rows]
    pairs = [(h, j, r) for h, j, r in pairs if h is not None and j is not None]
    if len(pairs) < 10:
        print(f"有効な行が {len(pairs)} 件しかありません。校正には最低50件を推奨します", file=sys.stderr)
        if not pairs:
            return 1

    human = [h for h, _, _ in pairs]
    judge = [j for _, j, _ in pairs]
    n = len(pairs)
    out = {"n": n}

    print(f"校正セット: {n} 件\n")
    if n < 50:
        print("⚠️ 50件未満です。κや相関の信頼性が低いので、件数を増やしてから採用判断してください\n")

    categorical = len(set(human) | set(judge)) <= 5
    if categorical:
        k, agree = cohen_kappa(human, judge)
        out.update({"mode": "categorical", "kappa": k, "agreement": agree})
        print("【一致度（カテゴリ採点）】")
        print(f"  単純一致率   : {agree:.1%}")
        print(f"  Cohen's κ   : {k:.3f}  → {interpret_kappa(k)}")
        # 混同行列（2値のとき）
        if set(human) | set(judge) <= {0.0, 1.0}:
            tp = sum(1 for h, j in zip(human, judge) if h == 1 and j == 1)
            tn = sum(1 for h, j in zip(human, judge) if h == 0 and j == 0)
            fp = sum(1 for h, j in zip(human, judge) if h == 0 and j == 1)
            fn = sum(1 for h, j in zip(human, judge) if h == 1 and j == 0)
            print(f"  混同行列     : 人間=合格→ジャッジ合格 {tp} / 不合格 {fn}, 人間=不合格→ジャッジ合格 {fp} / 不合格 {tn}")
            if fp > fn * 2 and fp > 0:
                print("  ⚠️ ジャッジが甘い（人間が落としたものを通している）。ルーブリックの不合格例を増やす")
            elif fn > fp * 2 and fn > 0:
                print("  ⚠️ ジャッジが厳しい（人間が通したものを落としている）。合格基準の表現を見直す")
            out.update({"tp": tp, "tn": tn, "fp": fp, "fn": fn})
    else:
        rho, r = spearman(human, judge), pearson(human, judge)
        out.update({"mode": "ordinal", "spearman": rho, "pearson": r})
        print("【一致度（順序・連続採点）】")
        print(f"  Spearman ρ  : {rho:.3f}  （0.7以上で良好）")
        print(f"  Pearson r   : {r:.3f}")
        if rho < 0.5:
            print("  ⚠️ 相関が弱い。ルーブリックの各スコアに例を付け、few-shotで渡す")

    # 長さバイアス
    lengths = [tonum(r.get(args.length_key)) for _, _, r in pairs]
    if all(l is not None for l in lengths) and len(set(lengths)) > 1:
        rj, rh = pearson(judge, lengths), pearson(human, lengths)
        out.update({"length_corr_judge": rj, "length_corr_human": rh})
        print("\n【長さバイアス】")
        print(f"  ジャッジ×長さ : r={rj:+.3f}")
        print(f"  人間×長さ     : r={rh:+.3f}")
        if rj - rh > 0.2:
            print("  ⚠️ ジャッジが長い回答を贔屓している。ルーブリックに「長さは評価しない」を明記し、長さを正規化する")
        else:
            print("  ✅ 人間と同程度。問題なし")

    # 位置バイアス
    swapped = [tonum(r.get(args.swapped_key)) for _, _, r in pairs]
    if all(s is not None for s in swapped):
        flips = sum(1 for j, s in zip(judge, swapped) if j != s)
        rate = flips / n
        out["position_flip_rate"] = rate
        print("\n【位置バイアス（ペアワイズ）】")
        print(f"  順番入替で結果が変わった割合: {rate:.1%}")
        if rate > 0.10:
            print("  ⚠️ 10%超。常に両順序で採点して多数決にする")
        else:
            print("  ✅ 許容範囲")

    print("\n【次のアクション】")
    if categorical and out.get("kappa", 0) >= 0.6 or (not categorical and out.get("spearman", 0) >= 0.7):
        print("  - 採用可。rubric.yaml の calibration.last_kappa に結果を記録し、月1回の再校正を予定する")
    else:
        print("  - まだ採用しない。ルーブリック修正 → few-shot追加 → ジャッジモデル変更 の順で試し、再実行する")
    print("  - 本番ではジャッジ出力の5〜10%を人がスポットチェックし続ける")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
