// THE AGREEMENT A PERSON ACCEPTS, AND WHERE TO READ IT (27 October 2026).
//
// The version comes from config/legal.json at build, as TRIAL_DAYS comes from
// plans.json (trial.ts): the bundle carries a number and fetches nothing. It
// is sent with every acceptance, and the server refuses one that names any
// other version - so a page left open across a change of terms cannot accept
// words the person was never shown.
//
// THE PAGES ARE THE MARKETING SITE'S, at /terms, /privacy and /refunds,
// rendered there from docs/legal. They are public, marked noindex, and linked
// from nowhere on the site itself (decided 27 October 2026); these links are
// how a person reaches them.
import { agreement_version } from "../../config/legal.json";
import { config } from "./config";

export const AGREEMENT_VERSION: number = agreement_version;

export const LEGAL = {
  terms: `${config.siteUrl}/terms`,
  privacy: `${config.siteUrl}/privacy`,
  refunds: `${config.siteUrl}/refunds`,
};
