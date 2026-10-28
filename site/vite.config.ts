import { defineConfig } from 'vite'
import { resolve } from 'node:path'
import { plansTable } from './plans-table'
import { legalPages } from './legal-pages'

// Multi-page, not a single-page app. Each page is a real file at a real path,
// so the site distribution needs no 403/404 rewrite and a genuine 404 stays a
// 404. See site.tf.
export default defineConfig({
  // The pricing page's plan table, rendered from config/plans.json while this
  // builds (18.5 / 11.3). It emits real HTML into the file; the browser never
  // fetches the JSON and the bundle does not know it exists. A missing or
  // malformed file stops the build - see plans-table.ts.
  // The Terms, Privacy and Refund pages, written in from docs/legal at build
  // (27 October 2026). See legal-pages.ts.
  plugins: [plansTable(), legalPages()],
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
        // The Agreement (27 October 2026). Built, and linked from no page of
        // the site but each other: sign-up and the app link to them.
        terms: resolve(__dirname, 'terms/index.html'),
        privacy: resolve(__dirname, 'privacy/index.html'),
        refunds: resolve(__dirname, 'refunds/index.html'),
      },
    },
  },
})
