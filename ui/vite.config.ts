import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * FAIL AT BUILD, NOT AT RUN.
 *
 * config.ts throws when the Paddle pair is missing or mismatched, but that
 * throw happens in a browser, after a bundle has been written, committed and
 * possibly deployed. This check happens before a single file is emitted, so a
 * broken bundle never exists to be committed. Same rules, earlier.
 */
function requirePaddleConfig(env: Record<string, string>) {
  const environment = env.VITE_PADDLE_ENVIRONMENT;
  const token = env.VITE_PADDLE_TOKEN;
  const fix = "Copy ui/.env.example to ui/.env and fill it in.";

  if (!environment) {
    throw new Error(`VITE_PADDLE_ENVIRONMENT is not set. ${fix}`);
  }
  if (environment !== "sandbox" && environment !== "production") {
    throw new Error(
      `VITE_PADDLE_ENVIRONMENT must be "sandbox" or "production", not ` +
      `"${environment}".`);
  }
  if (!token) {
    throw new Error(`VITE_PADDLE_TOKEN is not set. ${fix}`);
  }
  const expected = environment === "sandbox" ? "test_" : "live_";
  if (!token.startsWith(expected)) {
    throw new Error(
      `VITE_PADDLE_TOKEN does not match VITE_PADDLE_ENVIRONMENT: ` +
      `"${environment}" expects a token beginning "${expected}".`);
  }
}

export default defineConfig(({ mode }) => {
  // Only VITE_-prefixed variables, which are the only ones Vite exposes to
  // the client anyway. Nothing else in the environment is read or embedded.
  requirePaddleConfig(loadEnv(mode, process.cwd(), "VITE_"));

  return {
    plugins: [react()],
    // Build straight into the folder GitHub Actions deploys.
    build: {
      outDir: "../web",
      emptyOutDir: true,
    },
  };
});
