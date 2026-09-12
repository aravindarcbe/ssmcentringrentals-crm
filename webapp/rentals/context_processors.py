from django.conf import settings


def branding(request):
    google_app = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {})
    return {
        "company_name": settings.COMPANY_NAME,
        "google_sso_configured": bool(google_app.get("client_id") and google_app.get("secret")),
    }
