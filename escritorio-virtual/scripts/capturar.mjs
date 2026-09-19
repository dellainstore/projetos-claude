/**
 * Gera capturas REAIS da cena, abrindo o bundle num Chromium headless.
 *
 * Nao e' mockup: carrega exatamente o `escritorio.js` que vai para producao,
 * servindo uma API falsa no proprio navegador (o `fetch` e' interceptado antes
 * do bundle rodar). Assim da para ver cada situacao — loja fechada, todas
 * trabalhando, almoco, alguem no corredor — sem depender do relogio nem tocar
 * no ponto.
 *
 *   node scripts/capturar.mjs            # todas as cenas
 *   node scripts/capturar.mjs fechada    # só uma
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = resolve(AQUI, "..");
const BUNDLE = resolve(RAIZ, "../della_sistemas/static/escritorio/escritorio.js");
const SAIDA = resolve(RAIZ, "capturas");

// ── Planta: a MESMA da migration 0003_planta_integrada ────────────────────
const sala = (slug, nome, ordem, pos_x, pos_y, largura, altura) =>
  ({ slug, nome, ordem, pos_x, pos_y, largura, altura });

const PLANTA = [
  sala("store-entrance", "Entrada", 0, 560, 760, 320, 140),
  sala("showroom", "Show Room", 1, 0, 250, 560, 510),
  sala("anaca", "Anacã", 2, 880, 250, 560, 510),
  sala("corredor", "Corredor", 3, 560, 250, 320, 510),
  sala("cafeteria", "Refeitório", 4, 520, 0, 400, 250),
];

const pessoa = (id, personagem, nome, estado, sala, salaTrabalho) => ({
  id, personagem, nome,
  tipoAtor: "HUMAN_EMPLOYEE",
  estado, estadoEstavel: estado,
  desde: "2026-09-18T09:00:00-03:00",
  sala, salaTrabalho, salaOrigem: "loja",
  posX: 0, posY: 0, evento: null, inconsistencia: null,
});

const TINA = (estado, s) => pessoa(1, "tina", "Tina", estado, s, "showroom");
const SARA = (estado, s) => pessoa(2, "sara", "Sara", estado, s, "showroom");
const MICHELLE = (estado, s) => pessoa(3, "michelle", "Michelle", estado, s, "anaca");

const cena = (personagens, loja) => ({
  preview: { ativo: false, ultimoDiaComMovimento: "2026-09-18" },
  versao: 1,
  data: "2026-09-18",
  geradoEm: "2026-09-18T10:00:00-03:00",
  pollSegundos: 1, // captura precisa de ciclo curto
  loja: { pendencias: 0, ...loja },
  salas: PLANTA,
  personagens,
  avisos: [],
});

const FECHADA = { estado: "CLOSED", luzesAcesas: false, portaAberta: false };
const ABERTA = { estado: "OPEN", luzesAcesas: true, portaAberta: true };
const ALMOCO = { estado: "OPEN_LUNCH_ONLY", luzesAcesas: true, portaAberta: true };

/** Cada captura: nome, cena inicial, cenas seguintes e quando disparar. */
const ROTEIRO = {
  fechada: {
    titulo: "1. Loja fechada",
    quadros: [{ espera: 1200, cena: cena([
      TINA("OFF_SHIFT", null), SARA("OFF_SHIFT", null), MICHELLE("OFF_SHIFT", null),
    ], FECHADA) }],
  },
  postos: {
    titulo: "2. Tina e Sara no Show Room, Michelle na Anacã",
    quadros: [
      { espera: 200, cena: cena([
        TINA("OFF_SHIFT", null), SARA("OFF_SHIFT", null), MICHELLE("OFF_SHIFT", null),
      ], FECHADA) },
      { espera: 5000, cena: cena([
        TINA("WORKING", "showroom"), SARA("WORKING", "showroom"),
        MICHELLE("WORKING", "anaca"),
      ], ABERTA) },
    ],
  },
  trabalhando: {
    titulo: "3. Todas trabalhando",
    quadros: [{ espera: 1600, cena: cena([
      TINA("WORKING", "showroom"), SARA("WORKING", "showroom"),
      MICHELLE("WORKING", "anaca"),
    ], ABERTA) }],
  },
  corredor: {
    titulo: "4. Uma personagem atravessando o corredor",
    quadros: [
      { espera: 1600, cena: cena([
        TINA("WORKING", "showroom"), SARA("WORKING", "showroom"),
        MICHELLE("WORKING", "anaca"),
      ], ABERTA) },
      // Michelle sai da Anacã para o refeitório: pega ela no meio do caminho.
      { espera: 1700, cena: cena([
        TINA("WORKING", "showroom"), SARA("WORKING", "showroom"),
        MICHELLE("LUNCH", "cafeteria"),
      ], ABERTA) },
    ],
  },
  refeitorio: {
    titulo: "5. Todas no refeitório",
    quadros: [
      { espera: 200, cena: cena([
        TINA("WORKING", "showroom"), SARA("WORKING", "showroom"),
        MICHELLE("WORKING", "anaca"),
      ], ABERTA) },
      { espera: 5600, cena: cena([
        TINA("LUNCH", "cafeteria"), SARA("LUNCH", "cafeteria"),
        MICHELLE("LUNCH", "cafeteria"),
      ], ALMOCO) },
    ],
  },
  pendencia: {
    titulo: "7. Fechada com registro a conferir",
    quadros: [{ espera: 1400, cena: cena([
      { ...TINA("MISSING_PUNCH", null), inconsistencia: "MISSING_PUNCH" },
      SARA("OFF_SHIFT", null), MICHELLE("OFF_SHIFT", null),
    ], { ...FECHADA, estado: "CLOSED_WITH_PENDING", pendencias: 1 }) }],
  },
};

