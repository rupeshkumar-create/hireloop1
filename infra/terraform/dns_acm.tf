###############################################################################
# Hireloop — Route53 + ACM + Cloudflare DNS
# Domains: hireloop.in (web) + api.hireloop.in (API) + app.hireloop.in (app)
###############################################################################

# ACM certificate for API subdomain (ALB termination)
resource "aws_acm_certificate" "api" {
  domain_name               = "api.hireloop.in"
  subject_alternative_names = ["*.hireloop.in"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation records — added to Cloudflare
resource "cloudflare_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  type    = each.value.type
  value   = each.value.value
  ttl     = 60
  proxied = false  # Must be DNS-only for ACM validation
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for record in cloudflare_record.acm_validation : record.hostname]
}

# Cloudflare DNS — api.hireloop.in → ALB (proxied for WAF protection)
resource "cloudflare_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  type    = "CNAME"
  value   = aws_lb.main.dns_name
  proxied = true  # Cloudflare proxy ON — WAF + DDoS protection active
  ttl     = 1     # Auto when proxied
}

# Cloudflare DNS — app.hireloop.in → Vercel (proxied)
resource "cloudflare_record" "app" {
  zone_id = var.cloudflare_zone_id
  name    = "app"
  type    = "CNAME"
  value   = "cname.vercel-dns.com"
  proxied = true
  ttl     = 1
}

# Cloudflare DNS — hireloop.in → Vercel (marketing site, proxied)
resource "cloudflare_record" "root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  type    = "CNAME"
  value   = "cname.vercel-dns.com"
  proxied = true
  ttl     = 1
}

resource "cloudflare_record" "www" {
  zone_id = var.cloudflare_zone_id
  name    = "www"
  type    = "CNAME"
  value   = "cname.vercel-dns.com"
  proxied = true
  ttl     = 1
}
