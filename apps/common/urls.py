from django.urls import path
from . import views

urlpatterns = [
    path("status/", views.ai_status, name="ai-status"),
    path("login/", views.ai_login, name="ai-login"),
    path("login/code/", views.ai_login_code, name="ai-login-code"),
]
