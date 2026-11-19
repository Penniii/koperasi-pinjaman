from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from .templatetags.rupiah import rupiah


class RupiahTest(SimpleTestCase):
    def test_format(self):
        self.assertEqual(rupiah(Decimal("1000000")), "Rp1.000.000")
        self.assertEqual(rupiah(Decimal("1816.67")), "Rp1.816,67")
        self.assertEqual(rupiah(0), "Rp0")
        self.assertEqual(rupiah(None), "Rp0")
        self.assertEqual(rupiah(Decimal("-5000")), "-Rp5.000")


class AksesHalamanTest(TestCase):
    def test_harus_login_sebagai_staf(self):
        respons = self.client.get("/laporan/")
        self.assertEqual(respons.status_code, 302)  # dialihkan ke halaman login

    def test_staf_bisa_membuka_semua_halaman(self):
        staf = get_user_model().objects.create_user("staf", password="rahasia123", is_staff=True)
        self.client.force_login(staf)
        for alamat in ["/laporan/", "/laporan/tunggakan/", "/laporan/kas/"]:
            self.assertEqual(self.client.get(alamat).status_code, 200, alamat)

class MasukKeluarTest(TestCase):
    def setUp(self):
        self.staf = get_user_model().objects.create_user(
            "staf", password="rahasia123", is_staff=True
        )

    def test_belum_login_dialihkan_ke_halaman_masuk(self):
        respons = self.client.get("/laporan/")
        self.assertRedirects(respons, "/laporan/masuk/?next=/laporan/")

    def test_login_berhasil_menuju_dashboard(self):
        respons = self.client.post(
            "/laporan/masuk/", {"username": "staf", "password": "rahasia123"}
        )
        self.assertRedirects(respons, "/laporan/")

    def test_login_salah_tetap_di_halaman_masuk(self):
        respons = self.client.post("/laporan/masuk/", {"username": "staf", "password": "salah"})
        self.assertEqual(respons.status_code, 200)

    def test_keluar_lewat_post(self):
        self.client.force_login(self.staf)
        respons = self.client.post("/laporan/keluar/")
        self.assertRedirects(respons, "/laporan/masuk/")