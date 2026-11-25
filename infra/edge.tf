# Certificates, CloudFront and WAF. DNS for hamerappliedai.com stays at
# Squarespace, so the validation and site records are added there by hand: they
# come out as outputs (dns_records_*). First apply only the certificates
# (see docs/deploy-plan.md, step 3), add the validation records, then apply
# the rest; the *_validation resources wait for ACM to see the records.

# --- certificates ---

resource "aws_acm_certificate" "site" {
  provider          = aws.us_east_1 # CloudFront only uses certificates in us-east-1
  domain_name       = var.domain_name
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "origin" {
  domain_name       = var.origin_domain_name
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "site" {
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site.arn
  timeouts {
    create = "2h"
  }
}

resource "aws_acm_certificate_validation" "origin" {
  certificate_arn = aws_acm_certificate.origin.arn
  timeouts {
    create = "2h"
  }
}

# --- WAF (on CloudFront, so us-east-1) ---

resource "aws_wafv2_web_acl" "main" {
  provider    = aws.us_east_1
  name        = local.name
  scope       = "CLOUDFRONT"
  description = "baseball_gpt edge rules"

  default_action {
    allow {}
  }

  rule {
    name     = "ip-reputation"
    priority = 0
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # Login and Ask AI: a tight per-IP limit before the app's own limits.
  rule {
    name     = "rate-sensitive"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit_sensitive
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"
        scope_down_statement {
          or_statement {
            statement {
              byte_match_statement {
                search_string         = "/api/auth/login"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }
            statement {
              byte_match_statement {
                search_string         = "/api/chat"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-sensitive"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "rate-all"
    priority = 2
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit_all
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-all"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "known-bad-inputs"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # The common rule set, except on /api/chat: chat bodies carry the whole
  # conversation (often over the 8 KB body rule, and full of tables and code
  # that look like XSS to it). The app validates chat input itself.
  rule {
    name     = "common"
    priority = 4
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
        scope_down_statement {
          not_statement {
            statement {
              byte_match_statement {
                search_string         = "/api/chat"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = local.name
    sampled_requests_enabled   = true
  }
}

# --- CloudFront ---

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Caches only what the app marks cacheable (browse API: public, max-age=3600);
# index.html and anything without Cache-Control pass through.
data "aws_cloudfront_cache_policy" "origin_headers" {
  name = "UseOriginCacheControlHeaders-QueryStrings"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

# What reaches the app: cookies (sign-in), query strings, and the visitor's
# address. Not the Host header: CloudFront would then check the load
# balancer's certificate against the site name instead of the origin name.
resource "aws_cloudfront_origin_request_policy" "app" {
  name = "${local.name}-app"
  cookies_config {
    cookie_behavior = "all"
  }
  query_strings_config {
    query_string_behavior = "all"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["CloudFront-Viewer-Address", "Origin", "Accept", "Accept-Language", "Referer", "User-Agent"]
    }
  }
}

resource "aws_cloudfront_distribution" "main" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  comment         = "baseball_gpt"
  aliases         = [var.domain_name]
  price_class     = "PriceClass_100" # North America and Europe edges
  web_acl_id      = aws_wafv2_web_acl.main.arn

  origin {
    origin_id   = "alb"
    domain_name = var.origin_domain_name
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }
  }

  default_cache_behavior {
    target_origin_id           = "alb"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.origin_headers.id
    origin_request_policy_id   = aws_cloudfront_origin_request_policy.app.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  # Built assets have content hashes in their names: cache hard.
  ordered_cache_behavior {
    path_pattern               = "/assets/*"
    target_origin_id           = "alb"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  # Sign-in and Ask AI: never cached, every method allowed.
  dynamic "ordered_cache_behavior" {
    for_each = ["/api/auth/*", "/api/chat"]
    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = "alb"
      viewer_protocol_policy     = "https-only"
      allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = false # don't buffer the answer stream
      cache_policy_id            = data.aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id   = aws_cloudfront_origin_request_policy.app.id
      response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
