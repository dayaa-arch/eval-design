# ランナーの使い分けと設定サンプル

ランナーは「評価を実行し、採点し、CIに繋ぐ」土台。スキルが作るルーブリック・閾値・スライスを、ここで選んだランナーの設定に落とし込む。

## 使い分け

| ランナー | 向いている場面 | 設定形式 | インストール |
|---|---|---|---|
| **Promptfoo** | 言語を問わずCIゲートにしたい。複数モデル・複数プロンプトの比較グリッド。レッドチーム | YAML | `npm install -g promptfoo` / `pip install promptfoo` |
| **DeepEval** | Pythonチーム。pytestと同じ書き味でLLM出力をテストしたい。RAG・エージェント・マルチターンのメトリクスが揃っている | Python | `pip install deepeval` |
| **Inspect AI** | 研究寄り。solver（どう答えさせるか）とscorer（どう採点するか）を分離してエージェント・ツール使用を評価したい | Python | `pip install inspect-ai` |

未指定ならPromptfooを仮定する（言語非依存で、設定がそのままリポジトリに置ける）。

## Promptfoo

`assets/promptfooconfig.template.yaml` を埋める。

要点：
- `providers` に比較したいモデルを列挙する（自分用リーダーボード）
- `defaultTest.assert` に決定的チェックを置く（全テストに適用）
- ジャッジは `llm-rubric` で、ルーブリックファイルの内容を渡す
- スライスは `tests` の `metadata` でタグ付けし、`promptfoo view` でフィルタする
- 閾値は `assert` の `threshold` と、CI側のexit codeで二重に守る

```yaml
# 最小例
providers:
  - id: anthropic:messages:claude-sonnet-4-5
  - id: openai:chat:gpt-4o
prompts:
  - file://prompts/extract_employer.txt
defaultTest:
  assert:
    - type: is-json
    - type: javascript
      value: output.length < 500   # 決定的チェックを先に
tests:
  - vars: { resume_text: file://data/resume_001.txt }
    metadata: { slice: "standard_pdf" }
    assert:
      - type: equals
        value: "株式会社Example"
  - vars: { resume_text: file://data/resume_042.txt }
    metadata: { slice: "multi_employer" }
    assert:
      - type: llm-rubric
        value: file://rubrics/factual_consistency.yaml
        threshold: 0.8
```

実行：`promptfoo eval && promptfoo view`。CIでは `promptfoo eval --no-cache -o results.json` の exit code で判定する。

## DeepEval

```python
# tests/test_extract_employer.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import GEval

factual = GEval(
    name="factual_consistency",
    criteria=open("rubrics/factual_consistency.yaml").read(),
    evaluation_params=["input", "actual_output", "expected_output"],
    threshold=0.8,
)

@pytest.mark.parametrize("case", load_cases("data/golden.jsonl"))
def test_extract(case):
    # 決定的チェックは普通のassertで先に
    out = app.extract(case["input"])
    assert isinstance(out, dict) and "employer" in out
    tc = LLMTestCase(
        input=case["input"],
        actual_output=out["employer"],
        expected_output=case["expected"],
    )
    assert_test(tc, [factual])
```

実行：`deepeval test run tests/`。スライスは `pytest -m slice_name` でマーカーを使う。

## Inspect AI

```python
# evals/extract_employer.py
from inspect_ai import Task, task, eval
from inspect_ai.dataset import json_dataset
from inspect_ai.scorer import model_graded_fact, match
from inspect_ai.solver import generate, system_message

@task
def extract_employer():
    return Task(
        dataset=json_dataset("data/golden.jsonl"),
        solver=[system_message(open("prompts/system.txt").read()), generate()],
        scorer=[match(), model_graded_fact()],  # 決定的 → ジャッジの順
    )
```

実行：`inspect eval evals/extract_employer.py --model anthropic/claude-sonnet-4-5`。`inspect view` でスパン単位の結果を見られる。エージェント評価（ツール呼び出しの軌跡）はこのランナーが最も扱いやすい。

## CI

`assets/github-actions-eval.yml` を `.github/workflows/eval.yml` に置く。設計方針：

1. PRごとにオフライン回帰スイートを回す
2. 決定的チェックは必ず全件。ジャッジは `EVAL_JUDGE_SAMPLE_RATE` で割合を制御（デフォルト1.0、コストが問題なら0.1）
3. `thresholds.yaml` の最低ラインを下回ったらfail
4. 結果JSONをアーティファクトとして保存し、前回との差分をPRコメントに出す
5. ルーブリック・閾値・ジャッジプロンプトの変更は、評価結果の変更として扱う（同じPRでアプリ側を変えない）
