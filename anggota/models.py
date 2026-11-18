from django.core.validators import RegexValidator
from django.db import models


class Anggota(models.Model):
    class Status(models.TextChoices):
        AKTIF = "aktif", "Aktif"
        NONAKTIF = "nonaktif", "Nonaktif"

    no_anggota = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    nama_lengkap = models.CharField(max_length=100)
    nik = models.CharField(
        "NIK",
        max_length=16,
        unique=True,
        validators=[RegexValidator(r"^\d{16}$", "NIK harus 16 digit angka.")],
    )
    no_hp = models.CharField("No. HP", max_length=20)
    alamat = models.TextField()
    pekerjaan = models.CharField(max_length=100, blank=True)
    tanggal_bergabung = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AKTIF)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anggota"
        verbose_name_plural = "Anggota"
        ordering = ["no_anggota"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Nomor anggota dibuat otomatis setelah data pertama kali tersimpan
        if not self.no_anggota:
            self.no_anggota = f"AGT-{self.pk:04d}"
            super().save(update_fields=["no_anggota"])

    def __str__(self):
        return f"{self.no_anggota} - {self.nama_lengkap}"