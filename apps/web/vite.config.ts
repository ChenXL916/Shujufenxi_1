import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        onlyExplicitManualChunks: true,
        manualChunks(id: string): string | undefined {
          const moduleId = id.replace(/\\/g, '/')
          if (!moduleId.includes('/node_modules/')) return undefined
          if (
            /\/node_modules\/(?:react|react-dom|react-router|react-router-dom|scheduler|@tanstack\/react-query)\//.test(
              moduleId,
            )
          ) {
            return 'react'
          }
          if (moduleId.includes('/node_modules/zrender/')) return 'zrender'
          if (moduleId.includes('/node_modules/echarts/')) return 'echarts'
          if (moduleId.includes('/node_modules/@ant-design/icons')) return 'ant-design-icons'
          if (
            moduleId.includes('/node_modules/@ant-design/') ||
            moduleId.includes('/node_modules/rc-') ||
            moduleId.includes('/node_modules/@rc-component/')
          ) {
            return 'antd-rc'
          }
          if (moduleId.includes('/node_modules/antd/')) return 'antd'
          return undefined
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': apiProxyTarget,
      '/auth': apiProxyTarget,
      '/health': apiProxyTarget,
    },
  },
  preview: {
    host: '127.0.0.1',
    proxy: {
      '/api': apiProxyTarget,
      '/auth': apiProxyTarget,
      '/health': apiProxyTarget,
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
