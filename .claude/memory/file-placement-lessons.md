---
name: file-placement-lessons
description: 文件放置错误根因分析：skills/rules/memory 错位，脚本盲区，修复措施
metadata: 
  node_type: memory
  type: feedback
  tags: 
    - lessons
    - file-organization
    - quality
  originSessionId: 27d4ae34-931c-483c-9433-c808986b12d8
---

# 文件组织与验证教训

## 根因总结

| 根因 | 后果 | 修复 |
|------|------|------|
| 无文件放置决策树 | 22个含规则/知识的文件全放 skills/，永不自动触发 | 000-global-iron-rules.mdc 新增 §13 决策树 + §14 检查清单 |
| 创建后无强制检查清单 | 新文件未更新 MEMORY.md / today-session-context.json | §14 要求每个创建后执行 6 项检查 |
| 脚本盲区未被预见 | git diff HEAD 漏未跟踪文件；areaOrder 缺 Z 分类 | §15 防御性编程铁律 + 验证后 done |
| 不验证机制是否生效 | 不知道规则不会被触发就 claim done | §14-6 要求先验证再 done |

## 关键模式
- **skills/** = 用户 `/command` 触发（步骤流程）
- **rules/** = 每次会话自动加载（must-do 约束）
- **memory/** = 按标签召回，不自动加载（参考知识）

**Why:** 两天内反复出现同类问题（漏文件、放错位、描述不充分），说明缺少系统级预防机制
**How to apply:** 创建任何文件前先执行决策树（§13），创建后执行检查清单（§14）
**Related:** [[ewm-robot-project-root]], [[auto-daily-brief]]
