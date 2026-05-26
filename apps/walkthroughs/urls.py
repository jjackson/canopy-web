from django.urls import path

from . import views

urlpatterns = [
    path("", views.walkthroughs_list_or_create, name="walkthroughs-list-or-create"),
    path("<uuid:wid>/", views.walkthrough_detail, name="walkthrough-detail"),
    path("<uuid:wid>/rotate-token/", views.walkthrough_rotate_token, name="walkthrough-rotate-token"),
]
