import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(viteConfig, defineConfig({
  base: '/',   // matches the app's Vite base; vi.mock path resolution breaks with a non-root base
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.js'],
    exclude: ['tests/integration/**'],
  },
}))
