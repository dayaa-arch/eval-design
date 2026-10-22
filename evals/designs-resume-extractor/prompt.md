---
tags: [eval-design]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

履歴書PDFをアップロードすると、今の勤務先を抽出して採用管理システムに登録する機能を作ります。PDF→テキスト抽出→勤務先抽出の2段階です。この機能の評価を設計してください。ランナーはPromptfooで、CIはGitHub Actionsです。
