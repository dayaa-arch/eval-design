---
tags: [eval-design]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

うちのRAGチャットボット、GPT-4oに採点させて「事実整合性92%」って出てるんだけど、これ信用していい？人間が採点したデータは60件くらいある（labeled.csv、human/judge/length列）。
Input files: labeled.csv
