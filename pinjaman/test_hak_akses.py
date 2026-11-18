from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


class HakAksesPeranTest(TestCase):
    def setUp(self):
        call_command("siapkan_peran", "--akun-demo", stdout=StringIO())
        User = get_user_model()
        self.kasir = User.objects.get(username="kasir")
        self.pengurus = User.objects.get(username="pengurus")

    def test_kasir_mencairkan_dan_mencatat_bayar_tapi_tidak_menyetujui(self):
        self.assertTrue(self.kasir.has_perm("pinjaman.cairkan_pinjaman"))
        self.assertTrue(self.kasir.has_perm("pinjaman.add_pembayaran"))
        self.assertFalse(self.kasir.has_perm("pinjaman.setujui_pengajuan"))
        self.assertFalse(self.kasir.has_perm("pinjaman.add_jenispinjaman"))

    def test_pengurus_menyetujui_tapi_tidak_mencairkan(self):
        self.assertTrue(self.pengurus.has_perm("pinjaman.setujui_pengajuan"))
        self.assertFalse(self.pengurus.has_perm("pinjaman.cairkan_pinjaman"))
        self.assertFalse(self.pengurus.has_perm("pinjaman.add_pembayaran"))