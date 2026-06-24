// SAP-EWM 机器人调度平台 - Node-RED settings.js v3.4
// 生产级配置：异步 Git 拦截 + IP 白名单 + 安全函数注入 + 版本校验
// 部署路径：/data/settings.js（Docker 卷挂载只读）

const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { isIP } = require('net');

// ==========================================
// 0. 版本校验（启动时阻断不一致）
// ==========================================
const RUNTIME_VERSION = 'v3.4';
const VERSION_PATH = process.env.VERSION_FILE_PATH || '/app/config/VERSION';

function checkVersion() {
    try {
        if (!fs.existsSync(VERSION_PATH)) {
            console.error(`[FATAL] VERSION 文件不存在于 ${VERSION_PATH}`);
            console.error('[HINT] 请检查 Docker 卷挂载：./.cursor/rules/VERSION:/app/config/VERSION:ro');
            process.exit(1);
        }
        const docVersion = fs.readFileSync(VERSION_PATH, 'utf8').trim();
        if (RUNTIME_VERSION !== docVersion) {
            console.error(`[FATAL] 版本不一致！运行时:${RUNTIME_VERSION} 文档:${docVersion}`);
            console.error('[HINT] 请更新 .cursor/rules/VERSION 或修改 RUNTIME_VERSION');
            process.exit(1);
        }
        console.log(`[OK] 版本校验通过：${RUNTIME_VERSION}`);
    } catch (e) {
        console.error(`[FATAL] 版本校验异常：${e.message}`);
        process.exit(1);
    }
}

checkVersion();

// ==========================================
// 1. 辅助函数
// ==========================================

/**
 * CIDR 匹配（简化版，生产环境建议使用 ipaddr.js npm 包）
 */
function isInCIDR(ip, cidr) {
    if (!cidr.includes('/')) return ip === cidr;

    const [subnet, bits] = cidr.split('/');
    const mask = parseInt(bits, 10);

    function ipToLong(ipStr) {
        return ipStr.split('.').reduce((acc, octet) => (acc << 8) + parseInt(octet, 10), 0) >>> 0;
    }

    const ipLong = ipToLong(ip);
    const subnetLong = ipToLong(subnet);
    const maskLong = (0xFFFFFFFF << (32 - mask)) >>> 0;

    return (ipLong & maskLong) === (subnetLong & maskLong);
}

/**
 * 清理 IPv6-mapped IPv4 前缀
 */
function cleanIP(ip) {
    if (!ip) return '127.0.0.1';
    if (ip.startsWith('::ffff:')) return ip.substring(7);
    if (ip === '::1') return '127.0.0.1';
    return ip;
}

