# OBS-02 — A SELECT-only database user for the reconciler

**Raised 19 September 2026**, out of Stage 2. Noticed while writing a comment
that claimed a control the code does not have.

---

## The mistake it corrects

`reconcile.tf` first said:

> ExecuteStatement alone on the database. It only ever reads, and a role that
> cannot begin a transaction cannot write one either.

That is wrong, and wrong in the direction that matters. **`rds-data:Execute-
Statement` outside a transaction autocommits.** A role holding only that
action can `INSERT`, `UPDATE` and `DELETE` perfectly well - withholding
`BeginTransaction` stops it GROUPING writes, not making them.

So the reconciler is read-only because its code issues `SELECT`s. That is a
convention. It survives exactly as long as nobody adds a write to it, and
nothing would stop them.

## What would make it a control

A database user granted `SELECT` on `arqedia.document` and nothing else, with
its own secret, and `SECRET_ARN` on the reconciler pointing at that rather
than at the cluster's master secret.

Then a write from this function fails at the database, whoever wrote it and
whatever the IAM policy says.

## Why it was not done inline

It is not one line. It needs a user created outside Terraform (the master
secret is managed by RDS and users are not in the schema), a secret to hold
it, rotation decided, and a migration or a runbook step that is not a
migration. That is a piece of work, and Stage 2 was scoped to a queue and a
schedule.

## Wider than the reconciler

Every Lambda in the stack reads the database as the master user: normalizer,
extraction, collector, composition, api, signup, paddle. The API writes and
must; the reconciler never writes and could be stopped. Between those two
sit functions that write a little and read a lot.

Worth deciding once: whether ARQEDIA has one database identity or several,
and what each may do. One identity is simpler and is what exists; several is
what makes "this function cannot write" a fact rather than a habit.

## Done when

- The reconciler holds a credential that cannot write.
- The comment in `reconcile.tf` says what is enforced and by what.
- The wider question above is answered, or recorded as deliberately deferred
  with a reason.
