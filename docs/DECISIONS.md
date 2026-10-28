# Catatan Keputusan

## 1. Model YOLO (2026-10-28)

| | |
|---|---|
| File | `yolo26n.pt` (YOLO26n, bobot COCO, belum dilatih ulang) |
| Versi Ultralytics saat diuji | 8.4.191 |
| SHA-256 | `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef` |
| Lokasi di server | `backend/models/yolo.pt` (tidak masuk git, lihat `.gitignore`) |

Cara mendapatkan file, dari folder `backend` dengan venv aktif:

```bash
python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"
move yolo26n.pt models\yolo.pt        # Linux/macOS: mv yolo26n.pt models/yolo.pt
certutil -hashfile models\yolo.pt SHA256   # Linux/macOS: sha256sum models/yolo.pt
```

Pastikan SHA-256 sama dengan tabel di atas. Kalau model diganti (misalnya hasil fine tuning), perbarui tabel ini.

## 2. Pengaturan deteksi

Diukur dengan `VehicleDetector` backend pada video uji Malioboro (300 gambar) dan Hanoi (204 gambar), 5 gambar per detik, CPU i5-12450HX. Angka adalah rata-rata kendaraan terdeteksi per gambar. Video ini bukan CCTV Bandar Lampung, jadi hanya untuk uji fungsi. Akurasi tetap harus diukur di uji AI-01.

| Video | imgsz | conf | agnostic NMS | mobil | motor | bus | truk | total | ms/gambar |
|---|---|---|---|---|---|---|---|---|---|
| Malioboro | 640 | 0,70 | ya | 0,66 | 0,10 | 0,10 | 0,00 | 0,86 | 56 |
| Malioboro | 640 | 0,25 | ya | 2,10 | 1,08 | 0,18 | 0,09 | 3,45 | 64 |
| Malioboro | 640 | 0,25 | tidak | 2,16 | 1,09 | 0,19 | 0,22 | 3,66 | 58 |
| Malioboro | 960 | 0,25 | ya | 1,89 | 1,67 | 0,22 | 0,14 | 3,92 | 78 |
| Hanoi | 640 | 0,70 | ya | 0,28 | 0,00 | 0,06 | 0,00 | 0,34 | 74 |
| Hanoi | 640 | 0,25 | ya | 2,06 | 0,69 | 0,33 | 0,03 | 3,11 | 62 |
| Hanoi | 960 | 0,25 | ya | 1,99 | 1,24 | 0,37 | 0,04 | 3,64 | 87 |

Keputusan sementara:

1. **`YOLO_CONFIDENCE=0.70` dipertahankan** karena nilai proposal. Catatan: pada nilai ini hampir semua motor tidak terdeteksi (0,10 per gambar di Malioboro, 0 di Hanoi), sedangkan 0,25 menangkap 4 kali (Malioboro) sampai 9 kali (Hanoi) lebih banyak kendaraan. Nilai akhir ditentukan bersama dosen setelah uji AI-01 pada rekaman Bandar Lampung.
2. **`YOLO_AGNOSTIC_NMS=true` dipertahankan** sesuai proposal Bab 5.2.1 d. Mematikannya hampir tidak menambah motor; tambahannya sebagian besar label truk ganda pada mobil yang sama.
3. **`YOLO_IMGSZ=640` dipertahankan.** Ukuran 960 menambah motor terdeteksi sekitar 55% di Malioboro, dengan waktu proses sekitar 1,2 sampai 1,4 kali. Layak dipakai kalau worker memakai GPU (`YOLO_DEVICE=0`).

## 3. Pengambilan gambar dari stream HLS

Sebelumnya `StreamReader` mengambil gambar menurut jam dinding. Stream HLS mengirim satu potongan beberapa detik sekaligus, sehingga hanya sekitar 2 gambar per potongan yang terambil. Hasil ukur pada siaran HLS uji selama 60 detik: **0,42 gambar per detik** (target 5).

Sekarang gambar dilepas mengikuti kecepatan asli video seperti pemutar siaran, lalu diambil tiap `FRAME_INTERVAL_SECONDS`. Hasil ukur setelah perubahan: **5,00 gambar per detik** pada siaran HLS yang sama dan 5,05 pada file video. Akibatnya gambar tertunda beberapa detik dari siaran, tetapi tidak makin tertinggal karena pembacaan disinkronkan ulang bila tertinggal lebih dari 2 detik.

## 4. Catatan lingkungan

1. `pip install -r requirements-ml.txt` membuat Ultralytics memasang `opencv-python` 5.0, yang menimpa `opencv-python-headless==4.11.0.86` di folder `cv2` yang sama. Setelah instal, jalankan `pip install --force-reinstall --no-deps opencv-python-headless==4.11.0.86` supaya versi yang dikunci yang terpakai.
2. Di Windows, path video lokal seperti `C:\video\a.mp4` sebelumnya dianggap URL dengan skema `c`, sehingga video tidak diulang dan pengujian `test_opencv_file_source_sampled_at_five_fps` gagal. Sudah diperbaiki di `pipeline/sources.py`.
