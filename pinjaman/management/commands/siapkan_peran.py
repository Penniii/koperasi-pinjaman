from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

PERAN = {
    "Kasir": [
        "anggota.add_anggota",
        "anggota.change_anggota",
        "anggota.view_anggota",
        "pinjaman.view_jenispinjaman",
        "pinjaman.add_pengajuanpinjaman",
        "pinjaman.view_pengajuanpinjaman",
        "pinjaman.cairkan_pinjaman",
        "pinjaman.view_pinjaman",
        "pinjaman.view_jadwalangsuran",
        "pinjaman.add_pembayaran",
        "pinjaman.view_pembayaran",
        "pinjaman.add_transaksikas",
        "pinjaman.view_transaksikas",
    ],
    "Pengurus": [
        "anggota.view_anggota",
        "pinjaman.view_jenispinjaman",
        "pinjaman.view_pengajuanpinjaman",
        "pinjaman.setujui_pengajuan",
        "pinjaman.view_pinjaman",
        "pinjaman.view_jadwalangsuran",
        "pinjaman.view_pembayaran",
        "pinjaman.view_transaksikas",
    ],
}


class Command(BaseCommand):
    help = "Membuat peran Kasir dan Pengurus beserta izinnya. Aman dijalankan berulang kali."

    def add_arguments(self, parser):
        parser.add_argument(
            "--akun-demo",
            action="store_true",
            help="Buat akun kasir dan pengurus untuk demo (password: demo12345)",
        )

    def handle(self, *args, **options):
        for nama, daftar_izin in PERAN.items():
            grup, _ = Group.objects.get_or_create(name=nama)
            izin = []
            for kode in daftar_izin:
                app_label, codename = kode.split(".")
                izin.append(
                    Permission.objects.get(content_type__app_label=app_label, codename=codename)
                )
            grup.permissions.set(izin)
            self.stdout.write(self.style.SUCCESS(f"Peran {nama}: {len(izin)} izin"))

        if options["akun_demo"]:
            User = get_user_model()
            for username, peran in [("kasir", "Kasir"), ("pengurus", "Pengurus")]:
                user, dibuat = User.objects.get_or_create(username=username, defaults={"is_staff": True})
                if dibuat:
                    user.set_password("demo12345")
                    user.save()
                user.groups.add(Group.objects.get(name=peran))
            self.stdout.write(self.style.SUCCESS("Akun demo: kasir dan pengurus (password: demo12345)"))