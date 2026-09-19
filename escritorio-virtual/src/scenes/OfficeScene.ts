/**
 * Cena do escritorio: planta em corte, vista de cima, no estilo da imagem em
 * `design/reference/escritorio-virtual-referencia.png`.
 *
 * O que vem de ONDE:
 *
 * - a PLANTA (posicao e tamanho dos comodos) vem do banco, pela API;
 * - as PORTAS sao deduzidas de onde os comodos encostam (`geometry`);
 * - as ROTAS vem do grafo de waypoints (`config/paths`);
 * - o ACABAMENTO (paleta, mobiliario, silhueta) vem de `config/rooms`;
 * - o ESTADO das personagens vem do servidor, e so dele.
 *
 * A cena nunca deriva estado proprio. Se uma personagem esta no meio de uma
 * caminhada e chega uma resposta dizendo outra coisa, a caminhada e'
 * cancelada e ela vai para onde o servidor mandou.
 */

import Phaser from "phaser";

import { Personagem2D } from "../actors/Character";
import { NameTag } from "../ui/NameTag";
import {
  COR,
  PAREDE,
  SLUG,
  estiloDe,
  mobiliarioDe,
  posicaoDoMovel,
  postoDoComodo,
  silhueta,
  type Movel,
} from "../config/rooms";
import {
  assentoNoRefeitorio,
  construirGrafo,
  trajeto,
  type Grafo,
} from "../config/paths";
import { DoorController } from "../environment/DoorController";
import { LightingController } from "../environment/LightingController";
import {
  lojaAberta,
  repousoDaPorta,
  visualDaLoja,
  type EstadoPorta,
} from "../environment/StoreController";
import {
  distancia,
  limitesDoMundo,
  portas,
  salaPorSlug,
  vagaNaSala,
  type Ponto,
  type Porta,
} from "../environment/geometry";
import { hex } from "../config/characters";
import type { Cena, Personagem, Sala } from "../types";

/** Camadas, na ordem em que aparecem. */
export const CAMADA = {
  background: 0,
  floor: 10,
  rugs: 20,
  lowerWalls: 30,
  furnitureBehind: 40,
  characters: 50,
  furnitureFront: 60,
  upperWalls: 70,
  doors: 80,
  lights: 90,
  roomLabels: 100,
  effects: 110,
  debugOverlay: 120,
} as const;

/** Altura da parede de fundo visivel dentro de cada comodo. */
const FUNDO = 40;
/** Margem entre o predio e a borda do canvas. */
const MARGEM = 46;
/** Deslocamento do topo das paredes externas (efeito de volume). */
const RELEVO = 10;

export class CenaEscritorio extends Phaser.Scene {
  private salas: Sala[] = [];
  private assinaturaSalas = "";
  private grafo: Grafo = construirGrafo([]);

  private camadas!: Record<keyof typeof CAMADA, Phaser.GameObjects.Container>;
  private faixa!: Phaser.GameObjects.Text;
  private luzes!: LightingController;
  private portaDeRua!: DoorController;
  private estadoPorta: EstadoPorta = "CLOSED";

  private readonly personagens = new Map<number, Personagem2D>();
  private readonly etiquetas = new Map<number, NameTag>();
  private pendente: Cena | null = null;
  private pronta = false;

  constructor() {
    super("escritorio");
  }

  create(): void {
    this.cameras.main.setBackgroundColor(hex(COR.foraDoPredio));

    this.camadas = Object.fromEntries(
      (Object.keys(CAMADA) as Array<keyof typeof CAMADA>).map((nome) => {
        const c = this.add.container(0, 0);
        c.setDepth(CAMADA[nome]);
        return [nome, c];
      }),
    ) as Record<keyof typeof CAMADA, Phaser.GameObjects.Container>;

    this.luzes = new LightingController(this, this.camadas.lights);
    this.portaDeRua = new DoorController(this, this.camadas.doors);

    this.faixa = this.add.text(0, 0, "", {
      fontFamily: "system-ui, sans-serif",
      fontSize: "14px",
      color: hex(COR.paredeInterna),
      backgroundColor: "#1d1a17cc",
      padding: { x: 10, y: 5 },
    });
    this.faixa.setDepth(CAMADA.effects);
    this.faixa.setScrollFactor(0);

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.desmontar());

