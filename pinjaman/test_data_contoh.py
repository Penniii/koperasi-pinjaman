from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from anggota.models import Anggota

from .models import PengajuanPinjaman, Pinjaman


class DataContohTest(TestCase):
    def isi(self, *argumen):
        call_command("buat_data_contoh", *argumen, stdout=StringIO())

    def test_data_contoh_terbentuk(self):
        self.isi()
        self.assertEqual(Anggota.objects.count(), 12)
        self.assertEqual(Pinjaman.objects.count(), 7)
        self.assertEqual(Pinjaman.objects.filter(status=Pinjaman.Status.LUNAS).count(), 1)
        self.assertEqual(
            PengajuanPinjaman.objects.filter(status=PengajuanPinjaman.Status.DIAJUKAN).count(), 2
        )

    def test_tidak_menimpa_data_tanpa_bersih(self):
        self.isi()
        with self.assertRaises(CommandError):
            self.isi()
        self.isi("--bersih")
        self.assertEqual(Anggota.objects.count(), 12)