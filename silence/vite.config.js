import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/silence/',
  server: {
    host: true,
    proxy: {
      '/auth':  'http://corsproxy:5000',
      '/rawg':  'http://corsproxy:5000',
      '/proxy': 'http://corsproxy:5000',
    },
  },
})
