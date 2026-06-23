/* Dashboard configuration — adjust for your environment */

export const CONFIG = {
  /** MQTT WebSocket URL (browser cannot use raw TCP) */
  mqttWsUrl: import.meta.env.VITE_MQTT_WS_URL || 'ws://127.0.0.1:9001',

  /** MQTT connection options (anonymous) */
  mqttOptions: {
    clientId: `dashboard-${Math.random().toString(16).slice(2, 8)}`,
    clean: true,
    keepalive: 30,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
  } as const,

  /** VDA5050 topic prefix */
  /** 🔴 FIX: mqtt_publisher.py publishes to "vda5050/...", not "uagv/v2/..." */
  topicPrefix: 'vda5050',

  /** SAP Bridge API base (proxied through Vite in dev) */
  apiBase: import.meta.env.VITE_API_BASE || '/api',

  /** Refresh interval for stale robot detection (ms) */
  staleThresholdMs: 30_000,
} as const
