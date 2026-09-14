import { defineConfig } from 'vite'
import { resolve } from 'node:path'

// Multi-page, not a single-page app. Each page is a real file at a real path,
// so the site distribution needs no 403/404 rewrite and a genuine 404 stays a
// 404. See site.tf.
export default defineConfig({
  // tokens.css imports ui/src/tokens.css and the pages reference /brand,
  // both of which sit above this project root.
  server: { fs: { allow: ['..'] } },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        pricing: resolve(__dirname, 'pricing/index.html'),
      },
    },
  },
})
