import { defineConfig } from 'vite'
import { resolve } from 'node:path'
import { plansTable } from './plans-table'

// Multi-page, not a single-page app. Each page is a real file at a real path,
// so the site distribution needs no 403/404 rewrite and a genuine 404 stays a
// 404. See site.tf.
export default defineConfig({
  // The pricing page's plan table, rendered from config/plans.json while this
  // builds (18.5 / 11.3). It emits real HTML into the file; the browser never
  // fetches the JSON and the bundle does not know it exists. A missing or
  // malformed file stops the build - see plans-table.ts.
  plugins: [plansTable()],
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
        // The recipient's guide (12.3). Build wiring, not navigation: a page
        // absent from here is not built at all, and nothing links to this one
        // until the viewer and the share email exist.
        guide: resolve(__dirname, 'guide/index.html'),
      },
    },
  },
})
