"""Social account adapter enforcing an email-domain allowlist."""
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import render

from .auth_domains import allowed_email_domains, email_in_allowlist


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.account.extra_data.get("email") or "").lower()
        if email_in_allowlist(email):
            return

        allowed = ", ".join(allowed_email_domains())
        response = render(
            request,
            "auth/domain_rejected.html",
            {"email": email, "allowed_domain": allowed},
            status=403,
        )
        raise ImmediateHttpResponse(response)
