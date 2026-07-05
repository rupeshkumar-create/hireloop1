from hireloop_api.config import Settings


def test_production_resolves_localhost_public_api_url_via_app_proxy() -> None:
    s = Settings(
        environment="production",
        secret_key="x" * 32,
        service_secret="y" * 32,
        public_api_url="http://localhost:8000",
        public_app_url="https://hireloop1-app.vercel.app",
    )
    assert s.public_api_url == "https://hireloop1-app.vercel.app/hireloop-api"
    assert (
        s.gmail_oauth_redirect_uri
        == "https://hireloop1-app.vercel.app/hireloop-api/api/v1/gmail/callback"
    )


def test_development_keeps_localhost_public_api_url() -> None:
    s = Settings(
        environment="development",
        public_api_url="http://localhost:8000",
        public_app_url="http://localhost:3001",
    )
    assert s.public_api_url == "http://localhost:8000"
    assert s.gmail_oauth_redirect_uri == "http://localhost:8000/api/v1/gmail/callback"
