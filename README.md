# eval-design

LLMアプリ（RAG、エージェント、チャットボット、抽出、分類など）の評価パイプラインを設計する Claude のスキルです。

相談に答えて終わるのではなく、リポジトリに置けばそのまま回る評価設計書と設定ファイル一式を出します。ルーブリック、スライス定義、閾値、必要サンプル数、ジャッジの校正手順、CIの設定までを含みます。

## できること

依頼の種類に応じて、次のいずれかを出します。

| 依頼 | 出すもの |
|---|---|
| 新機能の評価設計 | `eval-design.md`（設計書）、ルーブリック、スライス定義、閾値、ランナー設定 |
| モデルの乗り換えやプロンプト変更の判断 | 必要サンプル数の計算結果と、比較用のランナー設定・CI |
| LLM-as-a-Judge の校正 | 人手の採点との一致度（Cohenのκ・相関）、バイアス診断、改善案 |
| 既存の評価セットのレビュー | 件数、スライス、再現性、ルーブリックの質の診断 |

設計では次の考え方をとります。

- 処理の段階ごとの評価（ユニットテストに当たる）と、タスク達成の評価（E2Eテストに当たる）を両方作る
- 評価手法は安い順に重ねる。決定的チェック、軽量モデル、LLMジャッジ、人手評価の順
- LLMジャッジは人手の採点と照合してから使う。κが0.4未満なら採用しない
- 全体平均だけでなく、入力の種類やユーザー層ごとのスライスで見る
- 必要サンプル数は記憶で概算せず、スクリプトで計算する

## インストール

### Claude Code

個人用のスキルフォルダに置きます。

```bash
git clone https://github.com/dayaa-arch/eval-design.git ~/.claude/skills/eval-design
```

特定のプロジェクトだけで使う場合は、そのプロジェクトの `.claude/skills/eval-design` に置きます。

### Claude アプリ（claude.ai・デスクトップ）

このフォルダをzipにまとめ、設定画面からスキルとしてアップロードします。

## 使い方

「評価」という言葉を使わなくても、LLM機能の品質やモデル比較の相談をすると呼び出されます。名前を指定して呼ぶこともできます。

```text
/eval-design 履歴書PDFから今の勤務先を抽出する機能の評価を設計して。ランナーはPromptfooで。
```

依頼の例:

- 「サポートの自動応答を安いモデルに乗り換えたい。品質が3%落ちていないか確かめるには何件必要？」
- 「GPT-4oに採点させて事実整合性92%と出た。これは信用していい？人手の採点が60件ある」
- 「このevalセットをレビューして」

ランナーは Promptfoo、DeepEval、Inspect AI に対応しています。指定がなければ Promptfoo を使います。

## 付属スクリプト

Python 3 の標準ライブラリだけで動きます。

```bash
# 検出したい差から必要サンプル数を計算する
python3 scripts/sample_size.py --delta 0.03 --baseline 0.88

# 代表的な差の一覧表を出す
python3 scripts/sample_size.py --table

# 既存のスコアの信頼区間を出し、件数が足りているか判定する
python3 scripts/bootstrap.py results.csv --delta 0.03

# 人手の採点とジャッジの一致度、長さバイアス、位置バイアスを診断する
python3 scripts/judge_calibration.py labeled.csv
```

`sample_size.py --table` の出力例（現在の合格率85%、有意水準0.05、検出力0.8）:

```text
      検出したい差 |        経験則 |       統計（各群）
------------------------------------------
        30% |         10 |           36
        10% |        100 |          141
         5% |        427 |          686
         3% |      1,247 |        2,036
         1% |     12,471 |       19,461
```

## ファイル構成

```text
eval-design/
├── SKILL.md                  # スキル本体（手順と設計書の形式）
├── references/
│   ├── playbook.md           # 評価パイプラインの3ステップの詳細と具体例
│   ├── judge-calibration.md  # ジャッジの校正とバイアス対策
│   └── runners.md            # Promptfoo / DeepEval / Inspect AI の使い分けと設定例
├── assets/                   # 設計時に埋めるテンプレート
│   ├── rubric.template.yaml
│   ├── slices.template.yaml
│   ├── thresholds.template.yaml
│   ├── promptfooconfig.template.yaml
│   └── github-actions-eval.yml
├── scripts/
│   ├── sample_size.py        # 必要サンプル数
│   ├── bootstrap.py          # スコアの信頼区間
│   └── judge_calibration.py  # ジャッジの校正
└── evals/                    # このスキル自体を評価するテストケース
```

`evals/` には、スキルが期待どおりに動くかを確かめるケースが3つ入っています。評価設計、サンプル数の計算、ジャッジの校正です。各ケースは依頼文（`prompt.md`）、期待する結果（`case.yaml`）、採点基準（`graders/`）でできています。

## 範囲外のこと

- 本番の常時監視。このスキルはオフラインの回帰テスト一式を作り、Langfuse などの監視基盤とつなぐ場所だけを示します。
- モデルの学習や、公開ベンチマークの一般的な解説。
