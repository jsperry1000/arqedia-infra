# ---------------------------------------------------------------------------
# GitHub Actions deployment role.
# GitHub authenticates directly to AWS via OIDC. No stored access keys.
# The trust policy restricts this to jsperry1000/arqedia-infra only.
# ---------------------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = { Name = "${local.name_prefix}-github-oidc" }
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:jsperry1000/arqedia-infra:*",
        "repo:jsperry1000@*/arqedia-infra@*:*",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${local.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json

  tags = { Name = "${local.name_prefix}-github-deploy" }
}

# Two surfaces, one role: the application in frontend.tf and the marketing
# site in site.tf. Both deploy from the same repository through the same OIDC
# trust, so they share a role rather than duplicating the federation.
data "aws_iam_policy_document" "github_deploy" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.frontend.arn,
      "${aws_s3_bucket.frontend.arn}/*",
      aws_s3_bucket.site.arn,
      "${aws_s3_bucket.site.arn}/*",
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["cloudfront:CreateInvalidation"]
    resources = [
      aws_cloudfront_distribution.frontend.arn,
      aws_cloudfront_distribution.site.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

# --- the staff console's own role ------------------------------------------
#
# A SECOND ROLE RATHER THAN TWO MORE RESOURCES ON THE FIRST. The role above
# is held by the workflows that publish the application and the marketing
# site, and adding the admin bucket to it would give those two the ability to
# overwrite the staff console. Group 16's rule is that the console shares
# nothing with the customer path; a deploy role is exactly the kind of thing
# that gets shared because it already exists.
#
# ITS TRUST IS NARROWER THAN THE OTHER ROLE'S, and deliberately the only one
# in this stack that is. github_assume above trusts any ref in the
# repository, which is right for the two customer surfaces: a branch that
# publishes the marketing site early is a mess, not a breach. This role can
# write the console that reads every tenant, so it is trusted from main and
# from nothing else - not a branch, not a tag, not a pull request.
#
# THE SUBJECT CLAIM HAS TWO FORMATS AND THIS REPOSITORY USES THE SECOND.
# Checked against GitHub's OIDC reference rather than remembered:
#
#   repo:OWNER/REPO:ref:refs/heads/main                  before 15 July 2026
#   repo:OWNER@<owner id>/REPO@<repo id>:ref:refs/heads/main   after it
#
# "The @ separator is used between names and IDs because @ cannot appear in
# GitHub usernames or repository names." A repository created after 15 July
# 2026 gets the immutable format by default; one created before it keeps the
# old format unless an administrator opts in. jsperry1000/arqedia-infra was
# created on 26 August 2026 - api.github.com/repos/jsperry1000/arqedia-infra,
# owner id 278752205, repository id 1347589209 - so the SECOND line is the
# one matching today and the first is there for a repository that is ever
# recreated or restored under the old format.
#
# The ids are written out rather than wildcarded, unlike github_assume's
# "repo:jsperry1000@*/arqedia-infra@*:*". An id is never reassigned, which is
# the whole point of the immutable format; a wildcard would trust any future
# repository that happened to be called arqedia-infra under any account
# called jsperry1000.
#
# StringEquals, not StringLike: there is no wildcard left to match.
#
# THE COST, ACCEPTED: a manual run of deploy-admin.yml from a branch other
# than main cannot assume this role. Dispatching it from main still can.
data "aws_iam_policy_document" "github_assume_admin" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:jsperry1000/arqedia-infra:ref:refs/heads/main",
        "repo:jsperry1000@278752205/arqedia-infra@1347589209:ref:refs/heads/main",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy_admin" {
  name               = "${local.name_prefix}-github-deploy-admin"
  assume_role_policy = data.aws_iam_policy_document.github_assume_admin.json

  tags = { Name = "${local.name_prefix}-github-deploy-admin" }
}

data "aws_iam_policy_document" "github_deploy_admin" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.admin.arn,
      "${aws_s3_bucket.admin.arn}/*",
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.admin.arn]
  }
}

resource "aws_iam_role_policy" "github_deploy_admin" {
  name   = "${local.name_prefix}-github-deploy-admin"
  role   = aws_iam_role.github_deploy_admin.id
  policy = data.aws_iam_policy_document.github_deploy_admin.json
}

output "github_deploy_admin_role_arn" {
  value = aws_iam_role.github_deploy_admin.arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}
