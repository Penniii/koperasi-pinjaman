from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "laporan"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tunggakan/", views.tunggakan, name="tunggakan"),
    path("kas/", views.laporan_kas, name="kas"),
    path("masuk/", auth_views.LoginView.as_view(template_name="laporan/masuk.html"), name="masuk"),
    path("keluar/", auth_views.LogoutView.as_view(next_page="laporan:masuk"), name="keluar"),
]