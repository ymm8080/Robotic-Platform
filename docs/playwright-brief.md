# Playwright E2E 测试框架搭建简报

> 日期：2026-06-21
> 项目：SAP-EWM 机器人调度平台 v3.4
> 根目录：`D:\EWM ROBOT\ROBOTIC PLATFORM CODES\`

---

## 一、修改的文件

### 1. `playwright.config.js` — 主配置文件（重写）

| 项目 | 修改前 | 修改后 |
|------|--------|--------|
| baseURL | `http://localhost:3000`（不存在） | `http://localhost:1880`（Node-RED） |
| 浏览器引擎 | 3 个（chromium/firefox/webkit） | 5 个 Project |
| 超时配置 | 默认值 | 显式设置（30s/15s/10s/20s） |
| .env 支持 | 无 | 引入 `dotenv` 加载 `.env` |

**新增 Project：**
| Project | 浏览器 | 目标端口 | 匹配规则 |
|---------|--------|----------|----------|
| `nodered-chromium` | Desktop Chrome | 1880 | `*.spec.js` |
| `nodered-firefox` | Desktop Firefox | 1880 | `*.spec.js`（超时 45s） |
| `nodered-webkit` | Desktop Safari | 1880 | `*.spec.js` |
| `rescue-dashboard-chromium` | Desktop Chrome | 8080 | `rescue-dashboard.spec.js` |
| `api-smoke` | 无浏览器 | 8000 | `api-*.spec.js` |

**关键配置项：**
- `fullyParallel: true` — 文件级并行执行
- `retries: CI ? 2 : 0` — CI 环境失败重试 2 次
- `trace: 'retain-on-failure'` — 失败保留 Trace
- `video: 'retain-on-failure'` — 失败保留录屏
- `screenshot: 'only-on-failure'` — 失败截图
- `ignoreHTTPSErrors: true` — 忽略自签名证书
- `reporter: ['html', 'list']` + CI 时追加 JUnit

---

### 2. `package.json` — 新增 11 个 Playwright 脚本

```json
"scripts": {
  "test:e2e":              "playwright test",
  "test:e2e:ui":           "playwright test --ui",
  "test:e2e:debug":        "playwright test --debug",
  "test:e2e:headed":       "playwright test --headed",
  "test:e2e:chromium":     "playwright test --project=nodered-chromium",
  "test:e2e:firefox":      "playwright test --project=nodered-firefox",
  "test:e2e:webkit":       "playwright test --project=nodered-webkit",
  "test:e2e:rescue":       "playwright test --project=rescue-dashboard-chromium",
  "test:e2e:api":          "playwright test --project=api-smoke",
  "test:e2e:auth":         "playwright test login.spec.js",
  "test:e2e:codegen":      "playwright codegen http://localhost:1880",
  "test:e2e:install":      "playwright install --with-deps",
  "test:e2e:all-browsers": "playwright test --project=nodered-chromium ...firefox ...webkit"
}
```

**新增 devDependency：** `dotenv@^17.4.2`

---

### 3. `.env.example` — 追加 Playwright 配置段

```ini
# Playwright E2E 测试配置
BASE_URL=http://localhost:1880
RESCUE_BASE_URL=http://localhost:8080
API_BASE_URL=http://localhost:8000
NODE_RED_ADMIN_USER=admin
NODE_RED_ADMIN_PASS=admin
CI=false
```

---

## 二、新增的文件

### `e2e/pages/` — 页面对象模型（4 个文件）

