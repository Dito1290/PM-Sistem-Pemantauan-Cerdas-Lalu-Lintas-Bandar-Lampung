# Catatan Keputusan

## 1. Model YOLO (2026-10-28)

| | |
|---|---|
| File | `yolo26m.pt` (YOLO26m, bobot COCO, belum dilatih ulang). Diganti dari YOLO26n pada 2026-11-02, lihat bagian 6 |
| Versi Ultralytics saat diuji | 8.4.191 |
| SHA-256 | `401cea9ab23ad19246ff7744859816bc599f350e93c9dd30367b6f0a0745d0b7` |
| Model sebelumnya | `yolo26n.pt`, SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef` |
| Lokasi di server | `backend/models/yolo.pt` (tidak masuk git, lihat `.gitignore`) |

Cara mendapatkan file, dari folder `backend` dengan venv aktif:

```bash
python -c "from ultralytics import YOLO; YOLO('yolo26m.pt')"
move yolo26m.pt models\yolo.pt        # Linux/macOS: mv yolo26m.pt models/yolo.pt
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

Keputusan sementara (diperbarui di bagian 6 setelah diuji pada rekaman Seribu Wajah):

1. **`YOLO_CONFIDENCE=0.70` dipertahankan** karena nilai proposal. Catatan: pada nilai ini hampir semua motor tidak terdeteksi (0,10 per gambar di Malioboro, 0 di Hanoi), sedangkan 0,25 menangkap 4 kali (Malioboro) sampai 9 kali (Hanoi) lebih banyak kendaraan. Nilai akhir ditentukan bersama dosen setelah uji AI-01 pada rekaman Bandar Lampung.
2. **`YOLO_AGNOSTIC_NMS=true` dipertahankan** sesuai proposal Bab 5.2.1 d. Mematikannya hampir tidak menambah motor; tambahannya sebagian besar label truk ganda pada mobil yang sama.
3. **`YOLO_IMGSZ=640` dipertahankan.** Ukuran 960 menambah motor terdeteksi sekitar 55% di Malioboro, dengan waktu proses sekitar 1,2 sampai 1,4 kali. Layak dipakai kalau worker memakai GPU (`YOLO_DEVICE=0`).

## 3. Pengambilan gambar dari stream HLS

Sebelumnya `StreamReader` mengambil gambar menurut jam dinding. Stream HLS mengirim satu potongan beberapa detik sekaligus, sehingga hanya sekitar 2 gambar per potongan yang terambil. Hasil ukur pada siaran HLS uji selama 60 detik: **0,42 gambar per detik** (target 5).

Sekarang gambar dilepas mengikuti kecepatan asli video seperti pemutar siaran, lalu diambil tiap `FRAME_INTERVAL_SECONDS`. Hasil ukur setelah perubahan: **5,00 gambar per detik** pada siaran HLS yang sama dan 5,05 pada file video. Akibatnya gambar tertunda beberapa detik dari siaran, tetapi tidak makin tertinggal karena pembacaan disinkronkan ulang bila tertinggal lebih dari 2 detik.

## 4. Catatan lingkungan

1. `pip install -r requirements-ml.txt` membuat Ultralytics memasang `opencv-python` 5.0, yang menimpa `opencv-python-headless==4.11.0.86` di folder `cv2` yang sama. Setelah instal, jalankan `pip install --force-reinstall --no-deps opencv-python-headless==4.11.0.86` supaya versi yang dikunci yang terpakai.
2. Di Windows, path video lokal seperti `C:\video\a.mp4` sebelumnya dianggap URL dengan skema `c`, sehingga video tidak diulang dan pengujian `test_opencv_file_source_sampled_at_five_fps` gagal. Sudah diperbaiki di `pipeline/sources.py`.

## 5. Kamera Seribu Wajah lewat pemutar web (2026-11-02)

