declare module "lenis" {
  interface LenisOptions {
    wrapper?: Window | HTMLElement;
    content?: HTMLElement;
    duration?: number;
    easing?: (t: number) => number;
    orientation?: "vertical" | "horizontal";
    gestureOrientation?: "vertical" | "horizontal" | "both";
    smoothWheel?: boolean;
    wheelMultiplier?: number;
    touchMultiplier?: number;
    infinite?: boolean;
    anchors?: boolean;
    autoResize?: boolean;
    autoRaf?: boolean;
    overscroll?: boolean;
    syncTouch?: boolean;
    prevent?: (node: HTMLElement) => boolean;
    lerp?: number;
  }

  interface ScrollToOptions {
    offset?: number;
    immediate?: boolean;
    lock?: boolean;
    duration?: number;
    easing?: (t: number) => number;
    onStart?: () => void;
    onComplete?: () => void;
    force?: boolean;
  }

  export default class Lenis {
    constructor(options?: LenisOptions);
    raf(time: number): void;
    scrollTo(
      target: number | string | HTMLElement,
      options?: ScrollToOptions
    ): void;
    destroy(): void;
    on(event: string, callback: (...args: unknown[]) => void): void;
    resize(): void;
    stop(): void;
    start(): void;
    readonly isStopped: boolean;
    readonly isLocked: boolean;
    readonly velocity: number;
    readonly direction: number;
    readonly progress: number;
    readonly limit: number;
    readonly animatedScroll: number;
    readonly targetScroll: number;
  }
}
