/**
 * The three Seribu Wajah cameras this system watches. Coordinates come from
 * OpenStreetMap; the SD 2 Rajabasa point is approximate (the school is not on
 * OSM) and must be confirmed. Counts are samples until stage 2 reads
 * GET /api/stats/summary.
 */
export type VehicleCounts = {
  car: number;
  motorcycle: number;
  bus: number;
  truck: number;
};

export type CameraSample = {
  id: number;
  code: string;
  name: string;
  area: string;
  description: string;
  lat: number;
  lng: number;
  typical: VehicleCounts;
};

export const VEHICLE_LABELS: Record<keyof VehicleCounts, string> = {
  car: "Mobil",
  motorcycle: "Motor",
  bus: "Bus",
  truck: "Truk",
};

export const CAMERAS: CameraSample[] = [
  {
    id: 1,
    code: "CAM-01",
    name: "Depan SD 2 Rajabasa",
    area: "Jl. Z.A. Pagar Alam, Rajabasa",
    description:
      "Jalan utama dekat Terminal Rajabasa. Pagi dan siang ramai antar-jemput siswa, ditambah bus dan angkot yang keluar-masuk terminal.",
    lat: -5.3673,
    lng: 105.2325,
    typical: { car: 12, motorcycle: 34, bus: 2, truck: 2 },
  },
  {
    id: 2,
    code: "CAM-02",
    name: "Underpass Unila",
    area: "Jl. Z.A. Pagar Alam, Labuhan Ratu",
    description:
      "Jalan lintas bawah di depan Universitas Lampung. Arus dari Rajabasa menuju pusat kota lewat di sini tanpa berhenti di persimpangan.",
    lat: -5.37176,
    lng: 105.23925,
    typical: { car: 18, motorcycle: 41, bus: 1, truck: 3 },
  },
  {
    id: 3,
    code: "CAM-03",
    name: "Tugu Adipura",
    area: "Bundaran Gajah, Enggal",
    description:
      "Bundaran di jantung kota, pertemuan Jl. Raden Intan dan Jl. Ahmad Yani. Arus dari empat arah bertemu di satu lingkaran.",
    lat: -5.42229,
    lng: 105.2582,
    typical: { car: 14, motorcycle: 38, bus: 1, truck: 2 },
  },
];

/** South-west and north-east corners that hold all three cameras. */
export const CAMERA_BOUNDS: [[number, number], [number, number]] = [
  [-5.4283, 105.2265],
  [-5.3613, 105.2642],
];
