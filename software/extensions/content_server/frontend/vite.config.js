import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import * as path from 'node:path'

export default defineConfig({
  root: './',
  publicDir: './public',
  plugins: [vue()],
  resolve: {
    alias: {
      'vue': 'vue/dist/vue.esm-bundler.js'
    }
  },
  server: {
    host: true,
    port: 9300,
    proxy: {
      '/api': {
        target: 'http://localhost:5050',
        changeOrigin: true
      },
      '/videos': {
        target: 'http://localhost:5050',
        changeOrigin: true
      },
      '/thumbnails': {
        target: 'http://localhost:5050',
        changeOrigin: true
      },
      '/pdfs': {
        target: 'http://localhost:5050',
        changeOrigin: true
      },
      '/figures': {
        target: 'http://localhost:5050',
        changeOrigin: true
      },
      '/code': {
        target: 'http://localhost:5050',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, './index.html')
      }
    }
  }
})
