import "@testing-library/jest-dom/vitest";

// O carimbo de build vem de `define` no bundle de producao; nos testes ele
// precisa existir antes de qualquer modulo que o leia no topo.
(globalThis as Record<string, unknown>).__BUILD_STAMP__ = "teste";
