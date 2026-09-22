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
# The trust is the same federation - the same repository, through the same
# OIDC provider. Narrowing it further, to one workflow or one branch, is a
# real option and is not done here: it would be the first place in this stack
# to do it, and doing it for one role and not the others is a decision rather
# than a tidy-up.
resource "aws_iam_role" "github_deploy_admin" {
  name               = "${local.name_prefix}-github-deploy-admin"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json

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
