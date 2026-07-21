/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

// Django's CSRF cookie name, inlined at build time via Vite `define`
// (VITE_CSRF_COOKIE_NAME → "csrftoken" default, "csrftoken_canopy" for the
// /canopy labs tenant). See vite.config.ts and src/api/base.ts.
declare const __CSRF_COOKIE_NAME__: string
