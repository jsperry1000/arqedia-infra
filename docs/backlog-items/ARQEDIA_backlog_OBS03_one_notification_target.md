# OBS-03 — One notification target for everything that goes wrong quietly

**Raised 19 September 2026**, out of Stage 2.

---

## The problem

Three things now fail silently, each in its own way, and nothing tells
anybody about any of them.

    paddle_processor_failed   an SQS queue with an alarm on it (paddle.tf).
                              The alarm has no action: it changes state and
                              nobody hears. A Paddle event not applied is a
                              subscription not recorded, or credit somebody
                              paid for and did not receive.

    normalizer_failed         an SQS queue with no alarm at all (reconcile.tf).
                              A message here is an upload that was never read
                              and never refused - the case Stage 1 cannot
                              reach.

    [orphan]                  a log line from the reconciler. An object in the
                              docs bucket with no document row, printed every
                              fifteen minutes to a log nobody tails.

Each was left deliberately: an alarm is a decision about who gets woken, and
that decision had not been made. It still has not. But three unmade decisions
of the same shape are one decision.

## What it needs

**One SNS topic**, with whatever subscriptions suit - an address to begin
with. Then:

- an alarm action on the existing `paddle_processor_failed` alarm
- an alarm on `normalizer_failed` of the same shape: any message at all,
  `ApproximateNumberOfMessagesVisible > 0`, `treat_missing_data` not
  breaching
- a metric filter on `[orphan]`, and an alarm on it - the pattern needs the
  regex form `%\[orphan\]%`, not `"[orphan]"`, for the reason recorded in
  `observability.tf`

## What to decide first

**Who is woken, and for what.** These are not equally urgent:

- money not applied is urgent and is somebody's balance
- an upload never read is urgent to the person who uploaded it and invisible
  to them
- an orphan is a backstop finding, and by the time it fires the other two
  have usually already fired for the same incident

One topic with one address is the honest starting point, because there is one
person. It should not stay that way once there is a second.

## Not in scope here

Anything that pages. This is notification, not on-call.

## Done when

- One topic exists and is subscribed to.
- All three fire into it.
- A deliberate test message has been sent and received, because an alarm
  nobody has ever seen fire is an alarm nobody knows is wired.
