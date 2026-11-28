"""Tes video.py tanpa Windows. Jalankan: python tes_video.py"""
import sys, types, unittest
from unittest import mock
sys.modules.setdefault("jendela", types.ModuleType("jendela"))
import video

CAPTION = 0x00C00000
MONITOR = (0, 0, 1920, 1080)


class Tes(unittest.TestCase):
    depan = True

    def test_alt_tidak_ditekan_kalau_browser_sudah_di_depan(self):
        w = mock.Mock()
        video.jendela._w = lambda: w
        with mock.patch.object(video, "di_depan", lambda h: True):
            video._fokus(1)
        w.fokus.assert_not_called()          # w.fokus() menekan Alt, yang memindahkan fokus ke menu browser
        with mock.patch.object(video, "di_depan", lambda h: False):
            video._fokus(1)
        w.fokus.assert_called_once_with(1)

    def test_tidak_menekan_tombol_ke_jendela_lain(self):
        self.depan = False
        for aksi, status in (("masuk", [False]), ("keluar", [True])):
            pesan, tombol = self.jalankan(aksi, status)
            self.assertEqual(tombol, [])
            self.assertIn("tidak bisa pindah", pesan)

    def test_maximize_menutupi_monitor_bukan_layar_penuh(self):
        self.assertFalse(video._penuh(CAPTION, (-8, -8, 1928, 1088), MONITOR))

    def test_layar_penuh_asli(self):
        self.assertTrue(video._penuh(0, MONITOR, MONITOR))

    def test_jendela_kecil_tanpa_bingkai(self):
        self.assertFalse(video._penuh(0, (100, 100, 900, 700), MONITOR))

    def jalankan(self, aksi, status):
        tombol, urutan = [], iter(status)
        akhir = status[-1]
        video.daftar_jendela = lambda: [{"hwnd": 1, "exe": "brave.exe", "judul": "YouTube"}]
        video.layar_penuh = lambda h: next(urutan, akhir)
        video.fokus = lambda h: None
        video.di_depan = lambda h: self.depan
        video.tekan = tombol.append
        video.jeda_fokus = video.jeda_cek = 0
        return video.jalankan(aksi), tombol

    def test_masuk_berhasil(self):
        pesan, tombol = self.jalankan("masuk", [False, False, True])
        self.assertEqual(tombol, [video.VK_F])
        self.assertIn("aku buat layar penuh", pesan)

    def test_masuk_gagal_tidak_mengaku_berhasil(self):
        pesan, tombol = self.jalankan("masuk", [False])
        self.assertEqual(tombol, [video.VK_F])          # F hanya sekali: dua kali = membatalkan
        self.assertIn("belum jadi layar penuh", pesan)

    def test_keluar_tetap_pakai_esc(self):
        _, tombol = self.jalankan("keluar", [True])
        self.assertEqual(tombol, [video.VK_ESC])

    def test_kenali(self):
        self.assertEqual(video.kenali("besarkan youtube"), "masuk")
        self.assertEqual(video.kenali("kecilkan youtube"), "keluar")


if __name__ == "__main__":
    unittest.main(verbosity=2)
