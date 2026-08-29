"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useFinePointer } from "@/lib/useFinePointer";

export default function CustomCursor() {
  const [visible, setVisible] = useState(false);
  const finePointer = useFinePointer();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    // The dot/ring elements only exist after the portal renders (mounted),
    // so this effect must run AFTER the mount gate flips — at first commit
    // they're not in the DOM yet and the early return would skip attaching
    // the listeners forever (deps are empty).
    if (!mounted) return;

    const dot = document.getElementById("cursor-dot");
    const ring = document.getElementById("cursor-ring");

    if (!dot || !ring) return;

    const handleMouseMove = (e: MouseEvent) => {
      dot!.style.left = `${e.clientX}px`;
      dot!.style.top = `${e.clientY}px`;
      ring!.style.left = `${e.clientX}px`;
      ring!.style.top = `${e.clientY}px`;
      setVisible(true);
    };

    const handleMouseLeave = () => setVisible(false);
    const handleMouseEnter = () => setVisible(true);

    const handleClickableHover = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const isClickable =
        target.tagName === "A" ||
        target.tagName === "BUTTON" ||
        target.closest("a") ||
        target.closest("button");

      if (isClickable) {
        ring!.classList.add("hovering");
      } else {
        ring!.classList.remove("hovering");
      }
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseleave", handleMouseLeave);
    document.addEventListener("mouseenter", handleMouseEnter);
    document.addEventListener("mouseover", handleClickableHover);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
      document.removeEventListener("mouseenter", handleMouseEnter);
      document.removeEventListener("mouseover", handleClickableHover);
    };
  }, [mounted]);

  // No custom cursor on touch/coarse-pointer devices — the native cursor
  // (or none) is the right experience there.
  if (!finePointer || !mounted) return null;

  // Portal to <body> so the cursor's z-index lives on the topmost plane —
  // any ancestor stacking context (transform/filter/backdrop) would
  // otherwise scope it below modals and the nav.
  return createPortal(
    <>
      <div
        id="cursor-dot"
        style={{ display: visible ? "block" : "none" }}
      />
      <div
        id="cursor-ring"
        style={{ display: visible ? "block" : "none" }}
      />
    </>,
    document.body,
  );
}
