/**
 * Paddle.js, loaded once.
 *
 * WHY A MODULE AND NOT A COMPONENT. Paddle.js takes its event callback at
 * initialisation, not at open: there is one callback for the whole page, and
 * every checkout it will ever open reports through it. That is a singleton
 * whether we like it or not, so it is held here rather than inside a screen.
 *
 * WHAT THIS DOES NOT DO. It does not grant anything, record anything or
 * decide that a payment happened. Paddle's own documentation is explicit:
 * "A customer can close the checkout tab before the callback fires or
 * experience connection issues, so use webhooks to grant access reliably."
 * checkout.completed here is a CUE TO GO AND ASK OUR OWN SERVER, nothing
 * more - which is decision record item 6, where buckets are granted only from
 * transaction.completed webhooks and never from an API success response.
 */

import { initializePaddle, CheckoutEventNames, type Paddle } from
  "@paddle/paddle-js";
import { config } from "./config";

/** Which way the overlay ended. Neither means the money has reached us. */
export type CheckoutOutcome = "completed" | "closed";

let paddle: Paddle | undefined;
let loading: Promise<Paddle | undefined> | null = null;

// The open checkout's resolver, or null when none is open. One at a time,
// because the overlay is one at a time.
let settle: ((outcome: CheckoutOutcome) => void) | null = null;

function finish(outcome: CheckoutOutcome) {
  // completed is followed by closed when the person shuts the overlay. The
  // first one wins, and the second finds nothing left to resolve.
  const waiting = settle;
  settle = null;
  waiting?.(outcome);
}

function load(): Promise<Paddle | undefined> {
  if (paddle) return Promise.resolve(paddle);
  if (!loading) {
    loading = initializePaddle({
      environment: config.paddleEnvironment,
      token: config.paddleToken,
      eventCallback: (event) => {
        if (event.name === CheckoutEventNames.CHECKOUT_COMPLETED) {
          finish("completed");
        } else if (event.name === CheckoutEventNames.CHECKOUT_CLOSED) {
          finish("closed");
        }
      },
    }).then((instance) => {
      paddle = instance;
      return instance;
    });
  }
  return loading;
}

/**
 * Open the overlay for a transaction the server made, and answer when it
 * ends.
 *
 * transactionId rather than items, deliberately. Paddle: "Pass transactionId
 * to Paddle.Checkout.open() to open a checkout for the passed transaction.
 * You should do this instead of passing an array of items", and "you cannot
 * change items on the checkout at this point". The price, the customer and
 * the tenant reference were all set server-side (item 7); the browser names a
 * transaction and nothing else.
 */
export async function openCheckout(transactionId: string):
  Promise<CheckoutOutcome> {
  const instance = await load();
  if (!instance) {
    throw new Error(
      "The payment window could not be loaded. If an extension or a network " +
      "is blocking paddle.com, allow it and try again.");
  }
  return new Promise<CheckoutOutcome>((resolve) => {
    settle = resolve;
    instance.Checkout.open({ transactionId });
  });
}
