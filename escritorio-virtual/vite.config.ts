import { defineConfig } from "vite";
import { resolve } from "node:path";

// O bundle e' escrito direto na pasta de estaticos do painel Django.
// Nomes FIXOS (sem hash): o cache-busting do projeto e' feito pela tag
// {% estatico %}, que anexa ?v=<mtime> (ver core/templatetags/core_extras.py).
// Nome com hash so criaria arquivo orfao a cada build, sem ganho nenhum.
const SAIDA = resolve(
  import.meta.dirname,
  "../della_sistemas/static/escritorio",
);

export default defineConfig({
  build: {
    outDir: SAIDA,
    // A pasta e' exclusiva deste bundle, entao limpar e' seguro.
    emptyOutDir: true,
    target: "es2020",
    sourcemap: false,
    lib: {
      entry: resolve(import.meta.dirname, "src/main.ts"),
      name: "EscritorioVirtual",
      formats: ["iife"],
      fileName: () => "escritorio.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "escritorio.[ext]",
      },
    },
  },
});
