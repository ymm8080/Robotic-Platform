# Prompts — Version Management

> Design doc v3.35, Blindspot #20: "Prompt 版本管理（文档即代码，git 管理 + model_tested 元数据）"

Rules:
1. **Every prompt has YAML frontmatter** with `model_tested`, `date`, `version`, `known_limitations`
2. **Version bump** when model changes or prompt logic changes
3. **Never delete old versions** — archive as `v1.0_20260601/001_generate_subflow_geek.md`
4. **Test with target model** before committing

## Current Prompts

| ID | Title | Model Tested | Version | Date |
|----|-------|-------------|---------|------|
| 001 | 生成极智嘉机器人 Sub-flow | Kimi K2.6, Claude Sonnet 4.6 | 1.0 | 2026-06-01 |
| 002 | 生成 SAP 桥接层 Dockerfile | Claude Sonnet 4.6 | 1.0 | 2026-06-01 |
| 003 | 凌晨2点急救 — 系统停摆应急处理 | Claude Sonnet 4.6, Kimi K2.6 | 1.1 | 2026-06-01 |

## Adding a New Prompt

```yaml
---
prompt_id: 004
title: 简短描述
model_tested: <model_name>
date: <YYYY-MM-DD>
version: 1.0
input: {param1, param2}
output: {output1, output2}
known_limitations: "已知限制"
---
```

## Git Workflow

```bash
# All prompts tracked in git
git add prompts/
git commit -m "prompts: add v1.1 of 003-rescue with updated model metadata"
```