    this.pronta = true;
    if (this.pendente) {
      const guardada = this.pendente;
      this.pendente = null;
      this.aplicar(guardada);
    }
  }

  /**
   * Mantem as etiquetas de nome coladas nas personagens.
   *
   * Um unico laco por quadro para TODAS (nada de um timer por personagem), e
   * sem consultar o DOM aqui dentro.
   */
  update(): void {
    for (const [id, ator] of this.personagens) {
      const etiqueta = this.etiquetas.get(id);
      if (!etiqueta) continue;
      etiqueta.definirNome(ator.nome);
      etiqueta.seguir(ator.x, ator.y, ator.estaVisivel, ator.opacidade);
    }
  }

  private desmontar(): void {
    for (const ator of this.personagens.values()) ator.destruir();
    for (const etiqueta of this.etiquetas.values()) etiqueta.destruir();
    this.personagens.clear();
    this.etiquetas.clear();
    this.luzes.limpar();
    this.portaDeRua.limpar();
  }

  /** Ponto de entrada unico: recebe a resposta da API e reflete na cena. */
  aplicar(dados: Cena): void {
    if (!this.pronta) {
      this.pendente = dados;
      return;
    }
    const primeiraVez = this.assinaturaSalas === "";
    this.garantirMapa(dados.salas);
    this.aplicarPersonagens(dados);

    const visual = visualDaLoja(dados, this.estadoPorta);
    this.luzes.aplicar(visual.acesos, lojaAberta(visual.estado), primeiraVez);
    this.portaDeRua.aplicar(visual.porta, primeiraVez);
    this.estadoPorta = repousoDaPorta(visual.porta);
    this.faixa.setText(visual.rotulo);
    this.faixa.setColor(hex(visual.alerta ? COR.alerta : COR.paredeInterna));
  }

  // ── mapa ───────────────────────────────────────────────────────────────

  private garantirMapa(salas: Sala[]): void {
    const assinatura = JSON.stringify(
      salas.map((s) => [s.slug, s.pos_x, s.pos_y, s.largura, s.altura, s.nome]),
    );
    if (assinatura === this.assinaturaSalas) return;
    this.assinaturaSalas = assinatura;
    this.salas = salas;
    this.grafo = construirGrafo(salas);
    this.desenharMapa();
  }

  private desenharMapa(): void {
    for (const nome of ["background", "floor", "rugs", "lowerWalls",
      "furnitureBehind", "furnitureFront", "upperWalls", "doors",
      "lights", "roomLabels"] as const) {
      this.camadas[nome].removeAll(true);
    }
    this.luzes.limpar();
    this.portaDeRua.limpar();

    const mundo = limitesDoMundo(this.salas);
    const largura = mundo.largura + MARGEM * 2;
    const altura = mundo.altura + MARGEM * 2;
    this.scale.setGameSize(largura, altura);
    for (const camada of Object.values(this.camadas)) camada.setPosition(MARGEM, MARGEM);
    this.faixa.setPosition(14, 12);

    if (this.salas.length === 0) return;

    this.desenharPredio();
    for (const sala of this.salas) this.desenharComodo(sala);
    this.abrirVaos();
    this.desenharPortaDeRua(mundo);
    for (const sala of this.salas) this.registrarLuz(sala);
  }

  /** Massa de parede: a silhueta externa, com relevo e sombra. */
  private desenharPredio(): void {
    const contorno = silhueta(this.salas);
    if (contorno.length < 3) return;

    const expandido = contorno.map((p) => p);
    const sombra = this.add.graphics();
    sombra.fillStyle(0x000000, 0.35);
    sombra.fillPoints(
      expandido.map((p) => new Phaser.Geom.Point(p.x + 10, p.y + 16)), true,
    );
    sombra.setDepth(CAMADA.background);

    const topo = this.add.graphics();
    topo.fillStyle(COR.fachadaTopo, 1);
    topo.fillPoints(
      expandido.map((p) => new Phaser.Geom.Point(p.x, p.y - RELEVO)), true,
    );
    topo.setDepth(CAMADA.background);

    const corpo = this.add.graphics();
    corpo.fillStyle(COR.fachada, 1);
    corpo.fillPoints(expandido.map((p) => new Phaser.Geom.Point(p.x, p.y)), true);
    corpo.lineStyle(3, COR.parede, 1);
    corpo.strokePoints(expandido.map((p) => new Phaser.Geom.Point(p.x, p.y)), true, true);
    corpo.setDepth(CAMADA.background);

    this.camadas.background.add([sombra, topo, corpo]);
  }

  /** Area util de um comodo (dentro das paredes). */
  private pisoDe(sala: Sala) {
    return {
      x: sala.pos_x + PAREDE / 2,
      y: sala.pos_y + PAREDE / 2,
      largura: Math.max(sala.largura - PAREDE, 1),
      altura: Math.max(sala.altura - PAREDE, 1),
    };
  }

  private desenharComodo(sala: Sala): void {
    const piso = this.pisoDe(sala);
    const estilo = estiloDe(sala.slug);

    const g = this.add.graphics();
    g.setDepth(CAMADA.floor);
    // Piso.
    g.fillStyle(estilo.piso, 1);
    g.fillRect(piso.x, piso.y, piso.largura, piso.altura);

    // Parede de fundo vista por dentro: e' o que faz o comodo parecer um
    // comodo, e nao um retangulo pintado no chao.
    const fundo = Math.min(FUNDO, piso.altura * 0.34);
    g.fillStyle(estilo.fundo, 1);
    g.fillRect(piso.x, piso.y, piso.largura, fundo);
    g.fillStyle(0x000000, 0.10);
    g.fillRect(piso.x, piso.y + fundo - 5, piso.largura, 5);
    g.fillStyle(0xffffff, 0.35);
    g.fillRect(piso.x, piso.y, piso.largura, 4);

    this.camadas.floor.add(g);

    this.desenharMoveis(sala, fundo);
    this.desenharPlaca(sala, fundo);
  }

  private desenharPlaca(sala: Sala, fundo: number): void {
    const estilo = estiloDe(sala.slug);
    if (estilo.placa === null) return;
    const piso = this.pisoDe(sala);
    const centroX = piso.x + piso.largura / 2;

    const texto = this.add.text(centroX, piso.y + fundo * 0.44, sala.nome.toUpperCase(), {
      fontFamily: "Georgia, 'Times New Roman', serif",
      fontSize: "17px",
      color: hex(estilo.placa),
    });
    texto.setOrigin(0.5, 0.5);
    texto.setLetterSpacing(3);
    texto.setDepth(CAMADA.roomLabels);

    const filete = this.add.rectangle(
      centroX, piso.y + fundo * 0.72, texto.width + 20, 1.5, COR.metalDourado, 0.75,
    );
    filete.setDepth(CAMADA.roomLabels);
    this.camadas.roomLabels.add([texto, filete]);
  }

  // ── mobiliario ─────────────────────────────────────────────────────────

  private desenharMoveis(sala: Sala, fundo: number): void {
    const atras = this.add.graphics();
    atras.setDepth(CAMADA.furnitureBehind);
    const frente = this.add.graphics();
    frente.setDepth(CAMADA.furnitureFront);
    const tapetes = this.add.graphics();
    tapetes.setDepth(CAMADA.rugs);
    const rotulos: Phaser.GameObjects.GameObject[] = [];

    for (const movel of mobiliarioDe(sala.slug)) {
      const pos = posicaoDoMovel(sala, movel);
      const alvo = movel.forma === "tapete"
        ? tapetes
        : movel.naFrente ? frente : atras;
      this.desenharMovel(alvo, movel, pos, sala, fundo);
    }

    this.camadas.rugs.add(tapetes);
    this.camadas.furnitureBehind.add([atras, ...rotulos]);
    this.camadas.furnitureFront.add(frente);
  }

  private desenharMovel(
    g: Phaser.GameObjects.Graphics, m: Movel, pos: Ponto, sala: Sala, fundo: number,
  ): void {
    const { x, y } = pos;
    const w = m.largura;
    const h = m.altura;
    const volume = m.volume ?? 0;

    switch (m.forma) {
      case "tapete":
        g.fillStyle(m.cor ?? COR.tapeteShowroom, 0.9);
        if (m.redondo) {
          g.fillEllipse(x + w / 2, y + h / 2, w, h);
        } else {
          g.fillRoundedRect(x, y, w, h, Math.min(14, h / 2));
          g.lineStyle(3, COR.madeira, 0.35);
          g.strokeRoundedRect(x + 7, y + 7, w - 14, h - 14, Math.min(10, h / 2));
        }
        break;

      case "monitor":
        // Tela do caixa, em cima do balcao.
        g.fillStyle(COR.movelPreto, 1);
        g.fillRoundedRect(x + w * 0.3, y + h * 0.7, w * 0.4, h * 0.3, 2);
        g.fillStyle(0x1b1f24, 1);
        g.fillRoundedRect(x, y, w, h * 0.78, 3);
        g.fillStyle(0x5b7c93, 1);
        g.fillRoundedRect(x + 3, y + 3, w - 6, h * 0.78 - 6, 2);
        break;

      case "caixa": {
        // Sombra no chao, corpo e tampo deslocado: da a impressao de volume.
        g.fillStyle(0x000000, 0.14);
        g.fillRoundedRect(x + 3, y + h - 4, w, 10, 5);
        g.fillStyle(m.cor ?? COR.movelPreto, 1);
        g.fillRoundedRect(x, y, w, h, 5);
        g.fillStyle(m.corTopo ?? COR.movelClaro, 1);
        g.fillRoundedRect(x, y - volume * 0.35, w, h * 0.7, 5);
        g.lineStyle(1.5, 0x000000, 0.12);
        g.strokeRoundedRect(x, y - volume * 0.35, w, h * 0.7, 5);
        break;
      }

      case "prateleira": {
        g.fillStyle(0x000000, 0.10);
        g.fillRoundedRect(x + 2, y + 3, w, h, 3);
        g.fillStyle(m.cor ?? COR.madeira, 1);
        g.fillRoundedRect(x, y, w, h, 3);
        g.fillStyle(0xffffff, 0.22);
        g.fillRect(x, y, w, 3);
        // Objetos apoiados, para a prateleira nao ficar vazia.
        const tons = [0x8d6e63, 0x3a332b, 0xcbb6a6, 0x6f5641];
        const quantos = Math.max(2, Math.floor(w / 34));
        for (let i = 0; i < quantos; i += 1) {
          g.fillStyle(tons[i % tons.length], 1);
          g.fillRoundedRect(x + 8 + i * (w - 16) / quantos, y - h * 0.42, 18, h * 0.5, 3);
        }
        break;
      }

      case "arara": {
        const vertical = h > w;
        const comprimento = vertical ? h : w;
        const tons = [
          0xefe6da, 0xd8bfb2, 0x2f2b28, 0xf3ece2, 0xc7a99b,
          0x4a443e, 0xe3d3c6, 0x8d6e63,
        ];
        // Sombra da arara no chao.
        g.fillStyle(0x000000, 0.10);
        if (vertical) g.fillRoundedRect(x + 4, y + 6, w, h, 6);
        else g.fillRoundedRect(x + 4, y + 6, w, h, 6);

        // Pecas penduradas, encostadas uma na outra.
        const passo = 19;
        const quantidade = Math.max(3, Math.floor((comprimento - 12) / passo));
        for (let i = 0; i < quantidade; i += 1) {
          g.fillStyle(tons[i % tons.length], 1);
          if (vertical) {
            const py = y + 8 + i * passo;
            g.fillRoundedRect(x + 1, py, w - 2, passo - 3, 4);
            g.fillStyle(0x000000, 0.07);
            g.fillRect(x + 1, py + passo - 5, w - 2, 2);
          } else {
            const px = x + 8 + i * passo;
            g.fillRoundedRect(px, y + 1, passo - 3, h - 2, 4);
            g.fillStyle(0x000000, 0.07);
            g.fillRect(px, y + h - 4, passo - 3, 2);
          }
        }

        // Barra dourada por cima das pecas.
        g.fillStyle(COR.metalDourado, 1);
        if (vertical) {
          g.fillRect(x + w / 2 - 2.5, y, 5, h);
          g.fillCircle(x + w / 2, y, 4);
          g.fillCircle(x + w / 2, y + h, 4);
        } else {
          g.fillRect(x, y + h / 2 - 2.5, w, 5);
          g.fillCircle(x, y + h / 2, 4);
          g.fillCircle(x + w, y + h / 2, 4);
        }
        break;
      }

      case "pecas": {
        // Pilhas de roupa dobrada em cima das mesas de exposicao.
        const tons = [0xe7d9cb, 0xcbb6a6, 0x3a332b, 0xf1e8dd];
        for (let i = 0; i < 3; i += 1) {
          const px = x + i * (w / 3);
          const alturaPilha = h * (0.6 + (i % 2) * 0.25);
          g.fillStyle(0x000000, 0.10);
          g.fillRoundedRect(px + 2, y + h - alturaPilha + 3, w / 3 - 6, alturaPilha, 3);
          g.fillStyle(tons[i % tons.length], 1);
          g.fillRoundedRect(px, y + h - alturaPilha, w / 3 - 8, alturaPilha, 3);
          g.lineStyle(1, 0x000000, 0.08);
          g.strokeRoundedRect(px, y + h - alturaPilha, w / 3 - 8, alturaPilha, 3);
        }
        break;
      }

      case "espelho":
        g.fillStyle(COR.metalDourado, 1);
        g.fillRoundedRect(x - 3, y - 3, w + 6, h + 6, 20);
        g.fillStyle(COR.vidro, 1);
        g.fillRoundedRect(x, y, w, h, 18);
        g.fillStyle(0xffffff, 0.35);
        g.fillRoundedRect(x + 4, y + 6, w * 0.32, h * 0.6, 10);
        break;

      case "manequim": {
        const cx = x + w / 2;
        g.fillStyle(0x000000, 0.14);
        g.fillEllipse(cx, y + h + 2, w * 0.7, 9);
        g.fillStyle(COR.madeiraEscura, 1);
        g.fillRect(cx - 2.5, y + h * 0.62, 5, h * 0.4);
        g.fillEllipse(cx, y + h, w * 0.46, 7);
        // Vestido: ombros estreitos, barra larga.
        g.fillStyle(0xd8bfb2, 1);
        g.fillTriangle(
          cx - w * 0.2, y + h * 0.08,
          cx + w * 0.2, y + h * 0.08,
          cx, y + h * 0.66,
        );
        g.fillEllipse(cx, y + h * 0.5, w * 0.62, h * 0.42);
        g.fillStyle(COR.movelClaro, 1);
        g.fillEllipse(cx, y + h * 0.12, w * 0.34, h * 0.2);
        break;
      }

      case "planta":
        g.fillStyle(0x000000, 0.12);
        g.fillEllipse(x + w / 2, y + h - 2, w * 0.7, 7);
        g.fillStyle(COR.movelClaro, 1);
        g.fillRoundedRect(x + w * 0.22, y + h * 0.58, w * 0.56, h * 0.42, 4);
        g.fillStyle(COR.planta, 1);
        g.fillCircle(x + w / 2, y + h * 0.4, w * 0.36);
        g.fillStyle(COR.plantaClara, 1);
        g.fillCircle(x + w * 0.36, y + h * 0.3, w * 0.2);
        g.fillCircle(x + w * 0.66, y + h * 0.34, w * 0.17);
        break;

      case "quadro": {
        // Pendurado na parede de fundo, nao apoiado no chao.
        const piso = this.pisoDe(sala);
        const py = piso.y + Math.max(fundo * 0.5 - h / 2, 4);
        g.fillStyle(0x000000, 0.18);
        g.fillRect(x + 2, py + 3, w, h);
        g.fillStyle(COR.metalDourado, 1);
        g.fillRect(x, py, w, h);
        g.fillStyle(COR.movelClaro, 1);
        g.fillRect(x + 3, py + 3, w - 6, h - 6);
        g.fillStyle(0xcdbfae, 1);
        g.fillRect(x + 8, py + 8, w - 16, h - 16);
        break;
      }

      case "luminaria": {
        // Pendente: halo quente no teto, visto de cima.
        g.fillStyle(0xffd9a0, 0.22);
        g.fillCircle(x + w / 2, y + h / 2, w * 0.9);
        g.fillStyle(0xffe6bd, 0.35);
        g.fillCircle(x + w / 2, y + h / 2, w * 0.55);
        g.fillStyle(COR.movelPreto, 1);
        g.fillCircle(x + w / 2, y + h / 2, w * 0.2);
        break;
      }
    }
  }

  // ── vaos e portas ──────────────────────────────────────────────────────

  private abrirVaos(): void {
    const vaos = portas(this.salas);
    if (vaos.length === 0) return;

    const g = this.add.graphics();
    g.setDepth(CAMADA.lowerWalls);
    const batentes = this.add.graphics();
    batentes.setDepth(CAMADA.doors);

    for (const porta of vaos) {
      const sala = salaPorSlug(this.salas, porta.slug);
      g.fillStyle(sala ? estiloDe(sala.slug).piso : COR.pisoCorredor, 1);

      if (porta.horizontal) {
        g.fillRect(porta.x - porta.vao / 2, porta.y - PAREDE / 2 - 1, porta.vao, PAREDE + 2);
      } else {
        g.fillRect(porta.x - PAREDE / 2 - 1, porta.y - porta.vao / 2, PAREDE + 2, porta.vao);
      }
      this.marcarBatente(batentes, porta);
      this.portaDeRua.desenharPortaInterna(batentes, porta, PAREDE);
    }

    this.camadas.lowerWalls.add(g);
    this.camadas.doors.add(batentes);
  }

  private marcarBatente(g: Phaser.GameObjects.Graphics, porta: Porta): void {
    g.fillStyle(COR.metalDourado, 0.9);
    const metade = porta.vao / 2;
    if (porta.horizontal) {
      g.fillRect(porta.x - metade - 4, porta.y - PAREDE / 2, 4, PAREDE);
      g.fillRect(porta.x + metade, porta.y - PAREDE / 2, 4, PAREDE);
    } else {
      g.fillRect(porta.x - PAREDE / 2, porta.y - metade - 4, PAREDE, 4);
      g.fillRect(porta.x - PAREDE / 2, porta.y + metade, PAREDE, 4);
    }
  }

  private desenharPortaDeRua(mundo: { largura: number; altura: number }): void {
    const entrada = salaPorSlug(this.salas, SLUG.ENTRADA);
    if (!entrada) return;

    const base = entrada.pos_y + entrada.altura;
    const vao = Math.min(96, entrada.largura * 0.42);
    const horizontal = Math.abs(base - mundo.altura) <= 1.5;
    const x = entrada.pos_x + entrada.largura / 2;
    const y = horizontal ? base : entrada.pos_y + entrada.altura / 2;

    const soleira = this.add.graphics();
    soleira.setDepth(CAMADA.lowerWalls);
    soleira.fillStyle(estiloDe(SLUG.ENTRADA).piso, 1);
    if (horizontal) {
      soleira.fillRect(x - vao / 2, y - PAREDE, vao, PAREDE * 2);
    } else {
      soleira.fillRect(x - PAREDE, y - vao / 2, PAREDE * 2, vao);
    }
    // Capacho do lado de fora.
    soleira.fillStyle(COR.tapeteEntrada, 0.9);
    soleira.fillRoundedRect(x - vao / 2, y + PAREDE, vao, 26, 4);
    this.camadas.lowerWalls.add(soleira);

    this.portaDeRua.criarPortaDeRua(x, y, vao, PAREDE - 2, horizontal);
  }

  private registrarLuz(sala: Sala): void {
    this.luzes.registrar(sala, this.pisoDe(sala));
  }

  // ── personagens ────────────────────────────────────────────────────────

  /** Posicao alvo de cada personagem, por comodo, sem sobrepor. */
  private posicoesAlvo(dados: Cena): Map<number, Ponto> {
    const porSlug = new Map(dados.salas.map((s) => [s.slug, s]));
    const agrupado = new Map<string, number[]>();
    for (const p of dados.personagens) {
      if (!p.sala || !porSlug.has(p.sala)) continue;
      const lista = agrupado.get(p.sala) ?? [];
      lista.push(p.id);
      agrupado.set(p.sala, lista);
    }

    const alvos = new Map<number, Ponto>();
    for (const [slug, ids] of agrupado) {
      const sala = porSlug.get(slug)!;
      ids.forEach((id, i) => {
        // Vaga configurada primeiro (balcão, arara, cadeira da mesa); quando
        // acabam as vagas, o restante se espalha sem sobrepor.
        const posto = postoDoComodo(sala, i);
        const alvo = posto
          ?? (slug === SLUG.REFEITORIO
            ? assentoNoRefeitorio(sala, i, ids.length)
            : vagaNaSala(sala, i, ids.length));
        alvos.set(id, alvo);
      });
    }
    return alvos;
  }

  private aplicarPersonagens(dados: Cena): void {
    const alvos = this.posicoesAlvo(dados);
    const vistos = new Set<number>();

    for (const p of dados.personagens) {
      vistos.add(p.id);
      const alvo = alvos.get(p.id) ?? null;
      let ator = this.personagens.get(p.id);

      if (ator && ator.precisaRecriar(p)) {
        ator.destruir();
        this.etiquetas.get(p.id)?.destruir();
        this.personagens.delete(p.id);
        this.etiquetas.delete(p.id);
        ator = undefined;
      }

      if (!ator) {
        ator = new Personagem2D(this, p, alvo ?? this.pontoDeEntrada());
        ator.anexarEm(this.camadas.characters);
        ator.salaAtual = p.sala;
        this.personagens.set(p.id, ator);
        this.etiquetas.set(p.id, new NameTag(this, this.camadas.effects, p.nome));
        ator.aplicar(p);
        if (alvo) ator.mostrar(true);
        continue;
      }

      ator.aplicar(p);
      this.moverPara(ator, p, alvo);
    }

    for (const [id, ator] of this.personagens) {
      if (vistos.has(id)) continue;
      ator.destruir();
      this.etiquetas.get(id)?.destruir();
      this.personagens.delete(id);
      this.etiquetas.delete(id);
    }
  }

  private moverPara(ator: Personagem2D, dados: Personagem, alvo: Ponto | null): void {
    // Sem sala: saiu de cena (folga, ausencia, batida faltando, fim do dia).
    if (alvo === null || dados.sala === null) {
      if (!ator.estaVisivel) {
        ator.salaAtual = null;
        return;
      }
      // Sai andando ate a rua antes de sumir, em vez de evaporar no lugar.
      const saida = this.pontoDaRua();
      const rota = trajeto({
        salas: this.salas,
        grafo: this.grafo,
        origem: ator.posicao,
        salaOrigem: ator.salaAtual,
        destino: saida,
        salaDestino: SLUG.ENTRADA,
      });
      ator.salaAtual = null;
      ator.caminharPor(
        rota,
        Personagem2D.duracaoPara(distancia(ator.posicao, rota)),
        () => ator.esconder(),
      );
      return;
    }

    // Entrando em cena: aparece na rua e caminha para dentro.
    if (!ator.estaVisivel) {
      const rua = this.pontoDaRua();
      ator.posicionar(rua);
      ator.mostrar();
      const rota = trajeto({
        salas: this.salas,
        grafo: this.grafo,
        origem: rua,
        salaOrigem: SLUG.ENTRADA,
        destino: alvo,
        salaDestino: dados.sala,
      });
      ator.salaAtual = dados.sala;
      ator.caminharPor(rota, Personagem2D.duracaoPara(distancia(rua, rota)));
      return;
    }

    const salaAnterior = ator.salaAtual;
    ator.salaAtual = dados.sala;

    if (salaAnterior === dados.sala) {
      const ateAlvo = Phaser.Math.Distance.Between(ator.x, ator.y, alvo.x, alvo.y);
      if (ateAlvo > 4) {
        ator.caminharPor([alvo], Personagem2D.duracaoPara(ateAlvo));
      }
      return;
    }

    const rota = trajeto({
      salas: this.salas,
      grafo: this.grafo,
      origem: ator.posicao,
      salaOrigem: salaAnterior,
      destino: alvo,
      salaDestino: dados.sala,
    });
    ator.caminharPor(rota, Personagem2D.duracaoPara(distancia(ator.posicao, rota)));
  }

  /** Ponto de rua: do lado de fora da porta, onde a personagem aparece e some. */
  private pontoDaRua(): Ponto {
    const entrada = salaPorSlug(this.salas, SLUG.ENTRADA);
    if (!entrada) return { x: 0, y: 0 };
    return {
      x: entrada.pos_x + entrada.largura / 2,
      y: entrada.pos_y + entrada.altura + 70,
    };
  }

  private pontoDeEntrada(): Ponto {
    const entrada = salaPorSlug(this.salas, SLUG.ENTRADA);
    if (!entrada) return { x: 0, y: 0 };
    return {
      x: entrada.pos_x + entrada.largura / 2,
      y: entrada.pos_y + entrada.altura * 0.55,
    };
  }

  // ── acesso para os testes ──────────────────────────────────────────────

  portasDaPlanta(): Porta[] {
    return portas(this.salas);
  }

  opacidadeDaLuz(slug: string): number | null {
    return this.luzes.opacidadeDe(slug);
  }

  estadoDaPortaDeRua(): EstadoPorta {
    return this.portaDeRua.estadoAtual;
  }

  elenco(): Map<number, Personagem2D> {
    return this.personagens;
  }
}