Permintaan langsung ke stream Seribu Wajah dijawab 401, tetapi halaman publik https://seribuwajah.bandarlampungkota.go.id/list memutar semua kamera untuk pengunjung tanpa login. Atas saran dosen pembimbing, ingest membuka halaman itu dengan browser headless (Playwright) seperti pengunjung biasa, mencari kamera, membuka monitor live, lalu menyalin gambar dari elemen `<video>` (1920x1080). Kodenya ada di `pipeline/browser_capture.py`. Bagian lain (pengambilan sampel, reconnect, Redis, Celery, YOLO) tidak berubah.

`stream_url` kamera ditulis dengan id kamera Seribu Wajah, misalnya `https://seribuwajah.bandarlampungkota.go.id/list?cctv=313`. Id diambil dari daftar kamera yang dimuat halaman tersebut.

| Kamera | Nama di Seribu Wajah | `stream_url` |
|---|---|---|
| CAM-01 | DEPAN SD 2 RAJABASA (PTZ) | `.../list?cctv=313` |
| CAM-02 | UNDERPASS UNILA (PTZ) | `.../list?cctv=310` |
| CAM-03 | TUGU ADIPURA 1 (PTZ) | `.../list?cctv=31` |

Instalasi di mesin ingest: `pip install -r requirements.txt`, lalu `playwright install chromium`. Alternatifnya, isi `BROWSER_CHANNEL=chrome` supaya ingest memakai Google Chrome yang sudah terpasang.

Hasil ukur di laptop i5-12450HX (CPU, tanpa GPU), 3 kamera sekaligus bersama satu worker Celery, `FRAME_INTERVAL_SECONDS=0.2`:

| | Hasil |
|---|---|
| Waktu membuka monitor | 6 sampai 8 detik per kamera |
| Gambar masuk antrean, 1 kamera saja | 5,0 per detik |
| Gambar masuk antrean, 3 kamera | 2,7 sampai 4,1 per detik per kamera |
| Hasil deteksi tersimpan | sekitar 1,5 per detik per kamera (worker CPU, sekitar 0,35 detik per tugas) |
| Putus sambung | 2 kali dalam sekitar 6 menit, masing-masing pulih sendiri dalam sekitar 13 detik |

Catatan:

1. Tiga browser dan YOLO berbagi CPU yang sama, sehingga target 5 gambar per detik per kamera belum tercapai saat 3 kamera berjalan bersamaan. Worker dengan GPU atau mesin terpisah untuk ingest akan membantu.
2. Ketiga kamera adalah PTZ, sehingga arah pandangnya bisa diubah operator.
3. Cara ini hanya memakai halaman publik. Izin resmi dari Diskominfo tetap perlu diurus sebelum sistem dipakai terus-menerus.

## 6. Deteksi motor pada CCTV Seribu Wajah (2026-11-02)

Dengan pengaturan lama (YOLO26n, `YOLO_IMGSZ=640`, `YOLO_CONFIDENCE=0.70`) hampir tidak ada motor yang terdeteksi di ketiga kamera. Pengujian memakai 60 gambar dari kamera 1-3 (20 per kamera, jarak 6 detik, siang hari). Pada 6 gambar, setiap kandidat motor dari semua pengaturan diperiksa manual, sehingga didapat 36 motor acuan. Motor yang parkir di area parkir Tugu Adipura tidak dihitung.

| Model | imgsz | conf | Motor tertangkap | Deteksi motor yang benar | ms/gambar CPU | ms/gambar GPU RTX 3050 |
|---|---|---|---|---|---|---|
| YOLO26n | 640 | 0,70 | 0% | - | 41 | 13 |
| YOLO26n | 640 | 0,35 | 19% | 100% | 41 | 13 |
| YOLO26n | 1280 | 0,25 | 42% | 94% | 128 | 17 |
| YOLO26s | 960 | 0,25 | 58% | 95% | 187 | 17 |
| YOLO26m | 960 | 0,70 | 25% | 100% | 480 | 35 |
| **YOLO26m** | **960** | **0,25** | **69%** | **93%** | 480 | **35** |
| YOLO26m | 1280 | 0,25 | 75% | 96% | 890 | 57 |

