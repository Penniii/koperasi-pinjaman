from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from anggota.models import Anggota
from pinjaman.models import (
    JadwalAngsuran,
    JenisPinjaman,
    Pembayaran,
    PengajuanPinjaman,
    Pinjaman,
    TransaksiKas,
)
from pinjaman.services import cairkan_pengajuan, tambah_bulan

NAMA_ANGGOTA = [
    ("Siti Aminah", "Pedagang pasar"),
    ("Budi Santoso", "Petani"),
    ("Dewi Lestari", "Pemilik warung"),
    ("Agus Prasetyo", "Tukang bangunan"),
    ("Rina Wulandari", "Penjahit"),
    ("Joko Susilo", "Pedagang sayur"),
    ("Maya Anggraini", "Guru les"),
    ("Hendra Gunawan", "Pengemudi ojek"),
    ("Putri Ayu", "Pedagang kelontong"),
    ("Eko Saputra", "Peternak ayam"),
    ("Lestari Wati", "Penjual makanan"),
    ("Slamet Riyadi", "Buruh tani"),
]

# (anggota ke-, jenis, jumlah, tenor, tujuan, bulan lalu, geser hari, jumlah dibayar, {angsuran ke: hari telat})
SKENARIO = [
    (0, "reguler", 3_000_000, 6, "Modal dagang di pasar", 8, 0, 6, {2: 5}),  # lunas (satu angsuran telat 5 hari)
    (1, "reguler", 10_000_000, 12, "Membeli bibit dan pupuk", 3, 0, 3, {}),  # berjalan lancar
    (2, "reguler", 5_000_000, 12, "Menambah stok warung", 3, -12, 2, {}),  # menunggak ringan
    (3, "reguler", 8_000_000, 12, "Membeli peralatan kerja", 4, -15, 2, {}),  # menunggak sedang
    (4, "mikro", 4_000_000, 12, "Membeli mesin jahit", 6, -10, 1, {}),  # macet
    (5, "reguler", 2_000_000, 6, "Modal dagang sayur", 0, 0, 0, {}),  # baru cair hari ini
    (6, "reguler", 6_000_000, 6, "Biaya kursus dan peralatan", 3, 4, 2, {}),  # jatuh tempo beberapa hari lagi
]


