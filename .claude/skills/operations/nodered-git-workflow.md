---
name: nodered-git-workflow
description: Node-RED Git workflow — projects integration, branch strategy (master/develop/feature), deploy-time Git check
---

# Node-RED Git 工作流

## Projects 集成
- Node-RED settings.js 启用 `projects.enabled = true`
- 每次 Deploy 自动检查 Git 状态
- 有未提交变更 → 返回 403 阻止部署

## 分支策略
- `master`：生产环境（只读部署）
- `develop`：开发分支（CI/CD 自动部署）
- `feature/*`：功能分支

## 提交流程
1. 在 Node-RED Editor 完成修改
2. 点击 Deploy → Git 检查 → 通过
3. 提交：`git add . && git commit -m 'deploy-{timestamp}'`
4. 推送：`git push origin master`