Hasil deteksi GPU sama persis dengan CPU; yang berbeda hanya waktunya. Motor acuan berasal dari kandidat model-model ini, jadi motor yang terlewat oleh semua model tidak terhitung dan persentase "tertangkap" cenderung terlalu tinggi. Angka ini perkiraan awal, bukan pengganti uji AI-01.

Keputusan:

1. **Model YOLO26m, `YOLO_IMGSZ=960`, `YOLO_CONFIDENCE=0.25`, `YOLO_DEVICE=0`.** Motor kecil di gambar 1920x1080 hilang bila gambar diperkecil ke 640, dan model nano tidak cukup kuat. Menurunkan conf saja tidak cukup (YOLO26n tetap 19%). Ini menyimpang dari proposal (Tabel 20 hanya varian n, conf 0,70), sehingga perlu persetujuan dosen.
2. **Worker harus memakai GPU.** Batas waktu 3 kamera x 5 gambar per detik adalah sekitar 66 ms per gambar. YOLO26m 960 butuh 35 ms di RTX 3050, sedangkan di CPU sekitar 480 ms. Cara memasang torch versi CUDA ada di `requirements-ml.txt`. Ukuran 1280 (57 ms) sedikit lebih akurat tetapi terlalu dekat dengan batas.

Hasil uji menyeluruh 3 kamera selama 2 menit (sekitar pukul 17.00, ingest Playwright + worker GPU di satu laptop):

| | Hasil |
|---|---|
| Hasil deteksi tersimpan | 2,4-2,5 per detik per kamera (sebelumnya 1,5 dengan CPU) |
| Waktu rata-rata satu tugas worker | 0,12 detik |
| Rata-rata motor per gambar | kamera 1: 20,7; kamera 2: 4,3; kamera 3: 4,1 |

Kamera 1 tinggi karena jam pulang sekolah: banyak motor penjemput menunggu atau parkir di tepi jalan depan SD 2 Rajabasa, dan semuanya ikut terhitung karena definisi hitungan adalah "kendaraan yang terlihat di gambar". Bila yang diinginkan hanya kendaraan di lajur jalan, perlu area hitung (ROI) per kamera.

Sisa motor yang terlewat sebagian besar motor bergerombol (terbaca satu kotak), motor kecil di kejauhan, dan motor yang tertutup mobil. Perbaikan berikutnya adalah fine tuning dengan gambar Seribu Wajah yang dikumpulkan lewat ingest Playwright, lalu diberi label.

## 7. Satu gambar per menit per kamera (2026-11-02)

Atas saran dosen pembimbing, ingest mengambil satu gambar per kamera setiap 60 detik (`FRAME_INTERVAL_SECONDS=60`). Gambar langsung dideteksi worker dan hasilnya disimpan ke PostgreSQL, lalu sistem menunggu menit berikutnya. Sebelumnya nilainya 0,2 (5 gambar per detik, sesuai proposal).

Pada percobaan pertama, monitor Seribu Wajah dibiarkan terbuka, sehingga tiga Chrome terus memutar video 1080p di antara pengambilan gambar. Karena itu `BrowserCapture` sekarang punya mode satu gambar: bila `FRAME_INTERVAL_SECONDS` 30 detik atau lebih, monitor dibuka hanya untuk mengambil satu gambar lalu ditutup lagi. Membuka monitor butuh 6-15 detik, sehingga jarak antar-gambar 49-76 detik dengan rata-rata 60 detik. Worker juga menjalankan satu deteksi kosong saat mulai (`celery_worker.py`), karena deteksi pertama di GPU lambat (sekitar 30 detik) dan membuat gambar pertama basi.

Hasil uji 3 kamera selama sekitar 4 menit (YOLO26m, GPU). Beban CPU laptop tanpa CitySight saat itu sudah sekitar 44% karena aplikasi lain, sehingga angka CPU hanya perbandingan kasar:

