"use client";

import { useEffect, useState } from "react";

/**
 * True when the device has hover capability (mouse/trackpad).
 * Uses `(hover: hover)` — NOT `(pointer: fine)` — because touchscreen
 * laptops report `pointer: coarse` even when a mouse is present, which
 * would wrongly hide cursor effects. `hover: none` is true only for
 * phones/tablets where the touchscreen is the primary pointer.
 * Returns false during SSR/first client paint to avoid hydration mismatch.
 */
export function useFinePointer(): boolean {
  const [fine, setFine] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(hover: hover)");
    const update = () => setFine(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return fine;
}
