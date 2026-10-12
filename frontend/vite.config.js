import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync, writeFileSync } from 'fs'
import { resolve } from 'path'

function stampServiceWorker() {
  return {
    name: 'stamp-sw',
    writeBundle(options, bundle) {
      // Derive a hash from the output bundle so the SW cache name changes on every build.
      const hash = Object.keys(bundle)
        .filter(f => f.endsWith('.js') || f.endsWith('.css'))
        .sort()
        .join(',')
        .split('')
        .reduce((h, c) => (Math.imul(31, h) + c.charCodeAt(0)) | 0, 0)
        .toString(16).replace('-', '')

      const swSrc  = resolve(__dirname, 'sw.js')
      const swDest = resolve(options.dir, 'sw.js')
      const src = readFileSync(swSrc, 'utf8')
      writeFileSync(swDest, src.replace(/__CACHE_VERSION__/g, hash))
    },
  }
}

export default defineConfig({
  plugins: [vue(), stampServiceWorker()],
  base: '/',
  server: {
    host: true,
    allowedHosts: ['frontend', 'localhost'],
    fs: {
      // Allow Vite to serve files from /node_modules (mounted outside /frontend in dev)
      allow: ['/frontend', '/node_modules'],
    },
    // Dev entry point: Vite serves the app and forwards API calls to the Flask
    // backend container (which serves no pages).
    proxy: {
      '/auth':  'http://backend:5000',
      '/games': 'http://backend:5000',
    },
  },
})
