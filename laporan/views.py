from datetime import date, timedelta
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F, Sum
from django.shortcuts import render
from django.utils import timezone

from anggota.models import Anggota
from pinjaman.models import JadwalAngsuran, PengajuanPinjaman, Pinjaman, TransaksiKas
from pinjaman.services import hitung_denda, hitung_hari_telat, kolektibilitas

NOL = Decimal("0")


def _jumlah(queryset, ekspresi):
    return queryset.aggregate(total=Sum(ekspresi))["total"] or NOL


def _tanggal(teks, bawaan):
    try:
        return date.fromisoformat(teks)
    except (TypeError, ValueError):
        return bawaan


@staff_member_required
def dashboard(request):
    hari_ini = timezone.localdate()
    belum_bayar = JadwalAngsuran.objects.filter(status=JadwalAngsuran.Status.BELUM)
    menunggak = belum_bayar.filter(jatuh_tempo__lt=hari_ini)

    kas_sampai_hari_ini = TransaksiKas.objects.filter(tanggal__lte=hari_ini)
    kas_masuk = _jumlah(kas_sampai_hari_ini.filter(jenis=TransaksiKas.Jenis.MASUK), "jumlah")
    kas_keluar = _jumlah(kas_sampai_hari_ini.filter(jenis=TransaksiKas.Jenis.KELUAR), "jumlah")

    konteks = {
        "halaman": "dashboard",
        "saldo_kas": kas_masuk - kas_keluar,
        "sisa_pokok": _jumlah(belum_bayar, "pokok"),
        "pinjaman_berjalan": Pinjaman.objects.filter(status=Pinjaman.Status.BERJALAN).count(),
        "anggota_aktif": Anggota.objects.filter(status=Anggota.Status.AKTIF).count(),
        "menunggu_keputusan": PengajuanPinjaman.objects.filter(
            status=PengajuanPinjaman.Status.DIAJUKAN
        ).count(),
        "siap_cair": PengajuanPinjaman.objects.filter(
            status=PengajuanPinjaman.Status.DISETUJUI
        ).count(),
        "tunggakan_jumlah": menunggak.count(),
        "tunggakan_total": _jumlah(menunggak, F("pokok") + F("jasa")),
        "jatuh_tempo": belum_bayar.filter(
            jatuh_tempo__range=(hari_ini, hari_ini + timedelta(days=7))
        )
        .select_related("pinjaman__pengajuan__anggota")
        .order_by("jatuh_tempo", "pinjaman_id"),
    }
    return render(request, "laporan/dashboard.html", konteks)


@staff_member_required
def tunggakan(request):
    hari_ini = timezone.localdate()
    jadwal = JadwalAngsuran.objects.filter(
        status=JadwalAngsuran.Status.BELUM, jatuh_tempo__lt=hari_ini
    ).select_related("pinjaman__pengajuan__anggota")

    baris = []
    total_tagihan = NOL
    for j in jadwal:
        hari = hitung_hari_telat(j.jatuh_tempo, hari_ini)
        denda = hitung_denda(j.total, j.pinjaman.denda_per_hari_persen, hari)
        tagihan = j.total + denda
        total_tagihan += tagihan
        baris.append(
            {
                "jadwal": j,
                "hari_telat": hari,
                "kolektibilitas": kolektibilitas(hari),
                "denda": denda,
                "tagihan": tagihan,
            }
        )
    baris.sort(key=lambda b: b["hari_telat"], reverse=True)

    return render(
        request,
        "laporan/tunggakan.html",
        {"halaman": "tunggakan", "baris": baris, "total_tagihan": total_tagihan, "hari_ini": hari_ini},
    )


@staff_member_required
def laporan_kas(request):
    hari_ini = timezone.localdate()
    dari = _tanggal(request.GET.get("dari"), hari_ini.replace(day=1))
    sampai = _tanggal(request.GET.get("sampai"), hari_ini)

    sebelum = TransaksiKas.objects.filter(tanggal__lt=dari)
    saldo_awal = _jumlah(sebelum.filter(jenis=TransaksiKas.Jenis.MASUK), "jumlah") - _jumlah(
        sebelum.filter(jenis=TransaksiKas.Jenis.KELUAR), "jumlah"
    )

    saldo = saldo_awal
    total_masuk = NOL
    total_keluar = NOL
    baris = []
    for t in TransaksiKas.objects.filter(tanggal__range=(dari, sampai)).order_by("tanggal", "id"):
        masuk = t.jumlah if t.jenis == TransaksiKas.Jenis.MASUK else NOL
        keluar = t.jumlah if t.jenis == TransaksiKas.Jenis.KELUAR else NOL
        saldo += masuk - keluar
        total_masuk += masuk
        total_keluar += keluar
        baris.append({"transaksi": t, "masuk": masuk, "keluar": keluar, "saldo": saldo})

    konteks = {
        "halaman": "kas",
        "dari": dari,
        "sampai": sampai,
        "saldo_awal": saldo_awal,
        "total_masuk": total_masuk,
        "total_keluar": total_keluar,
        "saldo_akhir": saldo,
        "baris": baris,
    }
    return render(request, "laporan/kas.html", konteks)