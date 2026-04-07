from django.urls import path
from . import views

urlpatterns = [
    path("status/", views.ai_status, name="ai-status"),
    path("switch/", views.ai_switch, name="ai-switch"),
    path("auth/start/", views.auth_start, name="auth-start"),
    path("auth/complete/", views.auth_complete, name="auth-complete"),
    path("auth/poll/", views.auth_poll, name="auth-poll"),
]
