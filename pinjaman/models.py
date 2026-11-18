from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
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
        permissions = [
            ("setujui_pengajuan", "Boleh menyetujui atau menolak pengajuan"),
            ("cairkan_pinjaman", "Boleh mencairkan pinjaman"),
        ]

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

class JadwalAngsuran(models.Model):
    class Status(models.TextChoices):
        BELUM = "belum", "Belum dibayar"
        LUNAS = "lunas", "Lunas"

    pinjaman = models.ForeignKey(Pinjaman, on_delete=models.PROTECT, related_name="jadwal")
    angsuran_ke = models.PositiveSmallIntegerField()
    jatuh_tempo = models.DateField()
    pokok = models.DecimalField(max_digits=15, decimal_places=2)
    jasa = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BELUM)

    class Meta:
        verbose_name = "Jadwal angsuran"
        verbose_name_plural = "Jadwal angsuran"
        ordering = ["pinjaman_id", "angsuran_ke"]
        constraints = [
            models.UniqueConstraint(
                fields=["pinjaman", "angsuran_ke"], name="angsuran_unik_per_pinjaman"
            )
        ]

    @property
    def total(self):
        return self.pokok + self.jasa

    def __str__(self):
        return (
            f"{self.pinjaman.no_pinjaman} - angsuran ke-{self.angsuran_ke} "
            f"(jatuh tempo {self.jatuh_tempo:%d-%m-%Y})"
        )

class Pembayaran(models.Model):
    # OneToOne: satu angsuran hanya bisa dibayar sekali (dijaga di level database)
    jadwal = models.OneToOneField(
        JadwalAngsuran, on_delete=models.PROTECT, related_name="pembayaran"
    )
    tanggal_bayar = models.DateField(default=timezone.localdate)
    pokok = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal("0"))
    jasa = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal("0"))
    hari_telat = models.PositiveIntegerField(editable=False, default=0)
    denda = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal("0"))
    dicatat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", editable=False
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pembayaran angsuran"
        verbose_name_plural = "Pembayaran angsuran"
        ordering = ["-tanggal_bayar", "-id"]

    @property
    def total_dibayar(self):
        return self.pokok + self.jasa + self.denda

    def clean(self):
        if not self.jadwal_id or not self.tanggal_bayar:
            return
        jadwal = self.jadwal
        if jadwal.status == JadwalAngsuran.Status.LUNAS:
            raise ValidationError("Angsuran ini sudah dibayar.")
        ada_yang_belum = JadwalAngsuran.objects.filter(
            pinjaman=jadwal.pinjaman,
            angsuran_ke__lt=jadwal.angsuran_ke,
            status=JadwalAngsuran.Status.BELUM,
        ).exists()
        if ada_yang_belum:
            raise ValidationError("Angsuran sebelumnya belum dibayar. Pembayaran harus berurutan.")
        if self.tanggal_bayar < jadwal.pinjaman.tanggal_cair:
            raise ValidationError("Tanggal bayar tidak boleh sebelum tanggal pencairan.")
        if self.tanggal_bayar > timezone.localdate():
            raise ValidationError("Tanggal bayar tidak boleh di masa depan.")
        
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Pembayaran tidak boleh diubah. Koreksi dibuat sebagai transaksi baru.")
        from .services import hitung_denda, hitung_hari_telat

        # atomic + select_for_update: dua kasir tidak bisa membayar angsuran yang sama bersamaan
        with transaction.atomic():
            jadwal = (
                JadwalAngsuran.objects.select_for_update()
                .select_related("pinjaman")
                .get(pk=self.jadwal_id)
            )
            if jadwal.status == JadwalAngsuran.Status.LUNAS:
                raise ValidationError("Angsuran ini sudah dibayar.")
            pinjaman = jadwal.pinjaman

            self.pokok = jadwal.pokok
            self.jasa = jadwal.jasa
            self.hari_telat = hitung_hari_telat(jadwal.jatuh_tempo, self.tanggal_bayar)
            self.denda = hitung_denda(jadwal.total, pinjaman.denda_per_hari_persen, self.hari_telat)
            super().save(*args, **kwargs)

            jadwal.status = JadwalAngsuran.Status.LUNAS
            jadwal.save(update_fields=["status"])

            rincian = [
                (TransaksiKas.Kategori.ANGSURAN_POKOK, self.pokok),
                (TransaksiKas.Kategori.ANGSURAN_JASA, self.jasa),
                (TransaksiKas.Kategori.DENDA, self.denda),
            ]
            for kategori, jumlah in rincian:
                if jumlah > 0:
                    TransaksiKas.objects.create(
                        tanggal=self.tanggal_bayar,
                        jenis=TransaksiKas.Jenis.MASUK,
                        kategori=kategori,
                        jumlah=jumlah,
                        keterangan=f"{pinjaman.no_pinjaman} angsuran ke-{jadwal.angsuran_ke}",
                        pinjaman=pinjaman,
                        pembayaran=self,
                        dibuat_oleh=self.dicatat_oleh,
                    )

            # Semua angsuran sudah dibayar -> pinjaman lunas
            if not pinjaman.jadwal.filter(status=JadwalAngsuran.Status.BELUM).exists():
                pinjaman.status = Pinjaman.Status.LUNAS
                pinjaman.save(update_fields=["status"])

    def __str__(self):
        return f"Pembayaran {self.jadwal}"


class TransaksiKas(models.Model):
    class Jenis(models.TextChoices):
        MASUK = "masuk", "Kas masuk"
        KELUAR = "keluar", "Kas keluar"

    class Kategori(models.TextChoices):
        PENCAIRAN = "pencairan", "Pencairan pinjaman"
        BIAYA_ADMIN = "biaya_admin", "Biaya admin"
        ANGSURAN_POKOK = "angsuran_pokok", "Angsuran pokok"
        ANGSURAN_JASA = "angsuran_jasa", "Angsuran jasa (bunga)"
        DENDA = "denda", "Denda"
        LAINNYA = "lainnya", "Lainnya (input manual)"

    tanggal = models.DateField(default=timezone.localdate)
    jenis = models.CharField(max_length=10, choices=Jenis.choices)
    kategori = models.CharField(max_length=20, choices=Kategori.choices, default=Kategori.LAINNYA)
    jumlah = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    keterangan = models.CharField(max_length=200, blank=True)
    pinjaman = models.ForeignKey(
        Pinjaman, null=True, blank=True, on_delete=models.PROTECT, related_name="kas", editable=False
    )
    pembayaran = models.ForeignKey(
        Pembayaran, null=True, blank=True, on_delete=models.PROTECT, related_name="kas", editable=False
    )
    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+", editable=False
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transaksi kas"
        verbose_name_plural = "Transaksi kas"
        ordering = ["-tanggal", "-id"]

    def __str__(self):
        return f"{self.get_jenis_display()} {rupiah(self.jumlah)} - {self.get_kategori_display()}"