from django.conf import settings


def branding(request):
    return {"company_name": settings.COMPANY_NAME}
