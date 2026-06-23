/* src/vite-env.d.ts */
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MQTT_WS_URL?: string
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
