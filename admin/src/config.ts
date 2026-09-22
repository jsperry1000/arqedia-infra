/**
 * What this build points at.
 *
 * LITERALS, AND THE SAME ENV-01 AS ui/src/config.ts. A second environment
 * needs a second set of these and there is no mechanism yet; the application
 * has the same gap, recorded in ENV-01, and inventing a different one here
 * would make two problems out of one.
 *
 * NONE OF THESE IS A SECRET. A user pool id, a client id and an API hostname
 * are identifiers a token is verified against, not credentials: the pool's
 * client holds no secret (a browser cannot keep one), and the admin API
 * refuses every request that does not carry a staff token signed by that
 * pool. This is why, unlike ui/, this app needs no .env to build.
 */
export const config = {
  // The STAFF pool, not the customer one. us-east-2_AcsEyzDLL is the
  // customer pool and must never appear in this codebase: a build pointed at
  // it would sign a tenant in to a console that reads every tenant.
  userPoolId: "us-east-2_W6DrH8qdv",
  userPoolClientId: "5c2eetptctkuktm8m4tiep5oef",

  // The admin API. Its own gateway; the customer API is not reachable from
  // this bundle and holds nothing this console asks for.
  apiUrl: "https://mnjjhsw6ra.execute-api.us-east-2.amazonaws.com",

  // What an authenticator app shows beside the code.
  totpIssuer: "ARQEDIA staff",
};
