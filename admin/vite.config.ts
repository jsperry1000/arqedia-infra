import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// A single-page app, like ui/ and unlike site/. Unknown paths are routes, so
// the distribution rewrites 403 and 404 to index.html - see admin_frontend.tf.
//
// NO .env AND NO BUILD-TIME CHECK, deliberately, where ui/ has both. The
// application's build refuses without a Paddle pair because a bundle pointed
// at the wrong Paddle account takes real money. This bundle has no such
// value: the staff pool, its client and the admin API are public identifiers
// that a token is checked against, not secrets. The consequence is that this
// app builds from a clean checkout with nothing but `npm ci`, which is what
// lets CI build it (DRIFT-01's addendum, on what a clean checkout cannot do).
export default defineConfig({
  plugins: [react()],

  // tokens.css imports ui/src/tokens.css and index.html references /brand,
  // both above this project root.
  server: { fs: { allow: [".."] } },

  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
