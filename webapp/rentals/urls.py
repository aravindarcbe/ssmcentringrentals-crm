from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("manage/", views.manage_home, name="manage"),
    path("rentals/new/", views.rental_new, name="rental_new"),
    path("rentals/<int:pk>/", views.rental_detail, name="rental_detail"),
    path("rentals/<int:pk>/return/", views.rental_return, name="rental_return"),
    path("search/", views.global_search, name="search"),
]
