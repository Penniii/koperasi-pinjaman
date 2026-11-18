from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from laporan.templatetags.rupiah import rupiah

from .models import JadwalAngsuran, JenisPinjaman, Pembayaran, Pinjaman, PengajuanPinjaman, TransaksiKas
from .services import buat_jadwal_angsuran, catat_kas_pencairan

admin.site.site_header = "Koperasi Pinjaman"
admin.site.site_title = "Koperasi Pinjaman"
admin.site.index_title = "Panel Pengelola"


def kolom_rupiah(nama_field, judul):
    """Membuat kolom admin berformat Rupiah yang tetap bisa diurutkan."""

    @admin.display(description=judul, ordering=nama_field)
    def kolom(self, obj):
        return rupiah(getattr(obj, nama_field))

    return kolom


@admin.register(JenisPinjaman)
class JenisPinjamanAdmin(admin.ModelAdmin):
    list_display = (
        "nama", "bunga_per_bulan", "biaya_admin_persen", "denda_per_hari_persen",
        "minimal_rp", "maksimal_rp", "aktif",
    )
    minimal_rp = kolom_rupiah("jumlah_minimal", "Jumlah minimal")
    maksimal_rp = kolom_rupiah("jumlah_maksimal", "Jumlah maksimal")


@admin.register(PengajuanPinjaman)
class PengajuanPinjamanAdmin(admin.ModelAdmin):
    list_display = ("id", "anggota", "jenis", "jumlah_rp", "tenor_bulan", "tanggal_pengajuan", "status")
    list_filter = ("status", "jenis")
    search_fields = ("anggota__nama_lengkap", "anggota__no_anggota")
    autocomplete_fields = ("anggota",)
    readonly_fields = ("status", "diputuskan_oleh", "tanggal_keputusan")
    actions = ["setujui", "tolak", "cairkan"]
    jumlah_rp = kolom_rupiah("jumlah", "Jumlah")

    # Aksi hanya muncul untuk peran yang punya izinnya
    def has_setujui_permission(self, request):
        return request.user.has_perm("pinjaman.setujui_pengajuan")

    def has_cairkan_permission(self, request):
        return request.user.has_perm("pinjaman.cairkan_pinjaman")

    @admin.action(description="Setujui pengajuan terpilih", permissions=["setujui"])
    def setujui(self, request, queryset):
        jumlah = queryset.filter(status=PengajuanPinjaman.Status.DIAJUKAN).update(
            status=PengajuanPinjaman.Status.DISETUJUI,
            diputuskan_oleh=request.user,
            tanggal_keputusan=timezone.localdate(),
        )
        self.message_user(request, f"{jumlah} pengajuan disetujui.", messages.SUCCESS)

    @admin.action(description="Tolak pengajuan terpilih", permissions=["setujui"])
    def tolak(self, request, queryset):
        jumlah = queryset.filter(status=PengajuanPinjaman.Status.DIAJUKAN).update(
            status=PengajuanPinjaman.Status.DITOLAK,
            diputuskan_oleh=request.user,
            tanggal_keputusan=timezone.localdate(),
        )
        self.message_user(request, f"{jumlah} pengajuan ditolak.", messages.SUCCESS)

    @admin.action(description="Cairkan pinjaman terpilih", permissions=["cairkan"])
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
                catat_kas_pencairan(pinjaman, request.user)
                pengajuan.status = PengajuanPinjaman.Status.DICAIRKAN
                pengajuan.save(update_fields=["status"])
                jumlah += 1
        self.message_user(request, f"{jumlah} pinjaman dicairkan.", messages.SUCCESS)


class JadwalAngsuranInline(admin.TabularInline):
    model = JadwalAngsuran
    extra = 0
    fields = ("angsuran_ke", "jatuh_tempo", "pokok_rp", "jasa_rp", "total_rp", "status")
    readonly_fields = fields
    can_delete = False
    pokok_rp = kolom_rupiah("pokok", "Pokok")
    jasa_rp = kolom_rupiah("jasa", "Jasa")

    @admin.display(description="Total")
    def total_rp(self, obj):
        return rupiah(obj.total)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pinjaman)
class PinjamanAdmin(admin.ModelAdmin):
    list_display = ("no_pinjaman", "pengajuan", "tanggal_cair", "pokok_rp", "tenor_bulan", "status")
    list_filter = ("status",)
    search_fields = ("no_pinjaman", "pengajuan__anggota__nama_lengkap")
    inlines = [JadwalAngsuranInline]
    pokok_rp = kolom_rupiah("pokok", "Pokok")

    # Pinjaman hanya lahir lewat aksi "Cairkan" dan tidak boleh diedit/dihapus manual
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JadwalAngsuran)
class JadwalAngsuranAdmin(admin.ModelAdmin):
    list_display = ("pinjaman", "angsuran_ke", "jatuh_tempo", "pokok_rp", "jasa_rp", "status")
    list_filter = ("status", "jatuh_tempo")
    search_fields = ("pinjaman__no_pinjaman", "pinjaman__pengajuan__anggota__nama_lengkap")
    pokok_rp = kolom_rupiah("pokok", "Pokok")
    jasa_rp = kolom_rupiah("jasa", "Jasa")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pembayaran)
class PembayaranAdmin(admin.ModelAdmin):
    list_display = ("id", "jadwal", "tanggal_bayar", "pokok_rp", "jasa_rp", "hari_telat", "denda_rp", "total_rp")
    search_fields = ("jadwal__pinjaman__no_pinjaman", "jadwal__pinjaman__pengajuan__anggota__nama_lengkap")
    autocomplete_fields = ("jadwal",)
    readonly_fields = ("pokok", "jasa", "hari_telat", "denda", "dicatat_oleh")
    pokok_rp = kolom_rupiah("pokok", "Pokok")
    jasa_rp = kolom_rupiah("jasa", "Jasa")
    denda_rp = kolom_rupiah("denda", "Denda")

    @admin.display(description="Total dibayar")
    def total_rp(self, obj):
        return rupiah(obj.total_dibayar)

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
    list_display = ("tanggal", "jenis", "kategori", "jumlah_rp", "keterangan")
    list_filter = ("jenis", "kategori")
    search_fields = ("keterangan",)
    date_hierarchy = "tanggal"
    jumlah_rp = kolom_rupiah("jumlah", "Jumlah")

    def save_model(self, request, obj, form, change):
        obj.dibuat_oleh = request.user
        super().save_model(request, obj, form, change)

    # Buku kas hanya boleh bertambah. Kesalahan dikoreksi dengan transaksi baru.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False