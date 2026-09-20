/**
 * What this build points at.
 *
 * The Cognito and API values are still literals, and still wrong for a second
 * environment (ENV-01). The Paddle pair is not: it is read from the build, so
 * one codebase can produce a sandbox bundle or a live one, and producing the
 * wrong one is an error rather than a surprise.
 */

/** A value the build cannot proceed without.
 *
 *  NEVER DEFAULTED. A default here is how a bundle ends up pointed at the
 *  wrong Paddle account while looking perfectly healthy: sandbox prices
 *  against a live token collect nothing, and a live token in a test build
 *  takes real money. Missing is a failure, and it says so. vite.config.ts
 *  makes the same check at build time, so this one should never fire in a
 *  bundle that was built properly - it is the belt to that braces. */
function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `${name} is not set. Copy ui/.env.example to ui/.env and fill it in, ` +
      `then build again.`);
  }
  return value;
}

/** Where the marketing site answers.
 *
 *  Terraform's, through the build: `site_url` in site.tf is derived from
 *  local.site_host in dns.tf, which is also what the DNS records and the
 *  certificate are built from. So the hostname exists once in the stack and
 *  this bundle carries a copy of it rather than a second opinion. */
const siteUrl = required("VITE_SITE_URL", import.meta.env.VITE_SITE_URL);

const paddleEnvironment = required(
  "VITE_PADDLE_ENVIRONMENT", import.meta.env.VITE_PADDLE_ENVIRONMENT);

if (paddleEnvironment !== "sandbox" && paddleEnvironment !== "production") {
  throw new Error(
    `VITE_PADDLE_ENVIRONMENT must be "sandbox" or "production", not ` +
    `"${paddleEnvironment}".`);
}

const paddleToken = required(
  "VITE_PADDLE_TOKEN", import.meta.env.VITE_PADDLE_TOKEN);

// THE PAIR MUST AGREE. Paddle's documented format is
// ^(test|live)_[a-zA-Z0-9]{27}$, and the prefix names the workspace the token
// belongs to. A test_ token with environment "production" is ENV-01 happening
// in front of a paying customer, so it is refused here rather than diagnosed
// later from a checkout that silently does nothing.
const expectedPrefix = paddleEnvironment === "sandbox" ? "test_" : "live_";
if (!paddleToken.startsWith(expectedPrefix)) {
  throw new Error(
    `VITE_PADDLE_TOKEN does not match VITE_PADDLE_ENVIRONMENT: ` +
    `"${paddleEnvironment}" expects a token beginning "${expectedPrefix}".`);
}

export const config = {
  userPoolId: "us-east-2_AcsEyzDLL",
  userPoolClientId: "7neoek1vpj90suoo8p8rrp04re",
  apiUrl: "https://o4fofn0ez5.execute-api.us-east-2.amazonaws.com",

  // The marketing site. Read from the build rather than written here, so the
  // hostname lives in dns.tf and nowhere else in this codebase.
  siteUrl,

  // Paddle's client-side token, and the environment it belongs to.
  //
  // PUBLIC BY DESIGN. Paddle's documentation: client-side tokens "have
  // limited access to the data in your system, so they're safe to publish",
  // and "never use API keys with Paddle.js". The API key and the webhook
  // secret live in Secrets Manager and are read by the Lambda at start-up
  // (decision record item 1); neither has any business in a bundle.
  //
  // FROM THE BUILD, NOT FROM GIT (ENV-01, partly closed 19 September). These
  // are compiled in, so the bundle is still bound to one environment - but
  // which one is now a build input rather than a commit, and a build with the
  // wrong pair, or no pair at all, fails instead of shipping.
  //
  // STILL TRUE, AND STILL ENV-01: web/ is committed build output, so whatever
  // token the last build used is in git inside web/assets/. Moving the value
  // out of config.ts does not take it out of the repository. What it buys is
  // that the live build never needs the live token to be committed anywhere.
  paddleToken,
  paddleEnvironment: paddleEnvironment as "sandbox" | "production",
};
