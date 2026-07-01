import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  // Path prefix when deployed as a labs tenant (labs.connect.dimagi.com/canopy).
  // Drives import.meta.env.BASE_URL, which the router basename + API client
  // baseUrl derive from. Defaults to "/" for dev and the root deployment.
  base: process.env.VITE_BASE_PATH || '/',
  // Django's CSRF cookie name. Path-scoped per tenant on the shared labs host
  // (csrftoken_canopy) to avoid collision with sibling tenants; defaults to
  // Django's "csrftoken" for dev / the root deployment. Inlined at build time so
  // the frontend reads the right cookie. Applies in vitest too (respects define).
  define: {
    __CSRF_COOKIE_NAME__: JSON.stringify(
      process.env.VITE_CSRF_COOKIE_NAME || 'csrftoken',
    ),
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/accounts': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
})
