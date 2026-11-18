from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from .services import hitung_jadwal_flat, tambah_bulan


class HitungJadwalFlatTest(SimpleTestCase):
    def test_contoh_6_juta_12_bulan(self):
        jadwal = hitung_jadwal_flat(Decimal("6000000"), 12, Decimal("1.5"), date(2026, 11, 18))
        self.assertEqual(len(jadwal), 12)
        for baris in jadwal:
            self.assertEqual(baris.pokok, Decimal("500000.00"))
            self.assertEqual(baris.jasa, Decimal("90000.00"))
            self.assertEqual(baris.total, Decimal("590000.00"))
        self.assertEqual(sum(b.pokok for b in jadwal), Decimal("6000000"))

    def test_sisa_pembulatan_masuk_angsuran_terakhir(self):
        jadwal = hitung_jadwal_flat(Decimal("1000000"), 6, Decimal("1.5"), date(2026, 11, 18))
        self.assertEqual(jadwal[0].pokok, Decimal("166666.67"))
        self.assertEqual(jadwal[-1].pokok, Decimal("166666.65"))
        self.assertEqual(sum(b.pokok for b in jadwal), Decimal("1000000"))

    def test_jatuh_tempo_akhir_bulan(self):
        self.assertEqual(tambah_bulan(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(tambah_bulan(date(2026, 1, 31), 2), date(2026, 3, 31))
    self.assertEqual(tambah_bulan(date(2026, 11, 18), 3), date(2027, 2, 18))