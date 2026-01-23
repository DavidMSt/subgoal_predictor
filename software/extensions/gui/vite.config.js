import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import * as path from 'node:path'
import { resolve } from 'path'

export default defineConfig({
  root: './',
  publicDir: './src/lib/assets',
  plugins: [vue()],
  resolve: {
    alias: {
      '@babylon_vis': path.resolve(__dirname, '../babylon/src/'),
      'vue': 'vue/dist/vue.esm-bundler.js',
      'events': 'events/'
    },
    // helps when using pnpm / workspaces / symlinked deps
    preserveSymlinks: true
  },
  server: {
    host: true,
    port: 9200,
    allowedHosts: ['.local', 'dale'],
    fs: {
      allow: [
        './',
        '../lib/',
        // ✅ explicitly allow the external source folder
        resolve(__dirname, '../babylon/src/')
      ]
    }
  },
  optimizeDeps: {
    // ✅ make Vite pre-bundle these (Babylon is large/esm and benefits from this)
    include: [
      '@babylonjs/core',
      '@babylonjs/gui',
      'chart.js/auto',
      'chartjs-adapter-moment',
      'chartjs-plugin-streaming',
      'events'
    ],
    // ✅ tell Vite to scan the external code too
    entries: [
      resolve(__dirname, './app.html'),
      resolve(__dirname, './gui.html'),
      // scan all your babylon source files
      resolve(__dirname, '../babylon/src/**/*.js')
    ]
  },
  build: {
    outDir: '../dist',
    rollupOptions: {
      input: {
        gui: path.resolve(__dirname, './gui.html'),
        app: path.resolve(__dirname, './app.html'),
      },
      output: {
        dir: path.resolve(__dirname, 'dist')
      }
    }
  }
})