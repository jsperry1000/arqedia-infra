# ARQEDIA — Backlog Item

## UP-02 · The upload screen does not refresh

| | |
|---|---|
| Status | Not built |
| Priority | Next. Low effort, and it is the reason upload "looks hung" |
| Type | Front end only. No API, no schema, no cost |
| Raised | 3 September 2026 |

---

### Observation

The register row is not written when the browser's PUT returns. S3 emits an
event, the normalizer reads the file, and only then does a row appear — seconds
later, and longer when Aurora is resuming from zero capacity.

The screen reads the register once when it loads and never asks again. So a
file uploads successfully, the screen shows nothing, and a hard refresh is the
only way to see what filed.

Observed twice in one session. Both times it read as a broken upload and was
diagnosed as one.

### Why polling, not a push from the backend

A backend trigger means a push channel — WebSockets or equivalent — which is
standing infrastructure held open per connected browser. That runs against the
zero-idle discipline behind the Aurora and Lambda decisions, for one screen.

Polling is a few reads against an API that already exists.

### Behaviour

- After a PUT completes, poll the register until the expected rows appear or a
  ceiling is reached.
- Stop polling when the screen is not in view, and when the ceiling is hit.
- **One poll in flight at a time.** The current screen dispatches `pending`,
  `documents` and `memos` twice over, the second set issued while the first is
  still outstanding — six requests where three would do, on the one path where
  each is already slow.
- The ceiling ends in a message, not in silence. "Still processing — refresh to
  check" is a worse answer than a row and a better one than nothing.

### The first read is slow, and that is not a fault

Aurora runs at `MinCapacity 0` and pauses when idle. Measured 3 September: the
first three requests after a pause took 12.8s, 13.3s and 13.6s; the next three
took 16ms, 23ms and 34ms. Around 590ms of each is Lambda cold start, the rest is
the cluster waking.

**The screen must say so.** Thirteen silent seconds is indistinguishable from a
hang, which is exactly how it was read. A loading state on these reads is part
of this item, not a separate one.

### Notes

- This does not fix the case where a file is rejected and no row is ever
  written. Polling for a row that will never appear ends at the ceiling with a
  message. The rejected row is UP-01.
- **Do not add polling on top of an upload the operator can fire repeatedly.**
  Whatever state the screen shows while waiting must also prevent a second
  submission of the same file.

### Acceptance

A file is uploaded and appears in the register without a manual refresh. While
waiting, the screen says what it is waiting for. Three reads are issued, not
six.
