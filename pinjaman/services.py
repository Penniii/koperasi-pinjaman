import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import JadwalAngsuran

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