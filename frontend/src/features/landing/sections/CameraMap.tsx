import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import { AnimatedNumber } from "@/components/motion/AnimatedNumber";
import { SIGER_HEIGHT, SIGER_WIDTH, sigerPath } from "@/components/siger/sigerPath";
import { CAMERA_BOUNDS, CAMERAS, VEHICLE_LABELS, type CameraSample, type VehicleCounts } from "../data/cameras";
import { useSampleCounts } from "../hooks/useSampleCounts";

const EASE = [0.22, 1, 0.36, 1] as const;

function pinIcon(active: boolean) {
  return L.divIcon({
    className: "",
    iconSize: [30, 18],
    iconAnchor: [15, 18],
    html: `<svg class="camera-pin" data-active="${active}" viewBox="0 0 ${SIGER_WIDTH} ${SIGER_HEIGHT}" width="30" height="18" fill="currentColor" aria-hidden="true"><path d="${sigerPath}"/></svg>`,
  });
}

/** Shows all three cameras first; after the visitor picks one, flies to it. */
function FlyTo({ camera }: { camera: CameraSample }) {
  const map = useMap();
  const reduce = useReducedMotion();
  // The camera shown when the map opened; the view moves only once it changes.
  const shown = useRef(camera.id);
  useEffect(() => {
    if (camera.id === shown.current) return;
    shown.current = camera.id;
    map.flyTo([camera.lat, camera.lng], 16, { duration: reduce ? 0 : 1.2 });
  }, [camera, map, reduce]);
  return null;
}

export function CameraMap() {
  const [activeId, setActiveId] = useState(CAMERAS[0].id);
  const camera = CAMERAS.find((c) => c.id === activeId) ?? CAMERAS[0];
  const counts = useSampleCounts(camera.typical);
  const total = counts.car + counts.motorcycle + counts.bus + counts.truck;
  const icons = useMemo(() => ({ on: pinIcon(true), off: pinIcon(false) }), []);

  const next = () => {
    const index = CAMERAS.findIndex((c) => c.id === activeId);
    setActiveId(CAMERAS[(index + 1) % CAMERAS.length].id);
  };

  return (
    <section
      id="peta"
      aria-label="Peta kamera"
      className="page-x grid gap-8 bg-surface py-12 lg:grid-cols-2 lg:py-[clamp(64px,7vw,112px)]"
    >
      {/* Left: the city map, opened like a shutter. */}
      <motion.div
        className="relative aspect-square w-full overflow-hidden bg-surface-2"
        initial={{ clipPath: "inset(100% 0% 0% 0%)" }}
        whileInView={{ clipPath: "inset(0% 0% 0% 0%)" }}
        viewport={{ once: true, margin: "0px 0px -15% 0px" }}
        transition={{ duration: 1.1, ease: EASE }}
      >
        <motion.div
          className="absolute inset-0"
          initial={{ scale: 1.12 }}
          whileInView={{ scale: 1 }}
          viewport={{ once: true, margin: "0px 0px -15% 0px" }}
          transition={{ duration: 1.4, ease: EASE }}
          data-ui
        >
          <MapContainer
            bounds={CAMERA_BOUNDS}
            scrollWheelZoom={false}
            className="city-map h-full w-full"
            aria-label="Peta Kota Bandar Lampung dengan tiga titik kamera"
          >
            <TileLayer
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            {CAMERAS.map((c) => (
              <Marker
                key={c.id}
                position={[c.lat, c.lng]}
                icon={c.id === activeId ? icons.on : icons.off}
                zIndexOffset={c.id === activeId ? 1000 : 0}
                title={`${c.code} ${c.name}`}
                eventHandlers={{ click: () => setActiveId(c.id) }}
              />
            ))}
            <FlyTo camera={camera} />
          </MapContainer>
        </motion.div>
      </motion.div>

      {/* Right: tabs on the map's top edge, actions on its bottom edge. */}
      <div className="flex flex-col gap-10 lg:justify-between lg:gap-8">
        <div role="tablist" aria-label="Pilih kamera" className="flex flex-wrap gap-x-7 gap-y-1">
          {CAMERAS.map((c) => {
            const selected = c.id === activeId;
            return (
              <button
                key={c.id}
                role="tab"
                aria-selected={selected}
                aria-controls="camera-panel"
                onClick={() => setActiveId(c.id)}
                className={`py-2 text-left transition-colors ${selected ? "text-ink" : "text-muted hover:text-ink"}`}
              >
                <span className={selected ? "font-medium underline decoration-2 underline-offset-8" : ""}>{c.name}</span>
              </button>
            );
          })}
        </div>

        <div id="camera-panel" role="tabpanel" aria-live="polite">
          <AnimatePresence mode="wait">
            <motion.div
              key={camera.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.45, ease: EASE }}
            >
              <h2 className="text-head">{camera.name}</h2>
              <p className="mt-4 text-muted">
                {camera.code} · {camera.area}
              </p>
              <p className="mt-6 max-w-[40ch]">{camera.description}</p>
            </motion.div>
          </AnimatePresence>

          <Readout counts={counts} total={total} />
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Link
            to={`/masuk?kamera=${camera.id}`}
            className="flex h-[60px] items-center bg-ink px-5 text-accent-ink transition-transform active:translate-y-px lg:h-[72px]"
          >
            Pantau kamera ini
          </Link>
          <button
            type="button"
            onClick={next}
            className="flex h-[60px] items-center bg-surface-2 px-5 text-left text-ink transition-colors hover:bg-ground active:translate-y-px lg:h-[72px]"
          >
            Kamera berikutnya
          </button>
        </div>
      </div>
    </section>
  );
}

function Readout({ counts, total }: { counts: VehicleCounts; total: number }) {
  const keys = Object.keys(VEHICLE_LABELS) as (keyof VehicleCounts)[];
  return (
    <div data-ui className="mt-10">
      <p className="m-0 flex items-baseline gap-3">
        <span className="text-head font-medium tracking-[-0.04em]">
          <AnimatedNumber value={total} />
        </span>
        <span>kendaraan dalam frame terakhir</span>
      </p>
      <dl className="m-0 mt-4 flex flex-wrap gap-x-7 gap-y-2">
        {keys.map((key) => (
          <div key={key} className="flex items-baseline gap-2">
            <dd className="m-0 text-lead font-medium">
              <AnimatedNumber value={counts[key]} />
            </dd>
            <dt>{VEHICLE_LABELS[key]}</dt>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-small text-muted">Angka contoh. Data langsung tampil setelah masuk ke dasbor.</p>
    </div>
  );
}
