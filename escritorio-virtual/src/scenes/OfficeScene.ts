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
  CONTORNO,
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

    // Piso com textura: tabua de madeira nos showrooms e corredor, ladrilho
    // no refeitorio e na entrada. Sem isso tudo vira uma mancha bege.
    g.fillStyle(estilo.piso, 1);
    g.fillRect(piso.x, piso.y, piso.largura, piso.altura);
    this.texturaDoPiso(g, piso, estilo);

    // Parede de fundo vista por dentro: e' o que faz o comodo parecer um
    // comodo, e nao um retangulo pintado no chao.
    const fundo = Math.min(FUNDO, piso.altura * 0.34);
    g.fillStyle(estilo.fundo, 1);
    g.fillRect(piso.x, piso.y, piso.largura, fundo);
    g.fillStyle(0xffffff, 0.12);
    g.fillRect(piso.x, piso.y, piso.largura, 5);
    g.fillStyle(COR.contorno, 0.45);
    g.fillRect(piso.x, piso.y + fundo - 3, piso.largura, 3);

    this.camadas.floor.add(g);

    this.desenharMoveis(sala, fundo);
    this.desenharPlaca(sala, fundo);
  }

  /** Tabuas ou ladrilhos, conforme o ambiente. */
  private texturaDoPiso(
    g: Phaser.GameObjects.Graphics,
    piso: { x: number; y: number; largura: number; altura: number },
    estilo: ReturnType<typeof estiloDe>,
  ): void {
    g.fillStyle(estilo.listra, 1);

    if (estilo.padrao === "ladrilho") {
      const lado = 34;
      for (let i = 0; i * lado < piso.largura; i += 1) {
        for (let j = 0; j * lado < piso.altura; j += 1) {
          if ((i + j) % 2 !== 0) continue;
          g.fillRect(
            piso.x + i * lado, piso.y + j * lado,
            Math.min(lado, piso.largura - i * lado),
            Math.min(lado, piso.altura - j * lado),
          );
        }
      }
      return;
    }

    // Tabuas: linhas finas no sentido longo do comodo.
    const vertical = estilo.padrao === "tabua-vertical";
    const passo = 30;
    if (vertical) {
      for (let x = piso.x + passo; x < piso.x + piso.largura; x += passo) {
        g.fillRect(x, piso.y, 2, piso.altura);
      }
    } else {
      for (let y = piso.y + passo; y < piso.y + piso.altura; y += passo) {
        g.fillRect(piso.x, y, piso.largura, 2);
      }
    }
  }

  private desenharPlaca(sala: Sala, fundo: number): void {
    const estilo = estiloDe(sala.slug);
    if (estilo.placa === null) return;
    const piso = this.pisoDe(sala);
    const centroX = piso.x + piso.largura / 2;

    const texto = this.add.text(centroX, piso.y + fundo * 0.44, sala.nome.toUpperCase(), {
      fontFamily: "Georgia, 'Times New Roman', serif",
      fontSize: "18px",
      color: hex(estilo.placa),
    });
    texto.setOrigin(0.5, 0.5);
    texto.setLetterSpacing(3);
    texto.setDepth(CAMADA.roomLabels);

    const filete = this.add.rectangle(
      centroX, piso.y + fundo * 0.74, texto.width + 24, 2, COR.metalDourado, 0.85,
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

    for (const movel of mobiliarioDe(sala.slug)) {
      const pos = posicaoDoMovel(sala, movel);
      const alvo = movel.forma === "tapete"
        ? tapetes
        : movel.naFrente ? frente : atras;
      this.desenharMovel(alvo, movel, pos, sala, fundo);
    }

    this.camadas.rugs.add(tapetes);
    this.camadas.furnitureBehind.add(atras);
    this.camadas.furnitureFront.add(frente);
  }

  /** Contorno escuro padrao: e' o que separa um objeto do outro. */
  private contorno(g: Phaser.GameObjects.Graphics, largura = CONTORNO.largura): void {
    g.lineStyle(largura, CONTORNO.cor, CONTORNO.alpha);
  }

  /** Retangulo arredondado com contorno e sombra no chao. */
  private bloco(
    g: Phaser.GameObjects.Graphics,
    x: number, y: number, w: number, h: number,
    cor: number, raio = 5, sombra = true,
  ): void {
    if (sombra) {
      g.fillStyle(COR.contorno, 0.16);
      g.fillRoundedRect(x + 3, y + 4, w, h, raio);
    }
    g.fillStyle(cor, 1);
    g.fillRoundedRect(x, y, w, h, raio);
    this.contorno(g);
    g.strokeRoundedRect(x, y, w, h, raio);
  }

  private desenharMovel(
    g: Phaser.GameObjects.Graphics, m: Movel, pos: Ponto, sala: Sala, fundo: number,
  ): void {
    const { x, y } = pos;
    const w = m.largura;
    const h = m.altura;
    const volume = m.volume ?? 0;

    switch (m.forma) {
      case "tapete": {
        const cor = m.cor ?? COR.tapeteShowroom;
        const borda = m.corTopo ?? COR.tapeteShowroomBorda;
        g.fillStyle(borda, 1);
        if (m.redondo) {
          g.fillEllipse(x + w / 2, y + h / 2, w, h);
          g.fillStyle(cor, 1);
          g.fillEllipse(x + w / 2, y + h / 2, w - 18, h - 18);
          g.fillStyle(borda, 0.5);
          g.fillEllipse(x + w / 2, y + h / 2, w - 34, h - 34);
          g.fillStyle(cor, 1);
          g.fillEllipse(x + w / 2, y + h / 2, w - 44, h - 44);
        } else {
          g.fillRoundedRect(x, y, w, h, 10);
          g.fillStyle(cor, 1);
          g.fillRoundedRect(x + 8, y + 8, w - 16, h - 16, 8);
        }
        break;
      }

      case "monitor": {
        // Estacao de trabalho: teclado, tela acesa e base.
        g.fillStyle(COR.movelClaro, 1);
        g.fillRoundedRect(x + w * 0.12, y + h * 0.82, w * 0.76, h * 0.24, 2);
        this.contorno(g, 1.5);
        g.strokeRoundedRect(x + w * 0.12, y + h * 0.82, w * 0.76, h * 0.24, 2);

        g.fillStyle(COR.movelPreto, 1);
        g.fillRect(x + w * 0.42, y + h * 0.66, w * 0.16, h * 0.2);
        this.bloco(g, x, y, w, h * 0.72, COR.tela, 3, false);
        g.fillStyle(COR.telaLuz, 0.85);
        g.fillRoundedRect(x + 4, y + 4, w - 8, h * 0.72 - 8, 2);
        g.fillStyle(0xffffff, 0.22);
        g.fillRect(x + 6, y + 6, w * 0.34, h * 0.14);
        break;
      }

      case "caixa": {
        // Corpo com contorno e tampo mais claro deslocado: volume legivel.
        this.bloco(g, x, y, w, h, m.cor ?? COR.movelPreto, 5);
        const topo = m.corTopo ?? COR.movelClaro;
        g.fillStyle(topo, 1);
        g.fillRoundedRect(x + 2, y - volume * 0.34, w - 4, h * 0.62, 5);
        this.contorno(g, 1.5);
        g.strokeRoundedRect(x + 2, y - volume * 0.34, w - 4, h * 0.62, 5);
        g.fillStyle(0xffffff, 0.16);
        g.fillRoundedRect(x + 5, y - volume * 0.34 + 3, w - 10, 4, 2);
        break;
      }

      case "prateleira": {
        this.bloco(g, x, y, w, h, m.cor ?? COR.madeira, 3);
        // Caixas e objetos apoiados, coloridos.
        const tons = COR.roupas;
        const quantos = Math.max(2, Math.floor(w / 38));
        for (let i = 0; i < quantos; i += 1) {
          const bw = (w - 14) / quantos - 6;
          const bx = x + 8 + i * ((w - 14) / quantos);
          const bh = h * (0.7 + (i % 2) * 0.35);
          g.fillStyle(tons[(i * 3) % tons.length], 1);
          g.fillRoundedRect(bx, y - bh, bw, bh, 2);
          this.contorno(g, 1.5);
          g.strokeRoundedRect(bx, y - bh, bw, bh, 2);
        }
        break;
      }

      case "arara": {
        const vertical = h > w;
        const comprimento = vertical ? h : w;
        const tons = COR.roupas;
        g.fillStyle(COR.contorno, 0.14);
        g.fillRoundedRect(x + 4, y + 6, w, h, 6);

        const passo = 21;
        const quantidade = Math.max(3, Math.floor((comprimento - 10) / passo));
        for (let i = 0; i < quantidade; i += 1) {
          g.fillStyle(tons[(i * 2 + 1) % tons.length], 1);
          if (vertical) {
            const py = y + 6 + i * passo;
            g.fillRoundedRect(x, py, w, passo - 4, 5);
            this.contorno(g, 1.5);
            g.strokeRoundedRect(x, py, w, passo - 4, 5);
          } else {
            const px = x + 6 + i * passo;
            g.fillRoundedRect(px, y, passo - 4, h, 5);
            this.contorno(g, 1.5);
            g.strokeRoundedRect(px, y, passo - 4, h, 5);
          }
        }

        // Barra por cima das pecas.
        g.fillStyle(COR.metalDourado, 1);
        this.contorno(g, 1.5);
        if (vertical) {
          g.fillRect(x + w / 2 - 3, y - 4, 6, h + 8);
          g.strokeRect(x + w / 2 - 3, y - 4, 6, h + 8);
        } else {
          g.fillRect(x - 4, y + h / 2 - 3, w + 8, 6);
          g.strokeRect(x - 4, y + h / 2 - 3, w + 8, 6);
        }
        break;
      }

      case "espelho":
        this.bloco(g, x - 4, y - 4, w + 8, h + 8, COR.metalDourado, 20);
        g.fillStyle(COR.vidro, 1);
        g.fillRoundedRect(x, y, w, h, 16);
        g.fillStyle(0xffffff, 0.45);
        g.fillRoundedRect(x + 5, y + 8, w * 0.3, h * 0.55, 10);
        this.contorno(g, 1.5);
        g.strokeRoundedRect(x, y, w, h, 16);
        break;

      case "manequim": {
        const cx = x + w / 2;
        g.fillStyle(COR.contorno, 0.18);
        g.fillEllipse(cx, y + h + 3, w * 0.7, 10);
        // Base e haste.
        g.fillStyle(COR.madeiraEscura, 1);
        g.fillRect(cx - 3, y + h * 0.6, 6, h * 0.42);
        g.fillEllipse(cx, y + h, w * 0.5, 9);
        this.contorno(g, 1.5);
        g.strokeEllipse(cx, y + h, w * 0.5, 9);
        // Vestido.
        g.fillStyle(COR.estofado, 1);
        g.fillTriangle(
          cx - w * 0.24, y + h * 0.06,
          cx + w * 0.24, y + h * 0.06,
          cx, y + h * 0.7,
        );
        g.fillEllipse(cx, y + h * 0.5, w * 0.66, h * 0.44);
        this.contorno(g, 1.5);
        g.strokeEllipse(cx, y + h * 0.5, w * 0.66, h * 0.44);
        g.fillStyle(COR.movelClaro, 1);
        g.fillEllipse(cx, y + h * 0.1, w * 0.36, h * 0.2);
        break;
      }

      case "planta": {
        const cx = x + w / 2;
        g.fillStyle(COR.contorno, 0.18);
        g.fillEllipse(cx, y + h, w * 0.7, 8);
        // Vaso de terracota.
        g.fillStyle(COR.vaso, 1);
        g.fillRoundedRect(x + w * 0.24, y + h * 0.58, w * 0.52, h * 0.42, 4);
        this.contorno(g, 1.5);
        g.strokeRoundedRect(x + w * 0.24, y + h * 0.58, w * 0.52, h * 0.42, 4);
        g.fillStyle(COR.vasoEscuro, 1);
        g.fillRect(x + w * 0.24, y + h * 0.58, w * 0.52, 5);
        // Folhagem em camadas.
        g.fillStyle(COR.plantaEscura, 1);
        g.fillCircle(cx, y + h * 0.38, w * 0.4);
        this.contorno(g, 1.5);
        g.strokeCircle(cx, y + h * 0.38, w * 0.4);
        g.fillStyle(COR.planta, 1);
        g.fillCircle(cx - w * 0.14, y + h * 0.3, w * 0.24);
        g.fillCircle(cx + w * 0.16, y + h * 0.34, w * 0.2);
        g.fillStyle(COR.plantaClara, 1);
        g.fillCircle(cx - w * 0.06, y + h * 0.22, w * 0.15);
        break;
      }

      case "pecas": {
        const tons = COR.roupas;
        for (let i = 0; i < 3; i += 1) {
          const px = x + i * (w / 3);
          const alturaPilha = h * (0.62 + (i % 2) * 0.28);
          g.fillStyle(tons[(i * 2) % tons.length], 1);
          g.fillRoundedRect(px, y + h - alturaPilha, w / 3 - 8, alturaPilha, 3);
          this.contorno(g, 1.5);
          g.strokeRoundedRect(px, y + h - alturaPilha, w / 3 - 8, alturaPilha, 3);
          g.fillStyle(0xffffff, 0.18);
          g.fillRect(px + 2, y + h - alturaPilha + 2, w / 3 - 12, 3);
        }
        break;
      }

      case "luminaria": {
        g.fillStyle(0xffd9a0, 0.26);
        g.fillCircle(x + w / 2, y + h / 2, w * 1.05);
        g.fillStyle(0xffe6bd, 0.4);
        g.fillCircle(x + w / 2, y + h / 2, w * 0.6);
        g.fillStyle(COR.movelPreto, 1);
        g.fillCircle(x + w / 2, y + h / 2, w * 0.22);
        this.contorno(g, 1.5);
        g.strokeCircle(x + w / 2, y + h / 2, w * 0.22);
        break;
      }

      case "quadro": {
        // Pendurado na parede de fundo, nao apoiado no chao.
        const piso = this.pisoDe(sala);
        const py = piso.y + Math.max(fundo * 0.5 - h / 2, 4);
        this.bloco(g, x, py, w, h, COR.metalDourado, 2, false);
        g.fillStyle(COR.movelClaro, 1);
        g.fillRect(x + 3, py + 3, w - 6, h - 6);
        g.fillStyle(COR.estofado, 0.8);
        g.fillRect(x + 7, py + 7, w - 14, h - 14);
        g.fillStyle(COR.planta, 0.7);
        g.fillCircle(x + w * 0.35, py + h * 0.62, Math.min(w, h) * 0.18);
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