| | 5 gambar per detik | 1 gambar per menit, monitor terbuka | 1 gambar per menit, mode satu gambar |
|---|---|---|---|
| Baris tersimpan per kamera | sekitar 2,4 per detik | 1 per menit | 1 per menit (jarak 49-76 detik) |
| Baris per hari untuk 3 kamera | sekitar 620 ribu | 4.320 | 4.320 |
| Beban CPU laptop | 51-79% | rata-rata 45% | rata-rata 27% (2-54%) |
| Data pertama setelah dinyalakan | - | 1-2 menit | 10-18 detik |

Catatan:

1. Nyalakan worker sebelum ingest. Worker butuh sekitar 15 detik untuk siap; gambar yang menunggu lebih dari `FRAME_MAX_AGE_SECONDS` (5 detik) dibuang sebagai gambar basi.
2. Waktu yang disimpan adalah saat gambar diambil, bukan awal menit.
3. Hitungan tetap berarti "kendaraan yang terlihat di satu gambar". Satu gambar per menit adalah sampel, bukan jumlah kendaraan yang lewat dalam satu menit.
4. Jumlah baris per hari yang jauh lebih kecil memudahkan pemakaian basis data cloud (lihat rancangan arsitektur cloud).


## 8. Indikasi anomali (2026-11-05)

Dengan satu gambar per menit, kendaraan tidak bisa dilacak dan kejadian seperti tabrakan (beberapa detik) hampir pasti terlewat. Model YOLO juga hanya mengenal benda, bukan kejadian. Karena itu backend tidak mendeteksi "kecelakaan", tetapi **indikasi anomali** dari akibatnya. Operator yang memastikan lewat CCTV.

| Jenis (`type`) | Aturan | Kemungkinan artinya |
|---|---|---|
| `high_density` | Semua gambar dalam 4 menit terakhir (minimal 3 gambar) berisi kendaraan sebanyak minimal `max(15, 2 x biasanya)`. Indikasi selesai bila semua gambar dalam 4 menit terakhir di bawah ambang yang memicunya. | Macet, kecelakaan, acara, jalan ditutup |
| `camera_offline` | Kamera aktif tidak punya gambar yang terdeteksi selama 5 menit. Penyebab dibaca dari status stream di Redis (ingest mati, sumber CCTV gagal dibuka, atau worker gagal). Selesai saat gambar masuk lagi. | Kamera atau server Seribu Wajah mati, layanan CitySight mati |

"Biasanya" adalah median `hourly_stats.avg_vehicle` kamera itu selama 14 hari terakhir pada jam yang sama (WIB). Bila jam yang sama belum punya minimal 3 jam data, dipakai median semua jam. Bila keduanya kurang dari 3 jam data, `high_density` tidak dicek. Jam yang sedang berjalan tidak ikut dihitung, supaya kemacetan yang sedang terjadi tidak menaikkan ambangnya sendiri. Semua angka bisa diubah lewat `ANOMALY_*` di `.env`.

Pengecekan:

1. `high_density` dicek worker setelah setiap gambar tersimpan. Gagalnya pengecekan tidak membatalkan hasil deteksi.
2. `camera_offline` dicek Celery Beat setiap menit (`citysight.check_anomalies`, antrean `stats`). Selama 5 menit pertama setelah worker menyala, pengecekan hanya menutup indikasi, karena kamera belum sempat mengirim gambar. Kamera yang dinonaktifkan atau dihapus menutup indikasinya.
3. Hanya ada satu indikasi aktif per kamera per jenis (indeks unik `uq_anomalies_active`).

Peringatan dikirim ke `GET /api/anomalies`, ke stream SSE (`event: anomaly`), dan ke Telegram bila `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` diisi. Untuk `high_density`, Telegram juga menerima foto gambar yang memicunya.

Batasan:

1. `hourly_stats` hanya terisi bila Celery Beat berjalan, atau diisi manual dengan `flask --app wsgi stats aggregate --from ... --to ...`. Tanpa itu, `high_density` tidak punya pembanding.
2. Hitungan "kendaraan terlihat" masih termasuk motor parkir dan penjemput (lihat bagian 6), dan kamera PTZ yang berputar atau zoom mengubah jumlah kendaraan yang terlihat. Keduanya bisa memicu `high_density` palsu.
3. Ambang 2x dan minimal 15 kendaraan adalah tebakan awal dari data 2 November, belum diuji pada kejadian nyata.

