# OBS-01 — Declare the normalizer's log group in Terraform

**Raised 18 September 2026**, out of the observability work. Small, and needs
an import, which is why it was not done inline.

---

## What

`aws_cloudwatch_log_metric_filter.normalizer_error` in `observability.tf`
references its log group by name:

    log_group_name = "/aws/lambda/${aws_lambda_function.normalizer.function_name}"

The group itself is not declared. Lambda creates it on first invocation, and
Terraform does not know it exists.

## Why it was left

Declaring it would fail on apply against dev, where Lambda already created it:
`ResourceAlreadyExistsException`. Closing it properly means

    terraform import aws_cloudwatch_log_group.normalizer /aws/lambda/arqedia-dev-normalizer

which is a step beyond the three things the observability branch was scoped
to, and an import is not something to slip into a branch nobody expected one
in.

## What it costs to leave

Two things, neither urgent.

**Retention is unbounded.** An auto-created Lambda log group keeps events for
ever. The API access group declared beside it is set to thirty days; the
normalizer's is not, and nor is any other function's. Every Lambda log group
in the stack has the same gap - this item is about the normalizer only because
that is where the metric filter is, and the wider question belongs with it.

**A brand new environment cannot create the filter.** Terraform would try to
attach it to a group that does not exist until the normalizer has run once.
Applying twice fixes it, which is exactly the kind of thing that wastes an
afternoon when nobody has written it down.

## Done when

- The normalizer's log group is declared, imported, and carries a retention.
- The same question is answered for the other Lambda log groups: one
  retention, or a reason why they differ.
- `observability.tf`'s note about the fresh-environment case is removed,
  because it is no longer true.
