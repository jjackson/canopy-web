"""Social account adapter enforcing an email-domain allowlist."""
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import render


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        allowed_domain = (getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "") or "").lower()
        if not allowed_domain:
            return

        email = (sociallogin.account.extra_data.get("email") or "").lower()
        if not email.endswith(f"@{allowed_domain}"):
            response = render(
                request,
                "auth/domain_rejected.html",
                {"email": email, "allowed_domain": allowed_domain},
                status=403,
            )
            raise ImmediateHttpResponse(response)
