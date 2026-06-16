# SAP-EWM 机器人调度平台 v3.4

> **工业级容错 + 物理级防呆 + 人性化降级**

## 快速启动

```bash
# 1. 准备环境
cp .env.example .env
vim .env  # 填入真实值

echo "your-sap-password" > secrets/sap_password.txt
chmod 600 secrets/sap_password.txt

# 2. 启动全栈
docker compose up -d --build

# 3. 验证
 curl http://localhost:1880/api/system-health
```

## 文档

- [部署指南](docs/DEPLOY_GUIDE_v3.4.md)
- [48小时检查清单](docs/48h-checklist-v3.4.md)（39项）
- [架构清单](docs/CURSOR_ARCHITECTURE_MANIFEST_v3.4.md)
- [NTP时钟同步](docs/APPENDIX_NTP.md)
- [告警通道降级](docs/APPENDIX_NOTIFICATION.md)
- [灾难恢复演练](docs/APPENDIX_BACKUP.md)

## 版本

v3.4 FINAL - 2026-06-02
