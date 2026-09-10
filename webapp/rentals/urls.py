from django.urls import path

from . import views

app_name = "rentals"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
