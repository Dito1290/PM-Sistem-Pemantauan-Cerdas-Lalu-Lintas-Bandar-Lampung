/**
 * Sample cameras for the landing page. Names, coordinates and counts are
 * placeholders until stage 2 reads GET /api/stats/summary; swap them for the
 * three Seribu Wajah cameras Diskominfo picks.
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
  photo: { src: string; alt: string; position: string };
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
    name: "Tugu Adipura",
    area: "Enggal, Tanjung Karang Pusat",
    description:
      "Bundaran di jantung kota, pertemuan Jl. Raden Intan dan Jl. Ahmad Yani. Arus dari empat arah bertemu di satu lingkaran.",
    lat: -5.4172,
    lng: 105.258,
    photo: {
      src: "/media/bundaran-tugu-adipura-bandar-lampung.jpg",
      alt: "Bundaran Tugu Adipura dengan patung gajah di bawah langit biru",
      position: "50% 40%",
    },
    typical: { car: 14, motorcycle: 38, bus: 1, truck: 2 },
  },
  {
    id: 2,
    code: "CAM-02",
    name: "Jl. Pangeran Antasari",
    area: "Kedamaian, Tanjung Karang Timur",
    description:
      "Jalan arteri timur kota dengan lampu jalan bermahkota siger. Padat pada jam berangkat dan pulang kerja.",
    lat: -5.414,
    lng: 105.273,
    photo: {
      src: "/media/jalan-pangeran-antasari-bandar-lampung-lp-29.jpg",
      alt: "Mobil dan motor melaju di Jalan Pangeran Antasari, lampu jalan bermotif siger",
      position: "50% 78%",
    },
    typical: { car: 11, motorcycle: 27, bus: 0, truck: 3 },
  },
  {
    id: 3,
    code: "CAM-03",
    name: "Jl. Ikan Hiu",
    area: "Teluk Betung Selatan",
    description:
      "Kawasan pertokoan lama dekat pelabuhan. Becak, motor, dan truk barang berbagi jalan yang sama.",
    lat: -5.448,
    lng: 105.266,
    photo: {
      src: "/media/jalan-ikan-hiu-bandar-lampung.jpg",
      alt: "Deretan becak di tepi Jalan Ikan Hiu, Teluk Betung, dengan ruko di kanan jalan",
      position: "40% 70%",
    },
    typical: { car: 6, motorcycle: 21, bus: 0, truck: 4 },
  },
];

export const CITY_CENTER: [number, number] = [-5.428, 105.262];
