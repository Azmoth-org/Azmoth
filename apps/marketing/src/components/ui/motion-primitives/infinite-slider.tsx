'use client'
import { cn } from '@/lib/utils'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

export type InfiniteSliderProps = {
  children: ReactNode
  gap?: number
  speed?: number
  speedOnHover?: number
  direction?: 'horizontal' | 'vertical'
  reverse?: boolean
  className?: string
}

/**
 * Pure-CSS infinite marquee (compositor-driven — no JS per frame, unlike the
 * framer-motion version it replaces). The track holds two copies of the
 * children and animates translate3d(-50%) linearly; a CSS variable carries
 * the gap so the loop seam is exact. Duration is measured once on mount.
 */
const KEYFRAMES = `
@keyframes infinite-slider-x { to { transform: translate3d(calc(-50% - var(--marquee-gap, 16px) / 2), 0, 0); } }
@keyframes infinite-slider-y { to { transform: translate3d(0, calc(-50% - var(--marquee-gap, 16px) / 2), 0); } }
`

export function InfiniteSlider({
  children,
  gap = 16,
  speed = 100,
  speedOnHover,
  direction = 'horizontal',
  reverse = false,
  className,
}: InfiniteSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [duration, setDuration] = useState<number | null>(null)

  useEffect(() => {
    const el = trackRef.current
    if (!el) return
    // One-time measure: the track holds 2 copies; -50% travel = one copy's size
    const copySize = (direction === 'horizontal' ? el.scrollWidth : el.scrollHeight) / 2
    setDuration(Math.max(6, copySize / Math.max(1, speed)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const hoverDuration =
    speedOnHover && duration ? Math.max(4, duration * (speed / speedOnHover)) : undefined

  const trackStyle: CSSProperties = {
    gap: `${gap}px`,
    ['--marquee-gap' as string]: `${gap}px`,
    animationName: direction === 'horizontal' ? 'infinite-slider-x' : 'infinite-slider-y',
    animationDuration: duration ? `${duration}s` : undefined,
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
    animationDirection: reverse ? 'reverse' : 'normal',
    willChange: 'transform',
  }

  return (
    <div className={cn('overflow-hidden', className)}>
      <style>{KEYFRAMES}</style>
      <div
        ref={trackRef}
        className={cn('flex w-max', direction === 'vertical' && 'flex-col')}
        style={trackStyle}
        onMouseEnter={
          speedOnHover
            ? (e) => {
                if (hoverDuration) e.currentTarget.style.animationDuration = `${hoverDuration}s`
              }
            : undefined
        }
        onMouseLeave={
          speedOnHover
            ? (e) => {
                if (duration) e.currentTarget.style.animationDuration = `${duration}s`
              }
            : undefined
        }
      >
        {children}
        {children}
      </div>
    </div>
  )
}
