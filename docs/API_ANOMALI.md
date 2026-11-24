# API Indikasi Anomali (untuk dashboard)

Semua endpoint butuh login (header `Authorization: Bearer <token>` dari `POST /api/auth/login`), peran `admin` atau `operator`. Waktu dalam UTC (ISO 8601, akhiran `Z`); tampilkan dalam WIB.

Anomali adalah **indikasi** untuk operator, bukan kejadian yang pasti. Jenisnya (`type`):

| `type` | Arti | Kapan muncul |
|---|---|---|
| `high_density` | Kepadatan tidak wajar | 3 sampel per menit berturut-turut jauh di atas kebiasaan kamera itu |
| `camera_offline` | Kamera tidak mengirim gambar | 5 menit tanpa gambar |
| `stopped_vehicle` | Kendaraan berhenti tidak wajar | Kendaraan diam 2 menit atau lebih di lajur sementara lalu lintas searah bergerak |
| `people_on_road` | Orang di badan jalan | Minimal 3 orang (bukan pengendara) bertahan 30 detik di satu titik di lajur |

## Daftar anomali

`GET /api/anomalies?status=active&camera_id=2&type=people_on_road&review=pending&page=1&per_page=50`

Semua parameter opsional. `status`: `active` | `ended`. `review`: `pending` (belum ditinjau) | `true` | `false`.

```json
{
  "data": [
    {
      "id": 42,
      "camera_id": 2,
      "camera_name": "Underpass Unila",
      "type": "people_on_road",
      "status": "active",
      "started_at": "2026-11-24T12:41:05Z",
      "ended_at": null,
      "message": "Orang di badan jalan: 4 orang berada di lajur jalan selama sekitar 35 detik. ...",
      "details": {"people": 4, "seconds": 35, "boxes": [[0.61, 0.38, 0.65, 0.52]], "min_people": 3},
      "photo_url": "/api/anomalies/42/photo",
      "review": null
    }
  ],
  "meta": {"page": 1, "per_page": 50, "total": 1, "pages": 1, "semantics": "indication"}
}
```

`details.boxes` dan `details.vehicles[].box` berupa `[x1, y1, x2, y2]` relatif terhadap gambar (0..1).

## Foto peringatan

`GET /api/anomalies/<id>/photo` mengembalikan JPEG yang diambil saat peringatan dimulai, dengan kotak merah pada kendaraan atau orang yang dimaksud. Bila `photo_url` bernilai `null`, foto tidak tersedia (misalnya `camera_offline`). Karena butuh header login, ambil fotonya dengan `fetch` lalu tampilkan sebagai `blob:` URL; `<img src>` biasa tidak membawa header.

## Tombol konfirmasi operator

`POST /api/anomalies/<id>/review`

```json
{"verdict": "false", "note": "parkir nongkrong"}
```

- `verdict`: `"true"` bila peringatan memang perlu perhatian (kecelakaan, mogok, kerumunan, dll.), `"false"` bila peringatan palsu.
- `note`: opsional, maksimal 500 karakter.
- Boleh dikirim ulang untuk mengubah penilaian; yang terakhir yang dipakai.
- Jawaban: anomali yang sudah diperbarui, dengan `review`:
  `{"verdict": "false", "note": "parkir nongkrong", "by": "operator1", "at": "2026-11-24T12:45:00Z"}`.

Saran tampilan: tombol **✅ Benar** dan **❌ Salah** di setiap kartu peringatan, kotak catatan opsional, dan filter "belum ditinjau".

## Rangkuman ketepatan

`GET /api/anomalies/review-summary?from=2026-11-01&to=2026-11-30` (tanggal WIB, bawaan 30 hari terakhir)

```json
{
  "data": [
    {"camera_id": 2, "camera_name": "Underpass Unila", "type": "people_on_road",
     "alerts": 12, "reviewed": 10, "correct": 8, "precision": 0.8}
  ],
  "meta": {"from": "2026-11-01", "to": "2026-11-30", "timezone": "Asia/Jakarta", "precision": "correct / reviewed"}
}
```

`precision` bernilai `null` bila belum ada yang ditinjau.

## Realtime (SSE)

`GET /api/stream/detections?access_token=<token>` mengirim `event: anomaly` dengan `data` berisi objek anomali seperti di atas, ditambah `"change"`:

| `change` | Kapan |
|---|---|
| `started` | Peringatan baru |
| `ended` | Peringatan selesai (`details.end_reason` berisi alasannya) |
| `reviewed` | Ada operator yang menandai benar/salah (perbarui kartu di semua layar) |
