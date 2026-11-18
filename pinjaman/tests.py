from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from anggota.models import Anggota

from .models import (
    JadwalAngsuran,
    JenisPinjaman,
    Pembayaran,
    PengajuanPinjaman,
    Pinjaman,
    TransaksiKas,
)
from .services import (
    buat_jadwal_angsuran,
    hitung_denda,
    hitung_hari_telat,
    hitung_jadwal_flat,
    kolektibilitas,
    tambah_bulan,
)


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


class HitungDendaTest(SimpleTestCase):
    def test_hari_telat(self):
        jatuh_tempo = date(2026, 12, 18)
        self.assertEqual(hitung_hari_telat(jatuh_tempo, date(2026, 12, 18)), 0)
        self.assertEqual(hitung_hari_telat(jatuh_tempo, date(2026, 12, 17)), 0)  # bayar lebih awal
        self.assertEqual(hitung_hari_telat(jatuh_tempo, date(2026, 12, 28)), 10)

    def test_denda(self):
        # 590.000 x 0,10% x 10 hari = 5.900
        self.assertEqual(hitung_denda(Decimal("590000"), Decimal("0.10"), 10), Decimal("5900.00"))
        self.assertEqual(hitung_denda(Decimal("590000"), Decimal("0.10"), 0), Decimal("0.00"))


class AlurPembayaranTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("kasir", password="rahasia123")
        anggota = Anggota.objects.create(
            nama_lengkap="Anggota Tes",
            nik="3571000000000009",
            no_hp="08123456789",
            alamat="Alamat tes",
            tanggal_bergabung=date(2026, 1, 1),
        )
        jenis = JenisPinjaman.objects.create(nama="Reguler")
        pengajuan = PengajuanPinjaman.objects.create(
            anggota=anggota, jenis=jenis, jumlah=Decimal("1200000"), tenor_bulan=6, tujuan="Tes"
        )
        self.pinjaman = Pinjaman.objects.create(
            pengajuan=pengajuan,
            tanggal_cair=date(2026, 1, 15),
            pokok=Decimal("1200000"),
            tenor_bulan=6,
            bunga_per_bulan=Decimal("1.50"),
            biaya_admin=Decimal("12000"),
            denda_per_hari_persen=Decimal("0.10"),
            dicairkan_oleh=self.user,
        )
        buat_jadwal_angsuran(self.pinjaman)  # 6 angsuran: pokok 200.000 + jasa 18.000 = 218.000

    def bayar(self, ke, tanggal=None):
        jadwal = self.pinjaman.jadwal.get(angsuran_ke=ke)
        pembayaran = Pembayaran(
            jadwal=jadwal, tanggal_bayar=tanggal or jadwal.jatuh_tempo, dicatat_oleh=self.user
        )
        pembayaran.clean()
        pembayaran.save()
        return pembayaran

    def test_bayar_tepat_waktu_tanpa_denda(self):
        pembayaran = self.bayar(1)  # jatuh tempo 15 Feb 2026
        self.assertEqual(pembayaran.hari_telat, 0)
        self.assertEqual(pembayaran.denda, Decimal("0.00"))
        self.assertEqual(
            self.pinjaman.jadwal.get(angsuran_ke=1).status, JadwalAngsuran.Status.LUNAS
        )
        kas = TransaksiKas.objects.filter(pembayaran=pembayaran)
        self.assertEqual(kas.count(), 2)  # pokok + jasa, tanpa denda
        self.assertEqual(sum(k.jumlah for k in kas), Decimal("218000"))

    def test_bayar_terlambat_kena_denda(self):
        pembayaran = self.bayar(1, date(2026, 2, 25))  # telat 10 hari
        self.assertEqual(pembayaran.hari_telat, 10)
        self.assertEqual(pembayaran.denda, Decimal("2180.00"))  # 218.000 x 0,1% x 10
        kas = TransaksiKas.objects.filter(pembayaran=pembayaran)
        self.assertEqual(kas.count(), 3)
        self.assertTrue(kas.filter(kategori=TransaksiKas.Kategori.DENDA).exists())

    def test_harus_berurutan_dan_tidak_boleh_dobel(self):
        jadwal_ke_2 = self.pinjaman.jadwal.get(angsuran_ke=2)
        with self.assertRaises(ValidationError):
            Pembayaran(
                jadwal=jadwal_ke_2, tanggal_bayar=date(2026, 3, 15), dicatat_oleh=self.user
            ).clean()

        self.bayar(1)
        jadwal_ke_1 = self.pinjaman.jadwal.get(angsuran_ke=1)
        with self.assertRaises(ValidationError):
            Pembayaran(
                jadwal=jadwal_ke_1, tanggal_bayar=date(2026, 2, 15), dicatat_oleh=self.user
            ).clean()

    def test_pinjaman_lunas_setelah_semua_angsuran_dibayar(self):
        for ke in range(1, 7):
            self.bayar(ke)
        self.pinjaman.refresh_from_db()
        self.assertEqual(self.pinjaman.status, Pinjaman.Status.LUNAS)
        total_pokok = sum(
            k.jumlah
            for k in TransaksiKas.objects.filter(kategori=TransaksiKas.Kategori.ANGSURAN_POKOK)
        )
        self.assertEqual(total_pokok, Decimal("1200000"))

class KolektibilitasTest(SimpleTestCase):
    def test_tingkat_kolektibilitas(self):
        self.assertEqual(kolektibilitas(0), "Lancar")
        self.assertEqual(kolektibilitas(1), "Terlambat")
        self.assertEqual(kolektibilitas(30), "Terlambat")
        self.assertEqual(kolektibilitas(31), "Kurang lancar")
        self.assertEqual(kolektibilitas(90), "Kurang lancar")
        self.assertEqual(kolektibilitas(91), "Macet")