import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import JadwalAngsuran, PengajuanPinjaman, Pinjaman, TransaksiKas

SEN = Decimal("0.01")


@dataclass(frozen=True)
class BarisAngsuran:
    angsuran_ke: int
    jatuh_tempo: date
    pokok: Decimal
    jasa: Decimal

    @property
    def total(self):
        return self.pokok + self.jasa


def tambah_bulan(tanggal, jumlah_bulan):
    """Tambah bulan tanpa library tambahan. 31 Jan + 1 bulan = 28 Feb (hari disesuaikan)."""
    indeks = tanggal.month - 1 + jumlah_bulan
    tahun = tanggal.year + indeks // 12
    bulan = indeks % 12 + 1
    hari = min(tanggal.day, calendar.monthrange(tahun, bulan)[1])
    return date(tahun, bulan, hari)


def hitung_jadwal_flat(pokok, tenor_bulan, bunga_per_bulan, tanggal_cair):
    """Bunga flat: jasa tiap bulan sama, dihitung dari pokok awal."""
    pokok = Decimal(pokok)
    bunga_per_bulan = Decimal(bunga_per_bulan)

    pokok_per_bulan = (pokok / tenor_bulan).quantize(SEN, ROUND_HALF_UP)
    jasa_per_bulan = (pokok * bunga_per_bulan / 100).quantize(SEN, ROUND_HALF_UP)

    baris = []
    sisa = pokok
    for ke in range(1, tenor_bulan + 1):
        # Angsuran terakhir menyerap sisa pembulatan, supaya total pokok pas
        pokok_ke = sisa if ke == tenor_bulan else pokok_per_bulan
        sisa -= pokok_ke
        baris.append(
            BarisAngsuran(
                angsuran_ke=ke,
                jatuh_tempo=tambah_bulan(tanggal_cair, ke),
                pokok=pokok_ke,
                jasa=jasa_per_bulan,
            )
        )
    return baris


def buat_jadwal_angsuran(pinjaman):
    """Simpan jadwal ke database. Aman dipanggil dua kali (tidak membuat ganda)."""
    with transaction.atomic():
        if pinjaman.jadwal.exists():
            return
        baris = hitung_jadwal_flat(
            pinjaman.pokok, pinjaman.tenor_bulan, pinjaman.bunga_per_bulan, pinjaman.tanggal_cair
        )
        JadwalAngsuran.objects.bulk_create(
            [
                JadwalAngsuran(
                    pinjaman=pinjaman,
                    angsuran_ke=b.angsuran_ke,
                    jatuh_tempo=b.jatuh_tempo,
                    pokok=b.pokok,
                    jasa=b.jasa,
                )
                for b in baris
            ]
        )

def hitung_hari_telat(jatuh_tempo, tanggal_bayar):
    """Bayar lebih awal atau tepat waktu = 0 hari telat (tidak pernah negatif)."""
    return max(0, (tanggal_bayar - jatuh_tempo).days)


def hitung_denda(total_angsuran, denda_per_hari_persen, hari_telat):
    """Denda = total angsuran x persen denda per hari x jumlah hari telat."""
    denda = Decimal(total_angsuran) * Decimal(denda_per_hari_persen) / 100 * hari_telat
    return denda.quantize(SEN, ROUND_HALF_UP)


def catat_kas_pencairan(pinjaman, petugas):
    """Kas keluar sebesar pokok, kas masuk sebesar biaya admin. Aman dipanggil dua kali."""
    with transaction.atomic():
        sudah_ada = pinjaman.kas.filter(
            kategori__in=[TransaksiKas.Kategori.PENCAIRAN, TransaksiKas.Kategori.BIAYA_ADMIN]
        ).exists()
        if sudah_ada:
            return
        TransaksiKas.objects.create(
            tanggal=pinjaman.tanggal_cair,
            jenis=TransaksiKas.Jenis.KELUAR,
            kategori=TransaksiKas.Kategori.PENCAIRAN,
            jumlah=pinjaman.pokok,
            keterangan=f"Pencairan {pinjaman.no_pinjaman}",
            pinjaman=pinjaman,
            dibuat_oleh=petugas,
        )
        if pinjaman.biaya_admin > 0:
            TransaksiKas.objects.create(
                tanggal=pinjaman.tanggal_cair,
                jenis=TransaksiKas.Jenis.MASUK,
                kategori=TransaksiKas.Kategori.BIAYA_ADMIN,
                jumlah=pinjaman.biaya_admin,
                keterangan=f"Biaya admin {pinjaman.no_pinjaman}",
                pinjaman=pinjaman,
                dibuat_oleh=petugas,
            )
def kolektibilitas(hari_telat):
    """Tingkat kualitas pinjaman berdasarkan lama keterlambatan."""
    if hari_telat <= 0:
        return "Lancar"
    if hari_telat <= 30:
        return "Terlambat"
    if hari_telat <= 90:
        return "Kurang lancar"
    return "Macet"

def cairkan_pengajuan(pengajuan, petugas, tanggal_cair):
    """Mencairkan pengajuan yang sudah disetujui: buat pinjaman, jadwal angsuran, dan catat kas."""
    with transaction.atomic():
        jenis = pengajuan.jenis
        pinjaman = Pinjaman.objects.create(
            pengajuan=pengajuan,
            tanggal_cair=tanggal_cair,
            pokok=pengajuan.jumlah,
            tenor_bulan=pengajuan.tenor_bulan,
            bunga_per_bulan=jenis.bunga_per_bulan,
            biaya_admin=(pengajuan.jumlah * jenis.biaya_admin_persen / 100).quantize(
                SEN, ROUND_HALF_UP
            ),
            denda_per_hari_persen=jenis.denda_per_hari_persen,
            dicairkan_oleh=petugas,
        )
        buat_jadwal_angsuran(pinjaman)
        catat_kas_pencairan(pinjaman, petugas)
        pengajuan.status = PengajuanPinjaman.Status.DICAIRKAN
        pengajuan.save(update_fields=["status"])
        return pinjaman