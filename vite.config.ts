// Build from the repository root. Serve dist/web through the same-origin local Python host.
export default {
  root: "web",
  build: { outDir: "../dist/web", emptyOutDir: true },
  server: { host: "127.0.0.1", strictPort: true },
  preview: { host: "127.0.0.1", strictPort: true },
};
