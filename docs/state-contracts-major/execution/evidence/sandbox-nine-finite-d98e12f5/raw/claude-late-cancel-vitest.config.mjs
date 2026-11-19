export default { test: { fileParallelism: false, testTimeout: 300000, hookTimeout: 300000,
coverage: { provider: "v8", include: ["claude-inside.ts"], reporter: ["json", "json-summary"], reportsDirectory: "../coverage" } } };
