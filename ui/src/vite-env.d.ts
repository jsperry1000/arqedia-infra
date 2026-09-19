/// <reference types="vite/client" />

/** The build-time configuration this app requires.
 *
 *  Declared rather than left to Vite's index signature, so a typo in a
 *  variable name is a compile error instead of `undefined` at run time. */
interface ImportMetaEnv {
  /** "sandbox" or "production". Never defaulted - see config.ts. */
  readonly VITE_PADDLE_ENVIRONMENT?: string;
  /** Paddle's client-side token: test_ for sandbox, live_ for production. */
  readonly VITE_PADDLE_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