class Command(BaseCommand):
    help = "Mengisi database dengan data contoh (fiktif) yang tanggalnya mengikuti hari ini."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bersih",
            action="store_true",
            help="HAPUS semua data anggota, pinjaman, dan kas lebih dulu, lalu isi data contoh",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if Anggota.objects.exists() or TransaksiKas.objects.exists():
            if not options["bersih"]:
                raise CommandError(
                    "Database sudah berisi data. Jalankan dengan --bersih untuk menghapus "
                    "semua data anggota, pinjaman, dan kas, lalu mengisi data contoh."
                )
            self.hapus_semua()

        call_command("siapkan_peran", "--akun-demo", stdout=self.stdout)
        User = get_user_model()
        kasir = User.objects.get(username="kasir")
        pengurus = User.objects.get(username="pengurus")
        hari_ini = timezone.localdate()

        jenis = {
            "reguler": JenisPinjaman.objects.create(nama="Pinjaman Reguler"),
            "mikro": JenisPinjaman.objects.create(
                nama="Pinjaman Usaha Mikro",
                bunga_per_bulan=Decimal("1.25"),
                biaya_admin_persen=Decimal("0.50"),
                jumlah_minimal=Decimal("500000"),
                jumlah_maksimal=Decimal("5000000"),
            ),
        }

        anggota = []
        for i, (nama, pekerjaan) in enumerate(NAMA_ANGGOTA, start=1):
            anggota.append(
                Anggota.objects.create(
                    nama_lengkap=nama,
                    nik=f"3571000000{i:06d}",
                    no_hp=f"0812000{i:05d}",
                    alamat=f"Jl. Melati No. {i}, Kediri",
                    pekerjaan=pekerjaan,
                    tanggal_bergabung=tambah_bulan(hari_ini, -(12 + i % 6)),
                )
            )

        TransaksiKas.objects.create(
            tanggal=tambah_bulan(hari_ini, -9),
            jenis=TransaksiKas.Jenis.MASUK,
            kategori=TransaksiKas.Kategori.LAINNYA,
            jumlah=Decimal("100000000"),
            keterangan="Modal awal kas (data contoh)",
            dibuat_oleh=kasir,
        )

        # Pinjaman yang sudah cair, dengan riwayat pembayaran
        for idx, kode_jenis, jumlah, tenor, tujuan, bulan_lalu, geser, dibayar, telat in SKENARIO:
            tanggal_cair = tambah_bulan(hari_ini + timedelta(days=geser), -bulan_lalu)
            pengajuan = PengajuanPinjaman.objects.create(
                anggota=anggota[idx],
                jenis=jenis[kode_jenis],
                jumlah=Decimal(jumlah),
                tenor_bulan=tenor,
                tujuan=tujuan,
                tanggal_pengajuan=tanggal_cair - timedelta(days=3),
                status=PengajuanPinjaman.Status.DISETUJUI,
                diputuskan_oleh=pengurus,
                tanggal_keputusan=tanggal_cair - timedelta(days=1),
            )
            pinjaman = cairkan_pengajuan(pengajuan, kasir, tanggal_cair)
            for jadwal in list(pinjaman.jadwal.order_by("angsuran_ke"))[:dibayar]:
                tanggal_bayar = min(
                    jadwal.jatuh_tempo + timedelta(days=telat.get(jadwal.angsuran_ke, 0)), hari_ini
                )
                Pembayaran(jadwal=jadwal, tanggal_bayar=tanggal_bayar, dicatat_oleh=kasir).save()

        # Pengajuan dalam berbagai tahap
        tahap = [
            (7, "reguler", 3_000_000, 6, PengajuanPinjaman.Status.DIAJUKAN, "Biaya servis kendaraan"),
            (8, "mikro", 2_500_000, 6, PengajuanPinjaman.Status.DIAJUKAN, "Menambah stok barang"),
            (9, "reguler", 4_000_000, 12, PengajuanPinjaman.Status.DISETUJUI, "Membangun kandang ayam"),
            (10, "reguler", 15_000_000, 24, PengajuanPinjaman.Status.DITOLAK, "Modal usaha rumah makan"),
        ]
        for idx, kode_jenis, jumlah, tenor, status, tujuan in tahap:
            keputusan = status != PengajuanPinjaman.Status.DIAJUKAN
            PengajuanPinjaman.objects.create(
                anggota=anggota[idx],
                jenis=jenis[kode_jenis],
                jumlah=Decimal(jumlah),
                tenor_bulan=tenor,
                tujuan=tujuan,
                tanggal_pengajuan=hari_ini - timedelta(days=2),
                status=status,
                diputuskan_oleh=pengurus if keputusan else None,
                tanggal_keputusan=hari_ini - timedelta(days=1) if keputusan else None,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Selesai: {Anggota.objects.count()} anggota, {Pinjaman.objects.count()} pinjaman, "
                f"{TransaksiKas.objects.count()} transaksi kas."
            )
        )

    def hapus_semua(self):
        urutan = [TransaksiKas, Pembayaran, JadwalAngsuran, Pinjaman, PengajuanPinjaman, Anggota, JenisPinjaman]
        for model in urutan:
            model.objects.all().delete()
        if connection.vendor == "sqlite":
            # supaya nomor AGT-/PJM- kembali mulai dari 0001
            tabel = [model._meta.db_table for model in urutan]
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join(["%s"] * len(tabel)),
                    tabel,
                )
        self.stdout.write(self.style.WARNING("Data lama dihapus."))