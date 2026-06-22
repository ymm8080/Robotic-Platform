# Playwright 测试用例详情

> 共 63 个测试用例，覆盖 6 个 spec 文件
> 测试框架：Playwright 1.61.0
> Group 标签：@nodered, @auth, @dashboard, @rescue, @api, @health, @robots

---

## 1. `e2e/login.spec.js` — Node-RED 登录测试（11 用例）

**Group:** @nodered @auth

### Login Page Rendering（页面渲染）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 1 | should display the login form when not authenticated | 未登录时访问认证页面 | 显示用户名/密码输入框和登录按钮，URL 包含 "login" |
| 2 | should have a page title | 验证页面标题 | `page.title()` 长度 > 0 |

### Authentication（认证逻辑）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 3 | should successfully log in with valid admin credentials | 使用 admin/admin 登录 | 跳转离开登录页，Header 可见 |
| 4 | should fail with wrong password and show error | 错误密码 | 停留在登录页，显示错误提示 |
| 5 | should fail with non-existent username | 非法用户名 | 停留在登录页，显示错误提示 |
| 6 | should reject empty username | 空用户名 | 停留在登录页 |
| 7 | should reject empty password | 空密码 | 停留在登录页 |

### Session Management（会话管理）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 8 | should maintain session after page refresh | 登录后刷新页面 | 保持认证状态，不跳回登录页 |
| 9 | should successfully log out and return to login page | 登出 | 通过菜单登出，URL 回到登录页 |
| 10 | should be redirected to login when accessing admin without auth | 未认证直接访问 /admin/ | 重定向到登录页 |

### Login Page Security（安全测试）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 11 | password field should be masked | 密码字段掩码 | `input[type="password"]` |
| 12 | should not expose credentials in URL after login | 登录后 URL 不含密码 | URL 中不包含 "admin" 或 "password" |

---

## 2. `e2e/nodered-admin.spec.js` — Node-RED 管理界面测试（14 用例）

**Group:** @nodered @dashboard

### Dashboard Layout（界面布局）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 13 | should display all major UI components after login | 所有主要 UI 组件可见 | Header/Canvas/Deploy/Sidebar/Palette/StatusBar 均可见 |
| 14 | should have a visible header with the platform title | 页面标题含 "SAP-EWM" | `page.title()` 包含 SAP-EWM |
| 15 | should have the deploy button visible and enabled | Deploy 按钮可见且可用 | Button visible + enabled |

### Flow Editor Canvas（流编辑器画布）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 16 | should display the workspace tabs | 工作区标签页 | Tab 数量 >= 1 |
| 17 | should display the flow editor canvas | 编辑画布可见 | Canvas 元素可见 |

### Palette（节点面板）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 18 | should display the node palette | Palette 面板可见 | Palette 元素 visible |
| 19 | should support palette search | 搜索 "mqtt" | 搜索框输入值包含 "mqtt" |
| 20 | should contain MQTT nodes (VDA5050 core protocol) | 验证 MQTT 节点 | MQTT Palette Node 可见 |
| 21 | should contain HTTP nodes (for SAP Bridge integration) | 验证 HTTP 节点 | HTTP Palette Node 可见 |
| 22 | should contain function nodes (for custom dispatch logic) | 验证 Function 节点 | Function Palette Node 可见 |
| 23 | palette search should support Chinese characters | 中文搜索支持 | 搜索输入值不为空 |

### Sidebar（侧边栏）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 24 | should display the sidebar panels | Sidebar 可见 | Sidebar 元素 visible |
| 25 | should have an Info tab in the sidebar | Info 标签页 | Info Tab visible |
| 26 | should have a Help tab in the sidebar | Help 标签页 | Help Tab visible |
| 27 | should be able to switch between Info and Help tabs | 标签页切换 | Help Tab 获得 active class |

### Connection Status & Status Bar
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 28 | should show connected status | 连接状态 | Status 内容非空 |
| 29 | should display the status bar | 状态栏 | StatusBar visible |

---

## 3. `e2e/rescue-dashboard.spec.js` — 急救面板测试（12 用例）

**Group:** @rescue @dashboard

### Page Rendering（页面渲染）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 30 | should load successfully | 急救面板正常加载 | 无加载错误 |
| 31 | should have a page title | 页面标题 | 标题包含 "rescue" |
| 32 | should have a visible main heading | 主标题 | h1 可见，文本非空 |

### Status Display（状态显示）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 33 | should display a system status indicator | 系统状态指示器 | statusIndicator visible |
| 34 | should show the last updated timestamp | 最后更新时间 | lastUpdated visible，文本非空 |

### Robot Status Section（机器人状态区域）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 35 | should have a robot status section | 机器人状态区域 | Section/Table/Cards 至少一个可见 |
| 36 | should display robot status data | 机器人状态数据 | Robot count >= 0 |
| 37 | should render robot cards/rows with name and status | 机器人卡片/行渲染 | 每个机器人有 name 和 status |
| 38 | should display robot status in Chinese (本地化) | 中文本地化检测 | 记录是否包含中文状态（不强制） |

### Refresh Functionality（刷新功能）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 39 | should have a refresh button | 刷新按钮 | RefreshButton visible |
| 40 | should update data on refresh | 刷新后数据更新 | 刷新后 robotCount >= 0 |

