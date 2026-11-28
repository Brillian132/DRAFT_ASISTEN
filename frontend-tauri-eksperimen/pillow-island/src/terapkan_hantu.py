#!/usr/bin/env python3
"""Mengganti wajah kartu (hijau/kuning/merah/ungu) dengan ikon hantu yang matanya bergerak, TANPA menimpa perubahanmu.

Cara pakai (PowerShell):
    python terapkan_hantu.py "D:\\asisten\\frontend-tauri-eksperimen\\pillow-island\\src"

  - argumen = folder src Tauri (tempat index.html, styles.css, main.js)
  - cadangan: <nama>.bak-hantu ; opsi --ulang mengembalikan dari cadangan dulu
Kalau ada bagian yang tidak cocok, skrip berhenti tanpa mengubah apa pun; kalau pemeriksaan sintaks gagal, semua dikembalikan.
"""
import os
import sys
import shutil
import subprocess

SUFFIX = ".bak-hantu"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]

KT_LAMA = '<div class="kt-face">\n          <div class="eye l"></div>\n          <div class="eye r"></div>\n        </div>'
KT_BARU = '<div class="kt-face">\n          <svg class="ghost" viewBox="317.2 325.2 618.6 639.6" aria-hidden="true" focusable="false">\n            <path class="g-ring" fill-rule="evenodd" d="M572.8 335.2 540.8 342.2 515.8 350.2 487.8 362.2 462.2 376.5 442.2 390.5 425.2 404.5 399.5 430.2 383.5 450.2 370.5 469.2 354.2 498.8 344.2 521.8 334.2 551.8 328.2 576.8 323.2 616.8 323.2 648.2 325.2 669.2 332.2 704.2 346.2 743.2 356.5 762.8 366.5 777.8 373.5 786.8 390.2 803.5 405.2 814.5 422.8 823.8 439.8 829.8 449.8 831.8 480.2 832.8 496.2 829.8 508.8 824.8 513.8 825.2 518.2 831.8 522.2 850.2 530.5 867.8 537.5 877.8 548.2 888.5 555.2 893.5 568.8 899.8 592.8 903.2 600.5 917.8 613.2 934.5 628.2 946.5 645.8 954.8 651.2 955.8 663.8 958.8 680.2 958.8 691.2 956.8 713.8 947.5 724.8 939.5 734.5 929.8 743.5 916.8 748.8 906.2 753.8 890.2 754.8 865.8 750.8 844.8 755.2 838.2 763.2 837.8 783.8 842.8 803.2 842.8 822.2 838.8 833.2 834.8 850.8 825.5 868.8 811.5 882.5 796.8 892.5 782.8 904.8 760.2 913.8 738.2 922.8 707.2 929.8 661.2 929.8 611.8 927.8 592.8 921.8 560.8 913.8 533.8 905.8 512.8 885.5 473.2 869.5 449.2 851.5 427.2 828.8 404.5 803.8 384.5 774.8 366.5 749.2 354.2 718.2 343.2 689.2 336.2 648.2 331.2 606.8 331.2ZM569.8 369.8 607.8 364.8 646.2 364.8 674.2 367.8 695.2 371.8 722.2 379.8 746.2 389.8 773.8 405.2 807.8 431.2 828.8 452.2 846.8 475.2 858.8 494.2 871.2 517.8 881.2 542.8 889.2 570.8 894.2 598.8 896.2 620.8 895.2 665.2 893.2 681.2 885.2 716.2 878.2 736.2 868.8 755.8 857.8 772.8 842.8 788.8 830.8 797.8 812.2 806.2 802.2 808.2 783.8 808.2 769.8 804.2 754.2 796.2 746.2 794.2 734.8 795.2 721.2 802.5 705.5 822.2 704.2 827.2 718.8 843.2 726.2 856.8 729.2 868.8 729.2 881.2 727.2 890.2 719.8 905.8 707.8 918.8 693.2 927.2 683.8 929.2 682.2 930.2 658.8 929.2 644.2 922.8 637.2 917.8 627.2 906.8 620.8 895.2 617.8 885.2 616.8 872.8 612.8 866.5 608.2 864.2 601.8 864.2 592.2 868.2 581.8 868.2 569.2 861.8 563.2 855.8 555.8 844.2 550.8 829.2 549.8 819.8 544.5 806.2 539.5 799.2 532.8 793.5 520.2 788.2 511.8 788.2 482.2 798.2 462.8 799.2 446.8 796.2 435.8 792.2 415.2 779.8 396.2 760.8 383.2 740.8 370.8 713.2 362.8 685.2 357.8 651.2 357.8 614.8 360.8 588.8 367.8 557.8 374.8 536.8 381.8 519.8 399.2 487.2 418.2 460.2 435.2 441.2 449.2 428.2 471.2 411.2 490.2 399.2 519.8 384.8 548.8 374.8Z"/>\n            <path class="g-dot" d="M671.8 848.2 663.8 850.2 656.2 854.5 650.5 861.2 647.2 868.8 646.2 874.8 647.2 883.2 652.5 893.8 659.2 899.5 667.8 902.8 679.2 902.8 688.8 898.5 696.5 890.8 699.8 883.2 700.8 878.2 699.8 868.8 694.5 858.2 689.8 853.5 680.2 849.2Z"/>\n            <path class="g-face" d="M609.8 401.2 590.8 403.2 564.8 408.2 526.8 421.2 504.2 432.5 485.2 444.5 469.2 457.5 448.5 478.2 437.5 492.2 423.5 514.2 411.2 539.8 403.2 561.8 398.2 580.8 394.2 603.8 393.2 651.2 400.2 689.2 409.2 714.2 421.5 735.8 437.2 752.5 449.8 759.8 458.8 762.8 469.2 763.8 480.2 761.8 489.8 757.5 503.2 746.2 514.8 739.8 523.8 737.8 539.2 739.8 550.8 746.2 558.8 754.2 567.2 769.8 573.2 786.2 578.5 795.8 583.5 802.8 595.2 814.5 607.8 821.8 616.8 824.8 633.2 825.8 642.2 823.8 654.8 818.5 670.5 805.8 683.5 786.8 689.8 770.8 698.2 755.2 707.2 746.2 715.8 740.8 727.8 737.8 744.2 740.8 751.8 745.2 769.2 763.5 775.8 767.8 787.8 771.8 802.2 770.8 810.8 767.5 819.8 761.5 834.5 743.8 843.8 725.2 850.8 706.2 855.8 686.2 859.8 661.2 860.8 618.8 854.8 577.8 851.8 565.8 839.8 532.8 831.5 516.2 815.5 491.2 801.5 474.2 785.8 458.5 769.8 445.5 749.8 432.5 725.2 420.2 700.2 411.2 685.2 407.2 656.2 402.2Z"/>\n            <ellipse class="g-eye l" cx="528" cy="584" rx="54.2" ry="80.2"/>\n            <ellipse class="g-eye r" cx="731" cy="584" rx="54.2" ry="80.2"/>\n          </svg>\n        </div>'
CSS_HANTU = '\n/* =========================================\n   --- WAJAH KARTU: ikon hantu dengan mata yang bergerak ---\n   Cincin ungu mengikuti ikon; titik di gelembung tetesan berwarna sesuai nada (--tone).\n   Mata memakai variabel lirikan yang sama dengan mata pill (--gx, --gy, --blink, --gdur),\n   jadi gerakan dan kedipan dari main.js langsung berlaku. Satuan translate = satuan viewBox SVG.\n   ========================================= */\n.kt-face { width: auto; height: auto; background: none; border-radius: 0; gap: 0; }\n.ghost { height: 58px; width: auto; display: block; overflow: visible; }\n.g-ring { fill: #a24dfd; }\n.g-dot { fill: var(--tone); transition: fill 0.25s ease; }\n.g-face { fill: #ffffff; }\n.g-eye {\n  fill: #0e021a;\n  transform-box: fill-box;\n  transform-origin: center;\n  /* clamp terukur: pada batas ini mata tetap >= 6 satuan dari tepi wajah di semua ekspresi (jangan dilonggarkan) */\n  translate: clamp(-26px, calc(var(--gx, 0) * 5.2px), 26px) clamp(-28px, calc(var(--gy, 0) * 12px), 28px);\n  scale: 1 var(--blink, 1);\n  transition:\n    translate var(--gdur, 0.14s) cubic-bezier(0.22, 1, 0.36, 1),\n    scale 0.07s ease-out, transform 0.25s ease, rotate 0.25s ease;\n}\n/* ekspresi (data-mood di #pill): senang = menyipit, kaget = membesar, khawatir = miring ke dalam */\n#pill[data-mood="happy"] .g-eye { scale: 1.12 calc(0.4 * var(--blink, 1)); transform: translateY(-12px); }\n#pill[data-mood="surprised"] .g-eye { scale: 1.18 calc(1.2 * var(--blink, 1)); }\n#pill[data-mood="worried"] .g-eye { scale: 1 calc(0.8 * var(--blink, 1)); }\n#pill[data-mood="worried"] .g-eye.l { rotate: 14deg; }\n#pill[data-mood="worried"] .g-eye.r { rotate: -14deg; }\n'
JS_LAMA = '  if (pill.dataset.mood === "happy") return; // mata senang berbentuk lengkung, tidak perlu berkedip'
JS_BARU = '  if (pill.dataset.mood === "happy" && state !== "card") return; // mata senang di pill kecil berbentuk lengkung; mata hantu di kartu boleh berkedip'

