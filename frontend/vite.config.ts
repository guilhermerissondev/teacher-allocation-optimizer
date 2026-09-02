import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Carimbo do build embutido no bundle. Serve para responder numa olhada a
// pergunta "estou vendo a versao nova?": se o carimbo na tela nao mudou depois
// de um novo build, o navegador esta servindo uma pagina antiga.
const BUILD_STAMP = new Date().toISOString().slice(0, 16).replace("T", " ");

export default defineConfig({
  define: { __BUILD_STAMP__: JSON.stringify(BUILD_STAMP) },
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // O carimbo de build e injetado por `define`, que nao vale nos testes.
    define: { __BUILD_STAMP__: JSON.stringify("teste") },
  },
});

