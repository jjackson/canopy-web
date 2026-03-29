"""
Project-level views for canopy-web.
"""
from django.http import JsonResponse


def health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({"status": "ok"})