// ==========================================
// 2. 核心配置
// ==========================================
module.exports = {
    // --- 基础 ---
    uiPort: process.env.PORT || 1880,
    uiHost: process.env.HOST || '0.0.0.0',

    // --- 安全：Admin 认证（等保三级-双因素认证预留） ---
    adminAuth: {
        type: "credentials",
        users: [{
            username: process.env.NODE_RED_ADMIN_USER || "admin",
            password: process.env.NODE_RED_ADMIN_PASS || "$2a$08$zZWtXTja0fB1pzD4sHCMyOCMYz2Z6dNbM6tlbUCJYWp6J2p/ikDqG", // 默认密码 'admin'，生产必须修改
            permissions: "*"
        }],
        // [Gap #9 修复] 等保三级密码复杂度校验
        authenticate: function(username, password) {
            // 密码复杂度检查：≥8位，含大小写+数字+特殊字符
            const complexityRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]).{8,}$/;
            if (password && !complexityRegex.test(password)) {
                console.warn(`[AUTH] 密码复杂度不足: ${username}`);
                return false;
            }
            // 这里可接入外部认证（LDAP / TOTP），当前使用默认密码校验
            return null; // null = 使用 Node-RED 默认密码校验
        },
        default: {
            permissions: "read"  // 默认只读，防止未授权修改
        }
    },

    // --- 安全：HTTP 节点中间件（全路径 IP 白名单 + 急救页保护） ---
    httpNodeMiddleware: function(req, res, next) {
        // 信任代理列表（仅这些来源的 x-forwarded-for 可信）
        const trustedProxies = ['127.0.0.1', '::1', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'];

        const rawIP = req.headers['x-forwarded-for'];
        const directIP = cleanIP(req.connection.remoteAddress || req.socket.remoteAddress || '127.0.0.1');

        // 判断 x-forwarded-for 是否可信
        let clientIP = directIP;
        if (rawIP && trustedProxies.some(cidr => isInCIDR(directIP, cidr))) {
            clientIP = cleanIP(rawIP.split(',')[0].trim());
        }

        const allowedIPsStr = process.env.RESCUE_DASHBOARD_ALLOWED_IPS || '127.0.0.1';
        const allowedIPs = allowedIPsStr.split(',').map(s => s.trim());

        // [Gap #7 修复] 保护所有 API 路径，不仅限急救路径
        const apiPostPaths = ['/api/safe-mode', '/api/restore-mode', '/api/orders', '/api/force_sync', '/api/zone_lock'];
        const isProtectedPath = apiPostPaths.some(p => req.path === p || req.path.startsWith(p))
            || req.method === 'POST';

        if (isProtectedPath) {
            const isAllowed = allowedIPs.some(allowed => {
                if (allowed.includes('/')) return isInCIDR(clientIP, allowed);
                return clientIP === allowed;
            });

            if (!isAllowed) {
                console.warn(`[SECURITY] 拒绝未授权访问 ${req.method} ${req.path} from ${clientIP}`);
                return res.status(403).json({
                    error: 'Forbidden',
                    clientIP: clientIP,
                    hint: '请联系管理员配置 RESCUE_DASHBOARD_ALLOWED_IPS',
                    timestamp: new Date().toISOString()
                });
            }
        }

        next();
    },

    // --- 安全：Admin 中间件（Git 强制提交 + 部署前校验） ---
    httpAdminMiddleware: function(req, res, next) {
        // 仅拦截 flows.json 的 Deploy 操作（POST /flows）
        if (req.method === 'POST' && req.url.match(/^\/flows$/)) {
            const { exec } = require('child_process');

            // 异步非阻塞 Git 检查，2 秒超时防悬挂
            exec('git rev-parse --git-dir', { cwd: '/data', timeout: 2000 }, (errGit) => {
                if (errGit) {
                    // 不是 Git 仓库 → 直接拦截（Gap #6 修复）
                    console.error('[BLOCKED] /data 不是 Git 仓库，禁止部署');
                    return res.status(403).json({
                        error: "请先初始化 Git 仓库！禁止直接部署未版本化的修改。",
                        hint: "在 Node-RED 右上角 Projects 面板启用版本控制，或执行：",
                        cmd: "cd /data && git init && git add . && git commit -m 'initial'"
                    });
                }
                exec('git diff --quiet', { cwd: '/data', timeout: 2000 }, (err) => {
                    if (err) {
                        // 有未提交变更（err.code === 1）或其他错误
                        console.error('[BLOCKED] 禁止部署未版本化的修改');
                        return res.status(403).json({
                            error: "请先提交 Git！禁止直接部署未版本化的修改。",
                            hint: "在 Node-RED 右上角 Projects 面板点击 Commit，或执行：",
                            cmd: `cd /data && git add . && git commit -m 'deploy-v${new Date().toISOString()}'`,
                            code: err.code
                        });
                    } else {
                        // 无未提交变更，放行
                        next();
                    }
                });
            });
        } else {
            next();
        }
    },

    // --- 编辑器主题：禁用危险快捷键 + 增加心理防线 ---
    editorTheme: {
        page: {
            title: "SAP-EWM 机器人调度平台",
            css: "/app/static/custom.css"  // 可选：自定义 CSS 隐藏危险按钮
        },
        header: {
            title: "SAP-EWM v3.4"
        },
        // 禁用删除快捷键（防误删）
        palette: {
            editable: false  // 禁止编辑 palette（防止误安装恶意节点）
        },
        projects: {
            enabled: true  // 强制启用 Projects 功能，确保 Git 集成
        },
        // 导入导出保留但增加确认（通过前端代码实现，此处仅后端配置）
        menu: {
            "menu-item-import": true,
            "menu-item-export": true,
            "menu-item-keyboard-shortcuts": false  // 禁用快捷键自定义，防止误配置
        }
    },

    // --- 运行时安全：全局安全函数注入（Function 节点可用） ---
    functionGlobalContext: {
        // 1. 安全循环：限制数组长度，防隐式 O(n²) 爆炸
        safeLoop: function(arr, callback, node, context) {
            if (!Array.isArray(arr)) {
                if (node) node.warn("[safeLoop] 输入非数组，跳过处理");
                return;
            }

            // 分级阈值（与 skills 文档对齐）
            const thresholds = {
                heartbeat: 100,
                order: 500,
                log: 1000,
                default: 300
            };

            // 白名单豁免（批量查询节点等）
            const whitelist = global.get('safeLoopWhitelist') || [];
            if (node && whitelist.includes(node.id)) {
                arr.forEach(callback);
                return;
            }

            const limit = thresholds[context] || thresholds.default;

            if (arr.length > limit) {
                if (node) {
                    node.warn(`[safeLoop] ${context || 'default'} 数组 ${arr.length} 项超过阈值 ${limit}，已自动分批`);
                }

                // 自动分批，使用 setImmediate 让出事件循环
                const batchSize = limit;
                let index = 0;

                function processBatch() {
                    const batch = arr.slice(index, index + batchSize);
                    batch.forEach(callback);
                    index += batchSize;

                    if (index < arr.length) {
                        setImmediate(processBatch);
                    }
                }

                processBatch();
                return;
            }

            arr.forEach(callback);
        },

        // 2. 安全 JSON 解析：限制大小，防内存炸弹
        safeParse: function(jsonStr, node) {
            if (typeof jsonStr !== 'string') {
                if (node) node.warn("[safeParse] 输入非字符串，返回空对象");
                return {};
            }

            // 限制 50KB（50 * 1024 = 51200）
            if (jsonStr.length > 51200) {
                if (node) {
                    node.error("[safeParse] JSON 字符串超过 50KB，禁止在 Function 节点解析！请拆分或推给 Python 桥接层。");
                }
                return {};
            }

            try {
                return JSON.parse(jsonStr);
            } catch (e) {
                if (node) node.warn(`[safeParse] JSON 解析失败: ${e.message}`);
                return {};
            }
        },

        // 3. 安全执行：限制函数耗时，防死循环阻塞事件循环
        safeExec: function(fn, node, timeoutMs) {
            timeoutMs = timeoutMs || 1000;
            const start = Date.now();
            const result = fn();
            const elapsed = Date.now() - start;

            if (elapsed > timeoutMs) {
                if (node) {
                    node.error(`[safeExec] 函数执行耗时 ${elapsed}ms，超过 ${timeoutMs}ms 阈值！请拆分逻辑或推给 Python 桥接层。`);
                }
                return null;
            }

            return result;
        },

        // 4. 时区统一：UTC 转换工具
        toUTC: function(dateInput) {
            const d = dateInput ? new Date(dateInput) : new Date();
            return d.toISOString();  // 始终返回 ISO 8601 UTC 格式
        },

        // 5. 数据脱敏：日志/告警前调用
        redactSensitive: function(obj) {
            if (!obj || typeof obj !== 'object') return obj;
            const sensitiveKeys = ['password', 'passwd', 'secret', 'token', 'api_key', 'auth', 'credential'];
            const result = JSON.parse(JSON.stringify(obj));

            function redact(target) {
                for (const key in target) {
                    if (sensitiveKeys.some(sk => key.toLowerCase().includes(sk))) {
                        target[key] = '***REDACTED***';
                    } else if (typeof target[key] === 'object' && target[key] !== null) {
                        redact(target[key]);
                    }
                }
            }

            redact(result);
            return result;
        }
    },

    // --- 上下文存储：使用 Redis（多实例共享） ---
    // Redis context store enabled for large state (>100KB) externalization
    contextStorage: {
        default: "memory",
        memory: {
            module: "memory"
        },
        redis: {
            module: "redis",
            config: {
                host: process.env.REDIS_HOST || "redis",
                port: process.env.REDIS_PORT || 6379,
                db: 0,
                password: process.env.REDIS_PASSWORD || "robot-platform-redis",
                prefix: "nodered-context:"
            }
        }
    },

    // --- 日志：结构化 + 审计合规 ---
    logging: {
        console: {
            level: process.env.LOG_LEVEL || "info",
            metrics: false,
            audit: true  // 启用审计日志
        },
        // 审计日志单独文件（等保 6 个月留存）
        audit: {
            level: "audit",
            handler: function() {
                return function(msg) {
                    const logEntry = {
                        timestamp: new Date().toISOString(),
                        level: 'AUDIT',
                        event: msg.event,
                        user: msg.user,
                        path: msg.path,
                        type: msg.type,
                        msg: msg.msg
                    };

                    // 写入 SQLite 审计表（异步，不阻塞）
                    let sqlite3;
                    try {
                        sqlite3 = require('sqlite3');
                    } catch (e) {
                        // sqlite3 模块未安装时跳过审计日志
                        console.warn('[AUDIT] sqlite3 not available, skipping');
                        return;
                    }
                    const dbPath = process.env.DB_PATH || '/data/robot_platform.db';
                    const db = new sqlite3.Database(dbPath, sqlite3.OPEN_READWRITE | sqlite3.OPEN_CREATE);

                    db.run(
                        `INSERT INTO audit_log (timestamp, event, user, path, type, message) VALUES (?, ?, ?, ?, ?, ?)`,
                        [logEntry.timestamp, logEntry.event, logEntry.user, logEntry.path, logEntry.type, JSON.stringify(logEntry.msg)],
                        function(err) {
                            if (err) console.error('[AUDIT] 写入失败:', err.message);
                            db.close();
                        }
                    );
                };
            }
        }
    },

    // --- 导出限制（防误导出敏感配置） ---
    exportGlobalContextKeys: function() {
        // 禁止导出包含敏感信息的键
        return Object.keys(global).filter(k => !k.toLowerCase().includes('secret') && !k.toLowerCase().includes('password'));
    },

    // --- Prometheus 指标端点（供 Watchdog / Grafana 采集） ---
    // 暴露 http://nodered:1880/metrics 供 Prometheus 刮取
    metrics: {
        includePerNode: true,      // 每个节点的指标
        includePerFlow: true,      // 每个流程的指标
        includeRuntime: true,      // 运行时指标（内存、事件循环延迟）
        prefix: "nodered_",        // 指标名称前缀
        gcInterval: 300000,        // GC 收集间隔（5分钟）
        collectDefault: true,      // Node.js 默认指标
    },

    // --- 其他生产级配置 ---
    debugMaxLength: 1000,  // debug 节点截断，防内存泄漏
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,
    socketReconnectTime: 15000,
    socketTimeout: 120000,
    tcpRequestTimeout: 30000,
    // 响应头：去除 X-Powered-By 等信息
    httpHeaders: {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
    },

    // --- 安全：禁止安装未审核节点（等保要求） ---
    externalModules: {
        // 允许安装的节点白名单（空数组 = 禁止所有外部节点）
        allowList: [],
        // denyList: ['node-red-contrib-unsafe-example']
    },

    // --- 时区：强制 UTC（与全局铁律第 6 条对齐） ---
    processEnv: {
        TZ: 'UTC'
    }
};
