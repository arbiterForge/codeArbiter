/// <reference types="vitest/globals" />
/// <reference types="@testing-library/jest-dom" />

// In Vitest's jsdom environment, `global` is the Node.js global object.
// Declare it so tsc does not flag test files that set properties on it
// (e.g. global.ResizeObserver = ..., global.fetch = ...).
declare const global: typeof globalThis
