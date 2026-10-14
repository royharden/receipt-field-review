// Configuration proposal only: the UI and Vite dependency are not installed in WP01.
export default {
  root: "web",
  build: { outDir: "../dist/web", emptyOutDir: true },
  server: { host: "127.0.0.1", strictPort: true },
  preview: { host: "127.0.0.1", strictPort: true },
};