# (berkas, nama, jenis, jangkar, teks, penanda)
PERUBAHAN = [
    ("index.html", "wajah kartu menjadi ikon hantu", "ganti", KT_LAMA, KT_BARU, 'class="ghost"'),
    ("styles.css", "gaya hantu, gerak mata, dan ekspresi", "tambah_akhir", "", CSS_HANTU, "WAJAH KARTU: ikon hantu"),
    ("main.js", "mata hantu boleh berkedip saat senang", "ganti", JS_LAMA, JS_BARU, 'state !== "card") return;'),
]


def terapkan(isi, jenis, jangkar, teks, penanda):
    if penanda in isi:
        return isi, "sudah"
    if jenis == "tambah_akhir":
        return isi.rstrip("\n") + "\n" + teks, "ok"
    n = isi.count(jangkar)
    if n != 1:
        return isi, "tidak-ketemu" if n == 0 else "ganda"
    return isi.replace(jangkar, teks, 1), "ok"


def main():
    try:
        folder = (ARGS[0] if ARGS else input("Folder src Tauri (tempat main.js): ")).strip().strip('"')
    except EOFError:
        folder = ""
    jalur = {b: os.path.join(folder, b) for b in ("index.html", "styles.css", "main.js")}
    hilang = [j for j in jalur.values() if not os.path.isfile(j)]
    if hilang:
        print("Berkas ini tidak ditemukan, periksa nama folder:\n  " + "\n  ".join(hilang))
        return 1
    if "--ulang" in sys.argv:
        for b, j in jalur.items():
            if os.path.isfile(j + SUFFIX):
                shutil.copy2(j + SUFFIX, j)
                print(f"  [dikembalikan] {b} dari cadangan")
    isi = {b: open(j, encoding="utf-8").read() for b, j in jalur.items()}
    asli = dict(isi)
    laporan, gagal = [], []
    for berkas, nama, jenis, jangkar, teks, penanda in PERUBAHAN:
        baru, status = terapkan(isi[berkas], jenis, jangkar, teks, penanda)
        if status == "ok":
            isi[berkas] = baru
            laporan.append(f"  [terpasang] {berkas}: {nama}")
        elif status == "sudah":
            laporan.append(f"  [sudah ada] {berkas}: {nama}")
        else:
            gagal.append(f"{berkas}: {nama} ({'jangkar tidak ditemukan' if status == 'tidak-ketemu' else 'jangkar muncul lebih dari sekali'})")
    print("\n".join(laporan))
    if gagal:
        print("\nTIDAK ADA FILE YANG DIUBAH. Bagian berikut tidak cocok dengan file-mu:\n  " + "\n  ".join(gagal))
        print("Kirim bagian file di sekitar itu ke saya, nanti saya sesuaikan.")
        return 2
    diubah = [b for b in jalur if isi[b] != asli[b]]
    for b in diubah:
        if not os.path.exists(jalur[b] + SUFFIX):
            shutil.copy2(jalur[b], jalur[b] + SUFFIX)
        with open(jalur[b], "w", encoding="utf-8") as f:
            f.write(isi[b])
    if "main.js" in diubah and shutil.which("node"):
        r = subprocess.run(["node", "--check", jalur["main.js"]], capture_output=True, text=True)
        if r.returncode != 0:
            for b in diubah:
                shutil.copy2(jalur[b] + SUFFIX, jalur[b])
            print("\nPemeriksaan sintaks GAGAL, semua file sudah dikembalikan seperti semula:\n  " + r.stderr.strip()[-300:])
            return 3
    print(f"\nSelesai. {len(diubah)} file diperbarui (cadangan: *{SUFFIX}).")
    print("Langkah berikut: jalankan ulang aplikasi (Ctrl+Shift+R di jendela pill).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
