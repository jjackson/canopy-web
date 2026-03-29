from django.urls import path

from . import views

urlpatterns = [
    path("", views.collection_list, name="collection-list"),
    path("<int:pk>/", views.collection_detail, name="collection-detail"),
    path("<int:pk>/sources/", views.add_source, name="add-source"),
]
