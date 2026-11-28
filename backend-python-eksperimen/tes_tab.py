"""Tes tab_brave.py dengan Brave tiruan. Jalankan: python tes_tab.py"""
import sys, types, unittest
from unittest import mock

sys.modules["asisten"] = types.SimpleNamespace(CDP="x", ngomong=None)
import tab_brave

TABS = [{"type": "page", "id": "1", "title": "Tutorial Python - YouTube"},
        {"type": "page", "id": "2", "title": "Lagu santai - YouTube"},
        {"type": "page", "id": "3", "title": "GitHub"},
        {"type": "service_worker", "id": "4", "title": "GitHub"}]


class Tes(unittest.TestCase):
    def jalankan(self, perintah, kode_tutup=200):
        ucap, ditutup = [], []
        tab_brave.asisten.ngomong = ucap.append

        def get(url, timeout):
            if "/close/" in url:
                ditutup.append(url.rsplit("/", 1)[1])
                return mock.Mock(status_code=kode_tutup)
            return mock.Mock(status_code=200, json=lambda: TABS)

        with mock.patch.object(tab_brave.requests, "get", get):
            tab_brave.jalankan(*tab_brave.kenali(perintah))
        return ditutup, ucap[-1]

    def test_satu_tidak_menutup_kalau_ganda(self):
        ditutup, pesan = self.jalankan("tutup tab youtube")
        self.assertEqual(ditutup, [])
        self.assertIn("belum aku tutup", pesan)

    def test_satu_dengan_judul_jelas(self):
        self.assertEqual(self.jalankan("tutup tab lagu santai")[0], ["2"])

    def test_semua(self):
        self.assertEqual(self.jalankan("tutup semua tab youtube")[0], ["1", "2"])

    def test_kata_tambahan_dan_tanda_baca(self):
        for p in ["tolong tutup tab github", "tutup tab github dong.", "tutup github tab", "tutup tab github di brave",
                  "coba tutup tabnya github ya"]:
            self.assertEqual(self.jalankan(p)[0], ["3"], p)

    def test_tanpa_nama_bertanya(self):
        for p in ["tutup tab", "tutup tab ini", "tutup semua tab", "tutup tab a"]:
            ditutup, pesan = self.jalankan(p)
            self.assertEqual(ditutup, [], p)
            self.assertIn("Sebutkan nama tab", pesan)

    def test_ditolak_tidak_mengaku_berhasil(self):
        self.assertIn("Hanya 0 dari 1", self.jalankan("tutup tab github", 404)[1])

    def test_bukan_perintah_tutup_tab(self):
        for p in ["tutup notepad", "buka tab tutup botol", "tutup tabel", "aku tidak mau tutup tab"]:
            self.assertIsNone(tab_brave.kenali(p), p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