const VIEWPORTS = {
  desktop: { width: 1600, height: 1100, deviceScaleFactor: 1 },
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};

function paginaHtml(bundle, roteiro) {
  return `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --branco:#fff; --preto:#211d1a; --cinza-medio:#d9d2c7;
          --cinza-claro:#f4f1ea; --cinza-escuro:#6d665e; }
  * { box-sizing: border-box; }
  body { margin:0; padding:12px; background:var(--cinza-claro);
         font-family: system-ui, sans-serif; }
  .ev-palco { background:#fff; border:1px solid var(--cinza-medio);
              border-radius:12px; padding:6px; overflow:hidden; }
  .ev-palco canvas { display:block; margin:0 auto; max-width:100%;
                     height:auto !important; border-radius:8px; }
  .oculto { position:absolute; left:-9999px; }
</style></head>
<body>
<div id="escritorio-diagnostico" data-api-url="/api/estado/" data-poll-segundos="1" data-debug="0">
  <div class="ev-palco" data-ev="palco"></div>
  <div data-ev="debug"></div>
  <div class="oculto">
    <span data-ev="loja"></span><span data-ev="luzes"></span>
    <span data-ev="pendencias"></span><span data-ev="data"></span>
    <table><tbody data-ev="corpo"></tbody></table>
    <span data-ev="situacao"></span><span data-ev="atualizado"></span>
    <span data-ev="contagem"></span><span data-ev="erro"></span>
    <span data-ev="avisos"></span><ul data-ev="log"></ul>
    <span data-ev="modo"></span>
    <input data-ev="campo-data"><input data-ev="campo-hora">
    <button data-ev="ver"></button><button data-ev="tocar"></button>
    <button data-ev="ao-vivo"></button><button data-ev="atualizar"></button>
  </div>
</div>
<script>
  // API falsa: o bundle nao sabe a diferenca. Trocamos so a resposta.
  window.__quadros = ${JSON.stringify(roteiro.quadros)};
  window.__indice = 0;
  const original = window.fetch;
  window.fetch = async () => {
    const q = window.__quadros[Math.min(window.__indice, window.__quadros.length - 1)];
    return new Response(JSON.stringify(q.cena), {
      status: 200,
      headers: { "Content-Type": "application/json", ETag: '"q' + window.__indice + '"' },
    });
  };
  void original;
</script>
<script>${bundle}</script>
</body></html>`;
}

async function capturar(navegador, nome, roteiro, viewport, sufixo) {
  const bundle = await readFile(BUNDLE, "utf8");
  const pagina = await navegador.newPage();
  await pagina.setViewport(viewport);
  const erros = [];
  pagina.on("pageerror", (e) => erros.push(String(e)));
  pagina.on("console", (m) => {
    if (m.type() === "error") erros.push(m.text());
  });

  await pagina.setContent(paginaHtml(bundle, roteiro), { waitUntil: "load" });

  for (let i = 0; i < roteiro.quadros.length; i += 1) {
    await pagina.evaluate((idx) => {
      window.__indice = idx;
      document.querySelector("[data-ev=atualizar]")?.click();
    }, i);
    // O poller consulta sozinho; o proximo ciclo pega o quadro novo.
    await new Promise((r) => setTimeout(r, roteiro.quadros[i].espera));
  }

  const palco = await pagina.$(".ev-palco");
  const arquivo = resolve(SAIDA, `${nome}${sufixo}.png`);
  await palco.screenshot({ path: arquivo });
  await pagina.close();
  return { arquivo, erros };
}

async function principal() {
  const apenas = process.argv[2];
  await mkdir(SAIDA, { recursive: true });

  const navegador = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
           "--force-device-scale-factor=1"],
  });

  const relatorio = [];
  for (const [nome, roteiro] of Object.entries(ROTEIRO)) {
    if (apenas && apenas !== nome) continue;
    const desktop = await capturar(navegador, nome, roteiro, VIEWPORTS.desktop, "");
    relatorio.push({ nome, titulo: roteiro.titulo, ...desktop });
    console.log(`[ok] ${nome}: ${desktop.arquivo}`);
    if (desktop.erros.length) console.log(`     erros: ${desktop.erros.join(" | ")}`);
  }

  // Versao mobile de uma cena representativa.
  if (!apenas || apenas === "trabalhando") {
    const mobile = await capturar(
      navegador, "trabalhando", ROTEIRO.trabalhando, VIEWPORTS.mobile, "-mobile",
    );
    relatorio.push({ nome: "trabalhando-mobile", titulo: "6. Mobile", ...mobile });
    console.log(`[ok] mobile: ${mobile.arquivo}`);
    if (mobile.erros.length) console.log(`     erros: ${mobile.erros.join(" | ")}`);
  }

  await navegador.close();
  await writeFile(
    resolve(SAIDA, "relatorio.json"),
    JSON.stringify(relatorio, null, 2),
    "utf8",
  );
}

principal().catch((e) => {
  console.error(e);
  process.exit(1);
});
