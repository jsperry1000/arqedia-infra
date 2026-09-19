export const config = {
  userPoolId: "us-east-2_AcsEyzDLL",
  userPoolClientId: "7neoek1vpj90suoo8p8rrp04re",
  apiUrl: "https://o4fofn0ez5.execute-api.us-east-2.amazonaws.com",

  // Paddle's client-side token, and the environment it belongs to.
  //
  // PUBLIC BY DESIGN, and the only Paddle credential that may appear here.
  // Paddle's documentation: client-side tokens "have limited access to the
  // data in your system, so they're safe to publish", and "never use API keys
  // with Paddle.js - API keys should be kept secret and never used in your
  // frontend". The API key and the webhook secret live in Secrets Manager and
  // are read by the Lambda at start-up (decision record item 1); neither has
  // any business in a bundle.
  //
  // SANDBOX ONLY. A token is bound to one workspace: a test_ token works only
  // against sandbox, where no real money is involved, and a live_ token only
  // against live. They are different strings from different dashboards.
  //
  // ONE BUNDLE CANNOT SERVE BOTH (ENV-01). These two values are compiled into
  // web/, so the committed bundle carries a sandbox credential. Before live,
  // this file must come from the build rather than from git - an environment
  // variable read at build time, or a configuration fetched at start-up.
  // Shipping this bundle against a live Paddle account would open a sandbox
  // checkout at real prices and collect nothing.
  paddleToken: "test_2e70a9990de45a16d204d1297ad",
  paddleEnvironment: "sandbox" as const,
};