## 9. Stream tetap berjalan, penyimpanan tetap satu baris per menit (2026-11-05)

Bagian 7 ternyata salah tafsir: yang dimaksud satu per menit adalah **penyimpanan** ke PostgreSQL, bukan pengambilan gambar. Dengan mode satu gambar, monitor Seribu Wajah ditutup di antara gambar, sehingga tidak ada tampilan langsung dan kejadian di antara dua gambar tidak terlihat.

Sekarang:

| | Bagian 7 | Sekarang |
|---|---|---|
| `FRAME_INTERVAL_SECONDS` | 60 (mode satu gambar) | **0,2** (monitor terbuka terus, target 5 gambar per detik) |
| Deteksi YOLO | 1 per menit | **Setiap gambar yang diambil** |
| SSE `event: detection` | 1 per menit | Setiap gambar, dengan `"stored": true/false` |
| Baris `detections` | 1 per kamera per menit | **Tetap 1 per kamera per menit** (`DETECTION_SAVE_INTERVAL_SECONDS=60`) |

Yang disimpan adalah gambar pertama yang terdeteksi pada setiap menit jam dinding per kamera (kunci Redis `camera:saved:<id>:<menit>`, atomik bila worker lebih dari satu). Arti hitungan tidak berubah: kendaraan yang terlihat di satu gambar. Statistik per jam dan indikasi anomali (bagian 8) tetap memakai baris yang tersimpan. Bila penyimpanan gagal karena basis data, kunci dilepas supaya gambar berikutnya di menit yang sama dicoba lagi.

Akibatnya beban kembali seperti 5 gambar per detik: worker perlu GPU untuk YOLO26m 960 (bagian 6). Di CPU (sekitar 480 ms per gambar) hanya sekitar 2 gambar per detik untuk satu kamera, sehingga rancangan VM cloud tanpa GPU perlu ditinjau ulang. Mode satu gambar tetap tersedia dengan `FRAME_INTERVAL_SECONDS` 30 atau lebih.

Hasil ukur 3 kamera sekaligus (2026-11-05 sekitar 15.45, YOLO26m 960 di GPU RTX 3050, 40 detik):

| Kamera | Diambil dari stream | Dideteksi, worker `--pool=solo` | Dideteksi, worker `--pool=threads --concurrency 3` |
|---|---|---|---|
| 1 | 4,3-4,6 fps | 2,7 fps | 3,9 fps |
| 2 | 3,9-4,1 fps | 2,6 fps | 4,0 fps |
| 3 | 4,9-5,0 fps | 2,7 fps | 4,3 fps |

Dengan satu thread, worker mengerjakan frame ketiga kamera bergantian (sekitar 8 frame per detik total), sehingga menjadi batas. Dengan 3 thread (satu model YOLO per thread, VRAM sekitar 1,4 GB), deteksi hampir menyamai kecepatan pemutar web Seribu Wajah, yang kini menjadi batasnya. Setiap kamera tetap menyimpan satu baris per menit. Beban CPU laptop 86-91%, sebagian besar karena tiga Chrome memutar video 1080p dan aplikasi lain. Jalankan worker dengan:

    celery -A celery_worker.celery worker -Q detection,stats --pool=threads --concurrency 3 -l info

Tampilan langsung: setelah setiap deteksi, worker menimpa hash Redis `camera:live:<id>` (berlaku 30 detik) berisi JPEG gambar itu dan kotak yang ia hitung (`category`, `conf`, `box` [x1, y1, x2, y2] relatif 0..1, lihat `pipeline/live_frame.py`). Penampil cukup menggambar kotak itu tanpa menjalankan YOLO kedua, sehingga kotak di layar sama persis dengan yang dihitung. Dengan penampil terbuka, deteksi tetap 3,6-4,0 fps per kamera untuk 3 kamera (sebelumnya turun ke sekitar 2,7 fps karena penampil menjalankan YOLO sendiri). Data yang sama bisa dipakai untuk tampilan live di dashboard.
