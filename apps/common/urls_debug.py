from django.urls import path

from . import views_debug

urlpatterns = [
    path("mint-session/", views_debug.mint_session, name="debug-mint-session"),
]
