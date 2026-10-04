import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { ProxyOptions } from 'vite'
import { defineConfig } from 'vitest/config'

const API_TARGET = 'http://127.0.0.1:8000'

// When FastAPI isn't running, answer like the API would (JSON `detail`) instead of a bare 500.
const apiProxy: ProxyOptions = {
  target: API_TARGET,
  configure: (proxy) => {
    proxy.on('error', (_error, _request, response) => {
      if (!('writeHead' in response) || response.headersSent) return
      response.writeHead(503, { 'Content-Type': 'application/json' })
      response.end(
        JSON.stringify({
          detail: `No se pudo conectar a la API en ${API_TARGET}. Levántala con: uv run uvicorn app.main:app --reload`,
        }),
      )
    })
  },
}

// In dev, Vite proxies API calls to FastAPI so the UI uses same-origin URLs
// (the same ones it gets in production, where FastAPI serves web/dist).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': apiProxy,
      '/health': apiProxy,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Vitest 4: restoreMocks only restores spies; mockReset also clears calls and implementations of
    // vi.fn() mocks (e.g. the mocked API client) so no state leaks between tests.
    mockReset: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      // text-summary for the terminal, html to browse (web/coverage/index.html), lcov for Coveralls.
      reporter: ['text-summary', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/**/*.d.ts', 'src/test/**', 'src/**/*.test.{ts,tsx}'],
    },
  },
})
