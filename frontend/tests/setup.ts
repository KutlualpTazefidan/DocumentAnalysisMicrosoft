import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom does not implement matchMedia; polyfill for components that check it.
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// jsdom does not implement ResizeObserver; recharts ResponsiveContainer
// gates child rendering on the first observer callback. Synchronous
// callback with a fixed size keeps chart tests deterministic.
if (typeof globalThis.ResizeObserver === "undefined") {
  class MockResizeObserver {
    constructor(private cb: ResizeObserverCallback) {}
    observe(target: Element): void {
      this.cb(
        [
          {
            target,
            contentRect: { width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON: () => ({}) } as DOMRectReadOnly,
            borderBoxSize: [{ inlineSize: 600, blockSize: 400 }],
            contentBoxSize: [{ inlineSize: 600, blockSize: 400 }],
            devicePixelContentBoxSize: [],
          } as ResizeObserverEntry,
        ],
        this as unknown as ResizeObserver,
      );
    }
    unobserve(): void {}
    disconnect(): void {}
  }
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;
}

afterEach(() => {
  cleanup();
});
