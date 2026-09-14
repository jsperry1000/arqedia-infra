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

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}
