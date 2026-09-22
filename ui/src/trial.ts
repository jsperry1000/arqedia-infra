// THE TRIAL LENGTH, FROM THE ONE FILE THAT STATES IT (18.5 follow-up).
//
// It was written out as prose in three places here and three on the marketing
// site, all saying 30, while signup.TRIAL_DAYS said 14 - so every person who
// signed up between 17 and 22 September was told thirty days on the page that
// sold it, on the sign-in card, in the signup header and in the summary shown
// immediately before they committed, and was given fourteen.
//
// BAKED AT BUILD, NOT FETCHED. Vite inlines the value, so the bundle carries a
// number and no request is made for the file. The marketing site does the same
// thing through site/plans-table.ts, which reads the same key.
//
// THIS IS THE PUBLISHED FIGURE, NOT THE ENFORCING ONE. signup.TRIAL_DAYS is
// what computes tenant.trial_ends_at, and the signup Lambda bundles
// lambda/signup only, so it cannot read config/plans.json.
// tests/test_plans_source.py fails if the two ever differ - the same
// arrangement the plan prices have with the Paddle catalogue.
//
// Named, not the whole document: rollup keeps the number and drops the rest,
// so nothing else in plans.json reaches a browser.
import { trial_days } from "../../config/plans.json";

export const TRIAL_DAYS: number = trial_days;
