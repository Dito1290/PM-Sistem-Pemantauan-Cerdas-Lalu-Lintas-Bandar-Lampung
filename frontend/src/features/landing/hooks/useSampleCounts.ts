import { useEffect, useState } from "react";
import type { VehicleCounts } from "../data/cameras";

const TICK_MS = 1400;

function vary(typical: VehicleCounts): VehicleCounts {
  const around = (n: number) => Math.max(0, Math.round(n * (0.75 + Math.random() * 0.5)));
  return {
    car: around(typical.car),
    motorcycle: around(typical.motorcycle),
    bus: Math.random() < 0.15 ? typical.bus + 1 : typical.bus,
    truck: around(typical.truck),
  };
}

/**
 * Sample per-frame counts that move around a camera's typical traffic.
 * Stage 2 replaces this with the SSE feed from /api/stream/detections.
 */
export function useSampleCounts(typical: VehicleCounts): VehicleCounts {
  const [counts, setCounts] = useState(typical);

  useEffect(() => {
    setCounts(typical);
    const id = window.setInterval(() => setCounts(vary(typical)), TICK_MS);
    return () => window.clearInterval(id);
  }, [typical]);

  return counts;
}
