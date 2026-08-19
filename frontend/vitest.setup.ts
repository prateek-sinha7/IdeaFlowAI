// Brings @testing-library/jest-dom matchers (`toBeInTheDocument`, etc.)
// into the global expect namespace for all tests in this project.
import "@testing-library/jest-dom/vitest";

// Polyfill ResizeObserver for test environment
if (!global.ResizeObserver) {
  global.ResizeObserver = class ResizeObserver {
    constructor(_callback: ResizeObserverCallback) {}
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof global.ResizeObserver;
}
