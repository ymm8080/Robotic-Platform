---
name: robot-dashboard-phase1
description: Fleet monitoring dashboard — React SPA with MQTT real-time, order form, Docker
metadata:
  type: project
---

# Robot Dashboard (Phases 1-3)

**Decision:** Built a fleet monitoring dashboard (`dashboard/`) using Vite + React 18 + TypeScript + MQTT.js.

## Architecture

- Browser connects to MQTT broker via WebSocket (port 9001) for real-time robot state
- Subscribes to `uagv/v2/+/+/state` + `connection` for all robots
- API calls (`/api/v1/orders`, `/api/v1/robots/status`) proxied to SAP Bridge via Nginx
- Production: Nginx container serves static SPA + proxies API
- Dev: `npm run dev` (port 4000) with Vite proxy

## Structure

| Path | Purpose |
|------|---------|
| `src/hooks/useMqtt.ts` | MQTT WebSocket connection + state management |
| `src/types/vda5050.ts` | Full VDA5050 type defs + `deriveDisplayState()` |
| `src/components/RobotList.tsx` | Robot card list + stats bar |
| `src/components/RobotCard.tsx` | Single robot status card |
| `src/components/RobotDetail.tsx` | Single robot detail view (click card) |
| `src/components/OrderForm.tsx` | Manual order form → `POST /api/v1/orders` |
| `src/components/TaskList.tsx` | Recent order list → `GET /api/v1/orders` |
| `Dockerfile` + `nginx.default.conf` | Production static serve + API proxy |
| `docker-compose.yml` | Dashboard service (port 4000, depends on sap-bridge) |

## SAP Bridge API 新增

- `POST /api/v1/orders` — 创建 VDA5050 order 并发布到 MQTT，存入 Redis
- `GET /api/v1/orders` — 查询最近 50 条订单

## Environment

- MQTT: `allow_anonymous true` for dev (WebSocket port 9001)
- API proxy: Nginx → `http://sap-bridge:8000`
- Build: TypeScript 0 errors, Vite build ~530KB

## How to apply

- Dev: `cd dashboard && npm run dev` (port 4000)
- Production: `docker-compose up -d dashboard` (port 4000)
- 确认 MQTT broker 运行中（WebSocket 9001 端口）
- 确认 SAP Bridge 健康（`curl http://localhost:8000/health`）
