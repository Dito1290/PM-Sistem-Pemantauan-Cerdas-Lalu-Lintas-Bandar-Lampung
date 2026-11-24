"""Tinjau peringatan anomali satu per satu dan tandai benar atau salah (pengganti sementara
tombol di dashboard). Hasilnya sama dengan POST /api/anomalies/<id>/review.

Foto diambil dari ANOMALY_PHOTO_DIR backend. Untuk peringatan lama yang belum punya foto
di sana, bisa dicari di folder pencatat (catat_anomali.py) lewat --foto-pencatat.

Contoh (dari folder backend, dengan venv backend):
    python scripts\\tinjau_anomali.py --nama adira
    python scripts\\tinjau_anomali.py --nama adira --foto-pencatat C:\\Users\\arkof\\deteksi_kendaraan\\hasil\\anomali_20261124
    python scripts\\tinjau_anomali.py --ringkasan          rangkuman ketepatan 30 hari terakhir

Di jendela:
    B  benar (memang kejadian yang perlu dicek operator)
    S  salah (peringatan palsu)
    L  lewati
    Q  selesai
Untuk menambah catatan (misalnya "parkir nongkrong"), klik kotak Catatan, ketik, lalu
tekan Ctrl+B atau Ctrl+S (atau Esc lalu B / S).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

from sqlalchemy import select  # noqa: E402

from citysight import create_app  # noqa: E402
from citysight.extensions import db  # noqa: E402
from citysight.models import Anomaly, Camera  # noqa: E402
from citysight.services import anomaly_service  # noqa: E402

JENIS = {"high_density": "Kepadatan tidak wajar", "camera_offline": "Kamera mati",
         "stopped_vehicle": "Kendaraan berhenti", "people_on_road": "Orang di badan jalan"}


def foto_pencatat(folder: Path | None, anomaly: Anomaly, tz) -> Path | None:
    """Foto dari catat_anomali.py: <HHMMSS>_kam<id>_<jenis>.jpg, disimpan saat peringatan diumumkan,
    yaitu beberapa detik sampai beberapa menit setelah started_at."""
    if folder is None or not folder.is_dir():
        return None
    mulai = anomaly.started_at.astimezone(tz)
    terbaik = None
    for path in folder.glob(f"*_kam{anomaly.camera_id}_{anomaly.type}.jpg"):
        try:
            jam = datetime.strptime(path.name[:6], "%H%M%S").time()
        except ValueError:
            continue
        waktu = datetime.combine(mulai.date(), jam, tz)
        selisih = (waktu - mulai).total_seconds()
        if -60 <= selisih <= 600 and (terbaik is None or selisih < terbaik[0]):
            terbaik = (selisih, path)
    return terbaik[1] if terbaik else None


def ringkasan(app) -> None:
    tz = ZoneInfo(app.config["REPORT_TIMEZONE"])
    akhir = datetime.now(tz)
    with app.app_context():
        baris = anomaly_service.review_summary(akhir - timedelta(days=30), akhir)
    if not baris:
        print("Belum ada peringatan dalam 30 hari terakhir.")
    for b in baris:
        tepat = "-" if b["precision"] is None else f"{b['precision']:.0%}"
        print(f"{b['camera_name']:22s} {JENIS.get(b['type'], b['type']):22s} "
              f"peringatan {b['alerts']:3d} | ditinjau {b['reviewed']:3d} | benar {b['correct']:3d} | ketepatan {tepat}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nama", default="operator-lokal", help="nama peninjau yang dicatat")
    p.add_argument("--foto-pencatat", help="folder hasil catat_anomali.py untuk peringatan lama")
    p.add_argument("--ringkasan", action="store_true", help="tampilkan rangkuman ketepatan lalu keluar")
    a = p.parse_args()

    app = create_app()
    if a.ringkasan:
        ringkasan(app)
        return
    tz = ZoneInfo(app.config["REPORT_TIMEZONE"])
    folder = Path(a.foto_pencatat) if a.foto_pencatat else None
    with app.app_context():
        antrean = list(db.session.execute(
            select(Anomaly, Camera.name).join(Camera, Camera.id == Anomaly.camera_id)
            .where(Anomaly.review_verdict.is_(None)).order_by(Anomaly.started_at)
        ).all())
        db.session.expunge_all()
    if not antrean:
        print("Tidak ada peringatan yang menunggu ditinjau.")
        return

    import tkinter as tk

    from PIL import Image, ImageTk

    root = tk.Tk()
    root.title("CitySight - tinjau peringatan")
    gambar = tk.Label(root, bg="black")
    gambar.pack()
    keterangan = tk.Label(root, justify="left", wraplength=1000, font=("Segoe UI", 11))
    keterangan.pack(fill="x", padx=10, pady=4)
    baris = tk.Frame(root)
    baris.pack(fill="x", padx=10, pady=4)
    tk.Label(baris, text="Catatan:").pack(side="left")
    catatan = tk.Entry(baris, width=60)
    catatan.pack(side="left", padx=6)
    tk.Label(root, text="B = benar   S = salah   L = lewati   Q = selesai   "
                        "(saat menulis catatan: Ctrl+B / Ctrl+S, atau Esc lalu B / S)",
             font=("Segoe UI", 10, "bold")).pack(pady=(0, 8))
    keadaan = {"i": 0, "benar": 0, "salah": 0}

    def tampilkan():
        if keadaan["i"] >= len(antrean):
            root.destroy()
            return
        anomaly, kamera = antrean[keadaan["i"]]
        foto = anomaly_service.photo_path(anomaly.id)
        with app.app_context():
            foto = foto if foto is not None and foto.is_file() else foto_pencatat(folder, anomaly, tz)
        if foto is not None and foto.is_file():
            img = Image.open(foto)
            img.thumbnail((1000, 560))
            gambar.foto = ImageTk.PhotoImage(img)
            gambar.configure(image=gambar.foto, text="")
        else:
            gambar.configure(image="", text="(tidak ada foto)", fg="white", width=100, height=20)
        mulai = anomaly.started_at.astimezone(tz).strftime("%d-%m-%Y %H.%M.%S")
        keterangan.configure(text=f"[{keadaan['i'] + 1}/{len(antrean)}]  {kamera}  ·  "
                                  f"{JENIS.get(anomaly.type, anomaly.type)}  ·  mulai {mulai} WIB\n{anomaly.message}")
        catatan.delete(0, "end")
        gambar.focus_set()  # B/S/L langsung bekerja; klik kotak Catatan untuk menulis

    def tandai(verdict: str):
        anomaly, _ = antrean[keadaan["i"]]
        with app.app_context():
            anomaly_service.review(anomaly.id, verdict, catatan.get().strip() or None, a.nama)
        keadaan["benar" if verdict == "true" else "salah"] += 1
        lanjut()

    def lanjut():
        keadaan["i"] += 1
        tampilkan()

    def tombol(event):
        kunci = event.char.lower()
        if event.widget is catatan and kunci not in ("\r",):
            # Huruf diketik di kotak catatan; pakai Ctrl+B / Ctrl+S / Ctrl+L dari kotak catatan.
            return
        if kunci == "b":
            tandai("true")
        elif kunci == "s":
            tandai("false")
        elif kunci == "l":
            lanjut()
        elif kunci == "q":
            root.destroy()

    root.bind("<Key>", tombol)
    root.bind("<Control-b>", lambda _e: tandai("true"))
    root.bind("<Control-s>", lambda _e: tandai("false"))
    root.bind("<Control-l>", lambda _e: lanjut())
    root.bind("<Escape>", lambda _e: gambar.focus_set())
    gambar.bind("<Button-1>", lambda _e: gambar.focus_set())
    tampilkan()
    gambar.focus_set()
    root.mainloop()
    print(f"Selesai: {keadaan['benar']} benar, {keadaan['salah']} salah, "
          f"{len(antrean) - keadaan['benar'] - keadaan['salah']} belum ditinjau.")


if __name__ == "__main__":
    main()