| 文件 | 导出的 Class | 主要方法 | 用途 |
|------|-------------|----------|------|
| `NodeRedLoginPage.js` | `NodeRedLoginPage` | `goto()`, `login()`, `enterUsername()`, `enterPassword()`, `clickLogin()`, `expectLoginFormVisible()`, `expectLoginError()`, `getErrorMessage()`, `isLoginFormVisible()` | Node-RED 管理员登录页 |
| `NodeRedDashboardPage.js` | `NodeRedDashboardPage` | `goto()`, `waitForDashboardReady()`, `expectDashboardLoaded()`, `deployFlow()`, `searchPalette()`, `openFlowTab()`, `logout()`, `getConnectionStatus()`, `getPageTitle()` | Node-RED 流编辑器主界面 |
| `RescueDashboardPage.js` | `RescueDashboardPage` | `goto()`, `waitForDashboardReady()`, `expectDashboardRendered()`, `getStatus()`, `getRobotCount()`, `getRobotStatusList()`, `clickRefresh()`, `getPageTitle()` | Nginx 急救降级页面 |
| `SapBridgeApi.js` | `SapBridgeApi` | `health()`, `ready()`, `live()`, `getRobotsStatus()`, `getRobotStatus(id)`, `getOrders()`, `expectHealthy()`, `expectReady()`, `expectLive()`, `expectRobotsStatusArray()` | SAP Bridge REST API 封装 |

### `e2e/fixtures/index.js` — 自定义 Fixture（更新）

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `authenticatedPage` | test | 已登录 Node-RED 管理界面的 Page 实例 |
| `noderedLoginPage` | test | NodeRedLoginPage POM 实例 |
| `noderedDashboardPage` | test | NodeRedDashboardPage POM 实例 |
| `rescueDashboardPage` | test | RescueDashboardPage POM 实例 |
| `sapBridgeApi` | test | SapBridgeApi API 封装实例 |

### `e2e/test-data/` — 测试数据（2 个文件）

| 文件 | 内容 |
|------|------|
| `robots.json` | 5 个 VDA5050 模拟机器人（KUKA/MiR/OTTO/OMRON）含状态、电量、位置；3 个模拟订单 |
| `env-tags.json` | 环境标签定义（PROD/STAGING） |

### `e2e/global-setup.js` — 全局启动钩子

- 检测 Node-RED（1880）、Rescue Dashboard（8080）、SAP Bridge API（8000）是否可访问
- 输出各服务健康状态 → 引导用户启动 Docker

### `e2e/global-teardown.js` — 全局收尾钩子

- 报告完成提示，指引查看 HTML 报告

---

## 三、Playwright 测试用例汇总（共 6 个 spec 文件）

总计 **63 个测试用例**，详见 `docs/playwright-test-cases.md`。

| Spec 文件 | 用例数 | 覆盖范围 |
|-----------|--------|----------|
| `login.spec.js` | 11 | Node-RED 登录页渲染、认证流程、Session 管理、安全测试 |
| `nodered-admin.spec.js` | 14 | Dashboard 布局、Canvas、Palette 搜索/节点验证、Sidebar、状态栏 |
| `rescue-dashboard.spec.js` | 12 | 急救面板加载、状态显示、机器人列表、刷新功能、中文本地化 |
| `api-health.spec.js` | 10 | /health/ready/live 探针、一致性检查、敏感信息、边界请求 |
| `api-robots.spec.js` | 10 | 机器人列表、VDA5050 状态验证、Redis 信息泄露防护、SQL 注入防护 |
| `nodered-api.spec.js` | 6 | 安全模式/恢复模式鉴权、Flows API、Admin API 安全扫描 |

---

## 四、环境依赖

- `@playwright/test@^1.61.0`（已有，仅在 devDependencies 中添加 `^` 号版本约束）
- `dotenv@^17.4.2`（新增，支持 .env 文件）
- 浏览器驱动：需运行 `npm run test:e2e:install` 安装 Chromium/Firefox/WebKit

---

## 五、快速开始

```bash
# 1. 确保 Docker 服务运行
docker compose up -d

# 2. 复制环境变量
cp .env.example .env

# 3. 安装浏览器（首次）
npm run test:e2e:install

# 4. 运行全部测试
npm run test:e2e

# 5. 查看报告
npm run test:e2e:report
```