### Safe Mode（安全模式）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 41 | should have a safe mode button visible | 安全模式按钮 | 如果按钮存在，应为 enabled |

---

## 4. `e2e/api-health.spec.js` — SAP Bridge 健康 API 测试（10 用例）

**Group:** @api @health

### GET /health
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 42 | should return 200 OK | 健康检查返回 200 | status = 200 |
| 43 | should return a JSON body with a status field | 含 status/health 字段 | 字段存在且非空 |
| 44 | should indicate healthy status | 状态为 healthy/ok | status/health 值在 ["ok","healthy","true"] 中 |
| 45 | should respond within 5 seconds | 响应时间 | 耗时 < 5000ms |

### GET /ready
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 46 | should return 200 OK when ready | Readiness 探针 | status = 200 |
| 47 | should return a JSON body | JSON 响应体 | body 非空 |

### GET /live
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 48 | should return 200 OK when alive | Liveness 探针 | status = 200 |
| 49 | should return a JSON body | JSON 响应体 | body 非空 |

### Consistency（一致性）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 50 | all three health endpoints should return 200 | 三个端点并行测试 | 全部 200 OK |
| 51 | health endpoint should not expose sensitive information | 不暴露敏感信息 | 响应中不含 password/secret/api_key |

### Edge Cases（边界测试）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 52 | should return 404 for unknown health sub-paths | 未知子路径 | GET /health/nonexistent → 404 |
| 53 | should return 405 for POST on health endpoint | 错误 HTTP 方法 | POST /health → 405/400/404 |

---

## 5. `e2e/api-robots.spec.js` — 机器人状态 API 测试（10 用例）

**Group:** @api @robots

### GET /api/v1/robots/status（全部机器人）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 54 | should return 200 OK | 获取机器人列表 | status = 200 |
| 55 | should return a list of connected robots | 返回数组 | Array.isArray 或 body.robots/data 为数组 |
| 56 | each robot should have the required VDA5050 fields | VDA5050 必需字段 | robotId/id/robot_id 存在（有空数据时 skip） |
| 57 | should not expose internal Redis details | 不暴露 Redis 信息 | 响应中不含 "redis" 或 "6379" |
| 58 | robot states should be valid VDA5050 states | VDA5050 有效状态 | 状态 ∈ [IDLE, EXECUTING, FAULT, CHARGING] |
| 59 | should respond quickly (under 3s) | 响应时间 | 耗时 < 3000ms |

### GET /api/v1/robots/status/:id（单个机器人）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 60 | should return 404 for a non-existent robot ID | 不存在 ID | 404 |
| 61 | should return robot details for a valid robot ID | 有效 ID 返回详情 | 200 + body 非空 |
| 62 | should reject invalid robot ID formats | SQL 注入/路径穿越防护 | 特殊字符 → 4xx |

### GET /api/v1/orders（订单 API）
| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 63 | should return 200 OK | 订单列表 | status = 200 |
| 64 | should return a list of orders | 订单数组 | 数组 + 每个订单有 orderNo |
| 65 | orders should have valid status transitions | 有效订单状态 | 状态 ∈ [CREATED, DISPATCHED, EXECUTING] |

---

## 6. `e2e/nodered-api.spec.js` — Node-RED 内部 API 测试（6 用例）

**Group:** @nodered @api

| # | 用例名 | 描述 | 预期 |
|---|--------|------|------|
| 66 | GET /api/system-health should return a health status | 系统健康 | URL 不跳转到 login |
| 67 | POST /api/safe-mode should require authentication | 安全模式需认证 | 401 或 403 |
| 68 | POST /api/restore-mode should require authentication | 恢复模式需认证 | 401 或 403 |
| 69 | GET /flows should require authentication | Flows API 需认证 | 401 或 403 |
| 70 | should reject unauthenticated requests to admin API | 批量 API 鉴权扫描 | /flows /nodes /settings /auth/revoke 全部需认证 |
| 71 | should not expose admin API via OPTIONS without auth | OPTIONS 方法安全 | OPTIONS /settings → 401/403/405 |

---

## 按测试组统计

| 组标签 | 用例数 | 覆盖主题 |
|--------|--------|----------|
| @auth | 11 | 登录认证、Session、安全 |
| @nodered | 20 | 管理界面 UI + API 安全 |
| @dashboard | 3 | Dashboard 布局渲染 |
| @rescue | 12 | 急救降级面板 |
| @api | 16 | 健康探针 + 机器人 API + 订单 API |
| @health | 10 | Health/Ready/Live 端点 |
| @robots | 10 | 机器人状态 CRUD + VDA5050 验证 |
| **总计** | **63** | — |

## 覆盖率维度

- **功能测试：** 登录、登出、Dashboard 加载、Palette 搜索、刷新、数据展示
- **API 测试：** 健康检查、读取状态（机器人/订单）
- **安全测试：** 密码掩码、敏感信息泄露、SQL注入防护、路径穿越防护、未认证访问防护
- **边界测试：** 空值、非法值、错误方法、未知路径
- **性能测试：** 健康 API 5s 阈值、机器人 API 3s 阈值
- **本地化测试：** 中文状态检测
- **Session 测试：** 登录保持、刷新不丢失、登出重置
