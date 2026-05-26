from django.urls import path

from . import views

urlpatterns = [
    path("", views.walkthroughs_list_or_create, name="walkthroughs-list-or-create"),
]
