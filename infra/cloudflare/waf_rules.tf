###############################################################################
# Hireloop — Cloudflare WAF rules
# India geo-lock layer 2: block non-IN ASN at WAF level
###############################################################################

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

variable "cloudflare_zone_id"    { type = string }
variable "cloudflare_account_id" { type = string }
variable "cloudflare_api_token"  { type = string; sensitive = true }

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ── WAF Custom Ruleset ────────────────────────────────────────────────────────

resource "cloudflare_ruleset" "india_geo_lock" {
  zone_id     = var.cloudflare_zone_id
  name        = "Hireloop India Geo-Lock"
  description = "Block all traffic originating outside India"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "Block non-India traffic (geo-lock layer 2)"
    enabled     = true

    # Block if country is NOT India
    # ip.geoip.country gives the 2-letter ISO country code
    expression = "(not ip.geoip.country eq \"IN\")"

    action_parameters {
      response {
        status_code  = 403
        content_type = "application/json"
        content      = "{\"detail\":\"This service is available in India only.\"}"
      }
    }
  }

  rules {
    action      = "block"
    description = "Block known bad bots and scrapers"
    enabled     = true
    expression  = "(cf.client.bot) and (not cf.verified_bot_category in {\"search_engine\" \"monitor\" \"aggregator\"})"
  }

  rules {
    action      = "challenge"
    description = "Challenge suspicious user agents"
    enabled     = true
    expression  = "(http.user_agent contains \"curl\" and not ip.geoip.country eq \"IN\")"
  }
}

# ── Rate limiting ──────────────────────────────────────────────────────────────

resource "cloudflare_ruleset" "rate_limits" {
  zone_id     = var.cloudflare_zone_id
  name        = "Hireloop Rate Limits"
  description = "Rate limiting rules for API endpoints"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Auth endpoints — stricter limits to prevent brute force
  rules {
    action      = "block"
    description = "Rate limit auth endpoints"
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/api/v1/auth\")"

    ratelimit {
      characteristics    = ["cf.colo.id", "ip.src"]
      period             = 60
      requests_per_period = 10
      mitigation_timeout = 300
    }
  }

  # General API — protect against abuse
  rules {
    action      = "block"
    description = "Rate limit general API"
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/api/v1\")"

    ratelimit {
      characteristics    = ["cf.colo.id", "ip.src"]
      period             = 60
      requests_per_period = 200
      mitigation_timeout = 60
    }
  }
}

# ── Security headers (via Transform Rules) ───────────────────────────────────

resource "cloudflare_ruleset" "security_headers" {
  zone_id     = var.cloudflare_zone_id
  name        = "Hireloop Security Headers"
  description = "Add security headers to all responses"
  kind        = "zone"
  phase       = "http_response_headers_transform"

  rules {
    action      = "rewrite"
    description = "Add HSTS and security headers"
    enabled     = true
    expression  = "true"

    action_parameters {
      headers {
        name      = "Strict-Transport-Security"
        operation = "set"
        value     = "max-age=31536000; includeSubDomains; preload"
      }
      headers {
        name      = "X-Content-Type-Options"
        operation = "set"
        value     = "nosniff"
      }
      headers {
        name      = "X-Frame-Options"
        operation = "set"
        value     = "DENY"
      }
    }
  }
}
