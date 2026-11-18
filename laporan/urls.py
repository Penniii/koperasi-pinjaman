from django.urls import path

from . import views

app_name = "laporan"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tunggakan/", views.tunggakan, name="tunggakan"),
    path("kas/", views.laporan_kas, name="kas"),
]