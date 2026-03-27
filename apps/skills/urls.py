from django.urls import path

from . import views

urlpatterns = [
    path("", views.skill_list, name="skill-list"),
    path("<int:pk>/", views.skill_detail, name="skill-detail"),
    path("<int:pk>/adapter/", views.generate_adapter, name="generate-adapter"),
]
