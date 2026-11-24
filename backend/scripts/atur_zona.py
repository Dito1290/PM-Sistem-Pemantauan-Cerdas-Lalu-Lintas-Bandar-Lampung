"""Gambar zona jalan (lajur yang seharusnya terus bergerak) untuk indikasi kendaraan berhenti.

Zona disimpan di ANOMALY_ZONES_FILE (bawaan backend/zones.json) dengan koordinat
relatif 0..1, jadi tidak bergantung pada ukuran gambar. Masukkan hanya lajur
kendaraan; jangan masukkan bahu jalan, trotoar, tempat parkir, atau tempat angkot
ngetem, supaya kendaraan yang wajar berhenti di sana tidak memicu peringatan.

Sumber gambar (pilih satu):
    --kamera 1             gambar terbaru dari pipeline yang sedang jalan (Redis)
    --gambar foto.jpg      file gambar
    --video rekaman.mp4    gambar dari video (detik ke --detik, bawaan 5)

Contoh (dari folder backend, dengan venv backend):
    python scripts\\atur_zona.py --kamera 1
    python scripts\\atur_zona.py --kamera 4 --video C:\\video\\uji_mogok.mp4

Di jendela:
    klik kiri   tambah titik sudut zona
    klik kanan  hapus titik terakhir
    c           kosongkan titik
    Enter       simpan dan tutup
    Esc         tutup tanpa menyimpan
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

LEBAR = 1280  # lebar tampilan; zona disimpan relatif, jadi ukuran ini tidak penting


def ambil_gambar(a) -> np.ndarray:
    if a.gambar:
        gambar = cv2.imread(a.gambar)
    elif a.video:
        cap = cv2.VideoCapture(a.video)
        cap.set(cv2.CAP_PROP_POS_MSEC, a.detik * 1000)
        ok, gambar = cap.read()
        cap.release()
        gambar = gambar if ok else None
    else:
        import redis
        from dotenv import load_dotenv

        load_dotenv()
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
        jpeg = r.hget(f"camera:live:{a.kamera}", "jpeg")
        if not jpeg:
            raise SystemExit(f"Belum ada gambar live kamera {a.kamera}. Nyalakan ingest dan worker dulu, "
                             "atau pakai --gambar / --video.")
        gambar = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if gambar is None:
        raise SystemExit("Gambar tidak bisa dibaca.")
    tinggi = round(gambar.shape[0] * LEBAR / gambar.shape[1])
    return cv2.resize(gambar, (LEBAR, tinggi), interpolation=cv2.INTER_AREA)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kamera", type=int, required=True, help="id kamera di database")
    p.add_argument("--gambar")
    p.add_argument("--video")
    p.add_argument("--detik", type=float, default=5.0)
    p.add_argument("--file", help="file zona (bawaan ANOMALY_ZONES_FILE dari .env atau zones.json)")
    a = p.parse_args()

    from dotenv import load_dotenv

    load_dotenv()
    path = a.file or os.getenv("ANOMALY_ZONES_FILE", "zones.json")
    zona = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            zona = json.load(f)
    gambar = ambil_gambar(a)
    h, w = gambar.shape[:2]
    lama = zona.get(str(a.kamera), [])
    if isinstance(lama, dict):  # {"areas": [...], "disabled": [...]}: keep the settings
        lama = lama.get("areas", [])
    if lama and not isinstance(lama[0][0], (int, float)):  # several areas: edit the first
        if len(lama) > 1:
            print(f"Kamera {a.kamera} punya {len(lama)} area; alat ini mengganti semuanya dengan satu area. "
                  "Untuk beberapa area (satu per arah), ubah zones.json langsung.")
        lama = lama[0]
    titik = [[x * w, y * h] for x, y in lama]

    import tkinter as tk
    from PIL import Image, ImageTk

    root = tk.Tk()
    root.title(f"Zona jalan kamera {a.kamera}  |  klik: titik, kanan: hapus, c: kosongkan, Enter: simpan, Esc: batal")
    kanvas = tk.Label(root)
    kanvas.pack()
    hasil = {"simpan": False}

    def gambar_ulang():
        layar = gambar.copy()
        if titik:
            pts = np.array(titik, np.int32)
            if len(titik) >= 3:
                isi = layar.copy()
                cv2.fillPoly(isi, [pts], (0, 200, 255))
                layar = cv2.addWeighted(isi, 0.25, layar, 0.75, 0)
            cv2.polylines(layar, [pts], len(titik) >= 3, (0, 220, 255), 2, cv2.LINE_AA)
            for x, y in pts:
                cv2.circle(layar, (int(x), int(y)), 5, (0, 220, 255), -1)
        foto = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(layar, cv2.COLOR_BGR2RGB)))
        kanvas.configure(image=foto)
        kanvas.foto = foto

    def klik_kiri(e):
        titik.append([e.x, e.y])
        gambar_ulang()

    def klik_kanan(_e):
        if titik:
            titik.pop()
            gambar_ulang()

    def kosongkan(_e):
        titik.clear()
        gambar_ulang()

    def simpan(_e):
        if len(titik) < 3:
            print("Zona butuh minimal 3 titik.")
            return
        hasil["simpan"] = True
        root.destroy()

    kanvas.bind("<Button-1>", klik_kiri)
    kanvas.bind("<Button-3>", klik_kanan)
    root.bind("c", kosongkan)
    root.bind("<Return>", simpan)
    root.bind("<Escape>", lambda _e: root.destroy())
    gambar_ulang()
    root.mainloop()

    if not hasil["simpan"]:
        print("Tidak disimpan.")
        return
    baru = [[round(x / w, 4), round(y / h, 4)] for x, y in titik]
    if isinstance(zona.get(str(a.kamera)), dict):
        zona[str(a.kamera)]["areas"] = [baru]
    else:
        zona[str(a.kamera)] = baru
    with open(path, "w", encoding="utf-8") as f:
        json.dump(zona, f, indent=2, ensure_ascii=False)
    print(f"Zona kamera {a.kamera} ({len(titik)} titik) tersimpan di {os.path.abspath(path)}. "
          "Worker membacanya ulang otomatis.")


if __name__ == "__main__":
    main()
