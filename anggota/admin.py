from django.contrib import admin

from .models import Anggota


@admin.register(Anggota)
class AnggotaAdmin(admin.ModelAdmin):
    list_display = ("no_anggota", "nama_lengkap", "no_hp", "tanggal_bergabung", "status")
    search_fields = ("no_anggota", "nama_lengkap", "nik")
    list_filter = ("status",)