from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from anggota.models import Anggota


def rupiah(nilai):
    return "Rp" + f"{nilai:,.0f}".replace(",", ".")


class JenisPinjaman(models.Model):
    nama = models.CharField(max_length=100, unique=True)
    bunga_per_bulan = models.DecimalField(
        "Bunga flat per bulan (%)", max_digits=5, decimal_places=2, default=Decimal("1.50")
    )
    biaya_admin_persen = models.DecimalField(
        "Biaya admin (%)", max_digits=5, decimal_places=2, default=Decimal("1.00")
    )
    denda_per_hari_persen = models.DecimalField(
        "Denda per hari (%)", max_digits=5, decimal_places=2, default=Decimal("0.10")
    )
    jumlah_minimal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("1000000"))
    jumlah_maksimal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("20000000"))
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Jenis pinjaman"
        verbose_name_plural = "Jenis pinjaman"

    def __str__(self):
        return self.nama


class PengajuanPinjaman(models.Model):
    class Status(models.TextChoices):
        DIAJUKAN = "diajukan", "Diajukan"
        DISETUJUI = "disetujui", "Disetujui"
        DITOLAK = "ditolak", "Ditolak"
        DICAIRKAN = "dicairkan", "Dicairkan"

    TENOR_CHOICES = [(6, "6 bulan"), (12, "12 bulan"), (24, "24 bulan")]

    anggota = models.ForeignKey(Anggota, on_delete=models.PROTECT, related_name="pengajuan")
    jenis = models.ForeignKey(JenisPinjaman, on_delete=models.PROTECT)
    jumlah = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("1"))]
    )
    tenor_bulan = models.PositiveSmallIntegerField(choices=TENOR_CHOICES)
    tujuan = models.CharField(max_length=200)
    tanggal_pengajuan = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DIAJUKAN, editable=False
    )
    diputuskan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", editable=False,
    )
    tanggal_keputusan = models.DateField(null=True, blank=True, editable=False)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pengajuan pinjaman"
        verbose_name_plural = "Pengajuan pinjaman"
        ordering = ["-dibuat_pada"]

    def clean(self):
        if self.anggota_id and self.anggota.status != Anggota.Status.AKTIF:
            raise ValidationError("Anggota yang tidak aktif tidak dapat mengajukan pinjaman.")
        if self.jenis_id and self.jumlah is not None:
            if not (self.jenis.jumlah_minimal <= self.jumlah <= self.jenis.jumlah_maksimal):
                raise ValidationError(
                    f"Jumlah pinjaman harus antara {rupiah(self.jenis.jumlah_minimal)} "
                    f"dan {rupiah(self.jenis.jumlah_maksimal)}."
                )

    def __str__(self):
        return f"Pengajuan #{self.pk} - {self.anggota.nama_lengkap}"


class Pinjaman(models.Model):
    class Status(models.TextChoices):
        BERJALAN = "berjalan", "Berjalan"
        LUNAS = "lunas", "Lunas"

    pengajuan = models.OneToOneField(
        PengajuanPinjaman, on_delete=models.PROTECT, related_name="pinjaman"
    )
    no_pinjaman = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    tanggal_cair = models.DateField()
    pokok = models.DecimalField(max_digits=15, decimal_places=2)
    tenor_bulan = models.PositiveSmallIntegerField()
    # Aturan disalin saat pencairan, supaya perubahan aturan nanti tidak mengubah pinjaman lama
    bunga_per_bulan = models.DecimalField(max_digits=5, decimal_places=2)
    biaya_admin = models.DecimalField(max_digits=15, decimal_places=2)
    denda_per_hari_persen = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BERJALAN)
    dicairkan_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "Pinjaman"
        verbose_name_plural = "Pinjaman"
        ordering = ["-tanggal_cair", "-id"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.no_pinjaman:
            self.no_pinjaman = f"PJM-{self.pk:04d}"
            super().save(update_fields=["no_pinjaman"])

    def __str__(self):
        return f"{self.no_pinjaman} - {self.pengajuan.anggota.nama_lengkap}"