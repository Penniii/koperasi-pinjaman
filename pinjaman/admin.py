from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import JadwalAngsuran, JenisPinjaman, Pembayaran, Pinjaman, PengajuanPinjaman, TransaksiKas
from .services import buat_jadwal_angsuran, catat_kas_pencairan


@admin.register(JenisPinjaman)
class JenisPinjamanAdmin(admin.ModelAdmin):
    list_display = ("nama", "bunga_per_bulan", "biaya_admin_persen", "jumlah_minimal", "jumlah_maksimal", "aktif")


@admin.register(PengajuanPinjaman)
class PengajuanPinjamanAdmin(admin.ModelAdmin):
    list_display = ("id", "anggota", "jenis", "jumlah", "tenor_bulan", "tanggal_pengajuan", "status")
    list_filter = ("status", "jenis")
    search_fields = ("anggota__nama_lengkap", "anggota__no_anggota")
    autocomplete_fields = ("anggota",)
    readonly_fields = ("status", "diputuskan_oleh", "tanggal_keputusan")
    actions = ["setujui", "tolak", "cairkan"]

    @admin.action(description="Setujui pengajuan terpilih")
    def setujui(self, request, queryset):
        jumlah = queryset.filter(status=PengajuanPinjaman.Status.DIAJUKAN).update(
            status=PengajuanPinjaman.Status.DISETUJUI,
            diputuskan_oleh=request.user,
            tanggal_keputusan=timezone.localdate(),
        )
        self.message_user(request, f"{jumlah} pengajuan disetujui.", messages.SUCCESS)

    @admin.action(description="Tolak pengajuan terpilih")
    def tolak(self, request, queryset):
        jumlah = queryset.filter(status=PengajuanPinjaman.Status.DIAJUKAN).update(
            status=PengajuanPinjaman.Status.DITOLAK,
            diputuskan_oleh=request.user,
            tanggal_keputusan=timezone.localdate(),
        )
        self.message_user(request, f"{jumlah} pengajuan ditolak.", messages.SUCCESS)

    @admin.action(description="Cairkan pinjaman terpilih")
    def cairkan(self, request, queryset):
        jumlah = 0
        # atomic: kalau ada error di tengah jalan, semua perubahan dibatalkan
        with transaction.atomic():
            for pengajuan in queryset.filter(
                status=PengajuanPinjaman.Status.DISETUJUI
            ).select_for_update():
                jenis = pengajuan.jenis
                pinjaman = Pinjaman.objects.create(
                    pengajuan=pengajuan,
                    tanggal_cair=timezone.localdate(),
                    pokok=pengajuan.jumlah,
                    tenor_bulan=pengajuan.tenor_bulan,
                    bunga_per_bulan=jenis.bunga_per_bulan,
                    biaya_admin=(
                        pengajuan.jumlah * jenis.biaya_admin_persen / Decimal("100")
                    ).quantize(Decimal("0.01")),
                    denda_per_hari_persen=jenis.denda_per_hari_persen,
                    dicairkan_oleh=request.user,
                )
                buat_jadwal_angsuran(pinjaman)
                buat_jadwal_angsuran(pinjaman)
                catat_kas_pencairan(pinjaman, request.user)
                pengajuan.status = PengajuanPinjaman.Status.DICAIRKAN
                pengajuan.save(update_fields=["status"])
                jumlah += 1
        self.message_user(request, f"{jumlah} pinjaman dicairkan.", messages.SUCCESS)


class JadwalAngsuranInline(admin.TabularInline):
    model = JadwalAngsuran
    extra = 0
    fields = ("angsuran_ke", "jatuh_tempo", "pokok", "jasa", "total", "status")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pinjaman)
class PinjamanAdmin(admin.ModelAdmin):
    list_display = ("no_pinjaman", "pengajuan", "tanggal_cair", "pokok", "tenor_bulan", "status")
    list_filter = ("status",)
    search_fields = ("no_pinjaman", "pengajuan__anggota__nama_lengkap")
    inlines = [JadwalAngsuranInline]

    # Pinjaman hanya lahir lewat aksi "Cairkan" dan tidak boleh diedit/dihapus manual
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(JadwalAngsuran)
class JadwalAngsuranAdmin(admin.ModelAdmin):
    list_display = ("pinjaman", "angsuran_ke", "jatuh_tempo", "pokok", "jasa", "status")
    list_filter = ("status", "jatuh_tempo")
    search_fields = ("pinjaman__no_pinjaman", "pinjaman__pengajuan__anggota__nama_lengkap")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pembayaran)
class PembayaranAdmin(admin.ModelAdmin):
    list_display = ("id", "jadwal", "tanggal_bayar", "pokok", "jasa", "hari_telat", "denda", "total_dibayar")
    search_fields = ("jadwal__pinjaman__no_pinjaman", "jadwal__pinjaman__pengajuan__anggota__nama_lengkap")
    autocomplete_fields = ("jadwal",)
    readonly_fields = ("pokok", "jasa", "hari_telat", "denda", "dicatat_oleh")

    def get_fields(self, request, obj=None):
        if obj:
            return ("jadwal", "tanggal_bayar", "pokok", "jasa", "hari_telat", "denda", "dicatat_oleh")
        return ("jadwal", "tanggal_bayar")  # kasir cukup isi dua kolom ini

    def save_model(self, request, obj, form, change):
        obj.dicatat_oleh = request.user
        super().save_model(request, obj, form, change)

    # Pembayaran yang sudah tercatat tidak boleh diubah atau dihapus
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransaksiKas)
class TransaksiKasAdmin(admin.ModelAdmin):
    list_display = ("tanggal", "jenis", "kategori", "jumlah", "keterangan")
    list_filter = ("jenis", "kategori")
    search_fields = ("keterangan",)
    date_hierarchy = "tanggal"

    def save_model(self, request, obj, form, change):
        obj.dibuat_oleh = request.user
        super().save_model(request, obj, form, change)

    # Buku kas hanya boleh bertambah. Kesalahan dikoreksi dengan transaksi baru.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False