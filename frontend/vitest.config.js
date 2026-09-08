import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { fileURLToPath } from 'url'

const currentDir = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': resolve(currentDir, 'src') } },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{js,ts}']
  }
})
