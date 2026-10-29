import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import { AnimatedNumber } from "@/components/motion/AnimatedNumber";
import { Reveal } from "@/components/motion/Reveal";
import { SIGER_CLIP_ID } from "@/components/siger/SigerClip";
import { SIGER_HEIGHT, SIGER_WIDTH, sigerPath } from "@/components/siger/sigerPath";
import { CAMERAS, CITY_CENTER, VEHICLE_LABELS, type CameraSample, type VehicleCounts } from "../data/cameras";
import { useSampleCounts } from "../hooks/useSampleCounts";

const EASE = [0.22, 1, 0.36, 1] as const;

function pinIcon(active: boolean) {
  return L.divIcon({
    className: "",
    iconSize: [36, 21],
    iconAnchor: [18, 21],
    html: `<svg class="camera-pin" data-active="${active}" viewBox="0 0 ${SIGER_WIDTH} ${SIGER_HEIGHT}" width="36" height="21" fill="currentColor" aria-hidden="true"><path d="${sigerPath}"/></svg>`,
  });
}

function FlyTo({ camera }: { camera: CameraSample }) {
  const map = useMap();
  const reduce = useReducedMotion();
  useEffect(() => {
    map.flyTo([camera.lat, camera.lng], 15, { duration: reduce ? 0 : 1.2 });
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
    <section id="peta" aria-label="Peta kamera" className="grid min-h-[88svh] bg-surface lg:grid-cols-2">
      {/* Left: the city map, opened like a shutter. */}
      <div className="flex items-center justify-center p-4 lg:p-10">
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
              center={CITY_CENTER}
              zoom={13}
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
                  title={`${c.code} ${c.name}`}
                  eventHandlers={{ click: () => setActiveId(c.id) }}
                />
              ))}
              <FlyTo camera={camera} />
            </MapContainer>
          </motion.div>

          {/* The place the camera watches, cut to the Siger and laid over its map. */}
          <AnimatePresence mode="wait">
            <motion.img
              key={camera.photo.src}
              src={camera.photo.src}
              alt={camera.photo.alt}
              width={600}
              height={360}
              loading="lazy"
              className="pointer-events-none absolute bottom-[4%] left-[4%] z-[500] aspect-[1000/600] w-[44%] object-cover"
              style={{ clipPath: `url(#${SIGER_CLIP_ID})`, objectPosition: camera.photo.position }}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.5, ease: EASE }}
            />
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Right: tabs, the place, its live readout, two actions. */}
      <div className="flex flex-col justify-between gap-12 px-4 pb-4 lg:py-10 lg:pr-10 lg:pl-0">
        <div role="tablist" aria-label="Pilih kamera" className="flex flex-wrap gap-x-6 gap-y-2 text-body">
          {CAMERAS.map((c) => {
            const selected = c.id === activeId;
            return (
              <button
                key={c.id}
                role="tab"
                aria-selected={selected}
                aria-controls="camera-panel"
                onClick={() => setActiveId(c.id)}
                className={`py-2 transition-colors ${selected ? "font-medium text-ink" : "text-muted hover:text-ink"}`}
              >
                <span className={selected ? "underline decoration-2 underline-offset-8" : ""}>{c.name}</span>
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
              <p className="mt-8 max-w-[34ch]">{camera.description}</p>
            </motion.div>
          </AnimatePresence>

          <Reveal order={1} className="mt-10">
            <Readout counts={counts} total={total} />
          </Reveal>
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
    <div data-ui>
      <p className="m-0 flex items-baseline gap-3">
        <span className="text-head font-medium tracking-[-0.04em]">
          <AnimatedNumber value={total} />
        </span>
        <span>kendaraan dalam frame terakhir</span>
      </p>
      <dl className="m-0 mt-5 flex flex-wrap gap-x-7 gap-y-2">
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
