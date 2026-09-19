/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** injected by vite.config.ts define (from package.json version) */
declare const __APP_VERSION__: string
