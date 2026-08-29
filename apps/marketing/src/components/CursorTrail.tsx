"use client";

import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Smile } from "lucide-react";
import { useFinePointer } from "@/lib/useFinePointer";

const messageStyles: React.CSSProperties = {
  position: "fixed",
  padding: "12px",
  backgroundColor: "rgba(31, 41, 55, 0.95)",
  color: "white",
  borderRadius: "16px",
  fontSize: "14px",
  pointerEvents: "none",
  display: "flex",
  alignItems: "center",
  gap: "8px",
  boxShadow:
    "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
  border: "1px solid rgba(75, 85, 99, 0.4)",
  zIndex: 1000,
  whiteSpace: "nowrap",
};

const iconStyles: React.CSSProperties = {
  width: "16px",
  height: "16px",
  color: "#FCD34D",
};

type CursorMessageProps = {
  x: number;
  y: number;
};

const CursorMessage = ({ x, y }: CursorMessageProps) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.95, y: 16 }}
    animate={{
      opacity: 1,
      scale: 1,
      y: 0,
      transition: {
        type: "spring",
        duration: 0.4,
        bounce: 0.15,
      },
    }}
    exit={{ opacity: 0, scale: 0.95, y: -12 }}
    transition={{
      type: "spring",
      duration: 0.2,
      bounce: 0,
    }}
    style={{
      ...messageStyles,
      left: x + 20,
      top: y - 40,
    }}
  >
    <Smile style={iconStyles} />
    <span>Cool effect huh! we LOVE IT TOO! 😏</span>
  </motion.div>
);

type CursorTrailAnimationProps = {
  totalSegments?: number;
  lineColor?: string;
  maxLineWidth?: number;
  isActive?: boolean;
  movementThreshold?: number;
  timeWindow?: number;
  messageDuration?: number;
};

export default function CursorTrailAnimation({
  totalSegments = 20,
  lineColor = "#6c63ff",
  maxLineWidth = 8,
  isActive = true,
  movementThreshold = 4000,
  timeWindow = 500,
  messageDuration = 3000,
}: CursorTrailAnimationProps) {
  const finePointer = useFinePointer();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const [segments, setSegments] = useState<
    Array<{ x: number; y: number }>
  >(Array(totalSegments).fill({ x: 0, y: 0 }));
  const [showMessage, setShowMessage] = useState(false);
  const lastMoveTimeRef = useRef(Date.now());
  const lastPositionRef = useRef({ x: 0, y: 0 });
  const requestRef = useRef<number | undefined>(undefined);
  const movementHistoryRef = useRef<
    Array<{ timestamp: number; distance: number }>
  >([]);

  const updateSegments = () => {
    const currentTime = Date.now();
    const timeSinceLastMove = currentTime - lastMoveTimeRef.current;
    const contractSpeed = timeSinceLastMove > 100 ? 0.3 : 0.5;

    setSegments((prevSegments) => {
      const newSegments = [...prevSegments];
      for (let i = 1; i < totalSegments; i++) {
        newSegments[i] = {
          x:
            newSegments[i].x +
            (newSegments[i - 1].x - newSegments[i].x) * contractSpeed,
          y:
            newSegments[i].y +
            (newSegments[i - 1].y - newSegments[i].y) * contractSpeed,
        };
      }
      return newSegments;
    });

    requestRef.current = requestAnimationFrame(updateSegments);
  };

  const checkMovementIntensity = (
    currentTime: number,
    distance: number
  ): boolean => {
    movementHistoryRef.current.push({
      timestamp: currentTime,
      distance,
    });

    const cutoffTime = currentTime - timeWindow;
    movementHistoryRef.current = movementHistoryRef.current.filter(
      (move) => move.timestamp >= cutoffTime
    );

    const totalMovement = movementHistoryRef.current.reduce(
      (sum, move) => sum + move.distance,
      0
    );

    return totalMovement > movementThreshold;
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isActive) {
        const currentTime = Date.now();

        const distanceX = e.clientX - lastPositionRef.current.x;
        const distanceY = e.clientY - lastPositionRef.current.y;
        const distance = Math.sqrt(
          distanceX * distanceX + distanceY * distanceY
        );

        if (
          checkMovementIntensity(currentTime, distance) &&
          !showMessage
        ) {
          setShowMessage(true);
          setTimeout(() => {
            setShowMessage(false);
            movementHistoryRef.current = [];
          }, messageDuration);
        }

        setSegments((prevSegments) => {
          const newSegments = [...prevSegments];
          newSegments[0] = { x: e.clientX, y: e.clientY };
          return newSegments;
        });

        lastMoveTimeRef.current = currentTime;
        lastPositionRef.current = { x: e.clientX, y: e.clientY };
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    requestRef.current = requestAnimationFrame(updateSegments);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [isActive, showMessage, timeWindow, movementThreshold, messageDuration]);

  // Desktop-only delight — never render on touch/coarse-pointer devices.
  if (!finePointer || !mounted) return null;

  // Portal to <body> so the trail sits on the topmost z-plane (no ancestor
  // stacking context can scope it below modals/nav).
  return createPortal(
    <span style={{ zIndex: 9997 }}>
      <svg
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          height: "100%",
          width: "100%",
          zIndex: 9997,
          userSelect: "none",
          pointerEvents: "none",
        }}
      >
        {segments.slice(0, -1).map((segment, i) => (
          <motion.line
            key={`trail-segment-${i}`}
            x1={segment.x}
            y1={segment.y}
            x2={segments[i + 1].x}
            y2={segments[i + 1].y}
            stroke={lineColor}
            strokeWidth={maxLineWidth * (1 - i / totalSegments)}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <AnimatePresence>
        {showMessage && segments[0].x && segments[0].y && (
          <CursorMessage x={segments[0].x} y={segments[0].y} />
        )}
      </AnimatePresence>
    </span>,
    document.body,
  );
}
