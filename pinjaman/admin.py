from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import JadwalAngsuran, JenisPinjaman, Pinjaman, PengajuanPinjaman
from .services import buat_jadwal_angsuran


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