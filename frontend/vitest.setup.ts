// Brings @testing-library/jest-dom matchers (`toBeInTheDocument`, etc.)
// into the global expect namespace for all tests in this project.
import "@testing-library/jest-dom/vitest";

// Polyfill localStorage for the test environment.
//
// Node >= 22 defines its own experimental `localStorage` global, and it wins
// over the one jsdom installs. Without `--localstorage-file` it resolves to
// undefined and only prints "ExperimentalWarning: localStorage is not available
// because --localstorage-file was not provided" — so `localStorage.clear()`
// fails with "Cannot read properties of undefined". That is why
// useNotifications.fix202.test.tsx and DesignSystemPicker.reskin.test.tsx each
// hand-roll their own stub, and why lib/api.ts's getToken() guards on
// `typeof localStorage === "undefined"`.
//
// Two deliberate choices:
//   * defineProperty, not `if (!global.localStorage)` — merely READING the
//     global triggers Node's getter and prints that warning once per worker.
//   * a plain value, not `vi.stubGlobal` — a test's own `vi.unstubAllGlobals()`
//     then restores this polyfill instead of removing storage outright, which
//     is what broke api.refreshRetry.test.ts. Tests wanting their own spy can
//     still stubGlobal over it and get this back on unstub.
{
  const store = new Map<string, string>();
  const memoryStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => [...store.keys()][index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
  Object.defineProperty(global, "localStorage", {
    configurable: true,
    writable: true,
    value: memoryStorage,
  });
}

// Polyfill ResizeObserver for test environment
if (!global.ResizeObserver) {
  global.ResizeObserver = class ResizeObserver {
    constructor(_callback: ResizeObserverCallback) {}
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof global.ResizeObserver;
}
