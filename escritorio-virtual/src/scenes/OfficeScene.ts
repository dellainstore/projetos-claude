/**
 * Cena principal: a imagem de fundo REAL (não redesenhada), com zonas de
 * iluminação, objetos interativos e as três personagens em pixel art
 * caminhando por cima dela.
 *
 * Fonte de cada coisa:
 * - a imagem em si: `BootScene` carrega e ajusta a resolução do jogo a ela;
 * - QUAL sala cada uma está: vem da API (`Personagem.sala`), sem mudança
 *   nenhuma na integração com o ponto;
 * - ONDE isso fica na tela: `config/officeZones.ts` (zonas) e
 *   `config/officePaths.ts` (rotas), calibrados sobre a arte;
 * - loja aberta/fechada e quais ambientes acendem: reaproveita
 *   `environment/StoreController.ts` (mesma lógica já testada, baseada só
 *   em slugs — não em pixels de backend, então continua correta aqui).
 *
 * A cena nunca decide sozinha o estado de ninguém: só reflete o que a API
 * mandou. Se uma personagem está no meio de uma caminhada e chega uma
 * resposta dizendo outra coisa, a caminhada é cancelada e ela vai para onde
 * o servidor mandou.
 */

import Phaser from "phaser";

import { EmployeeCharacter } from "../actors/EmployeeCharacter";
import { paletaDoSlug } from "../config/employees";
import { CAFETERIA_SEATS, OFFICE_ZONES, WORK_SPOTS, zonaDaSala, type OfficeRoomId } from "../config/officeZones";
import { buildWalkPath, OFFICE_POINTS } from "../config/officePaths";
import { computeImageFrame, pointToScreen, rectToScreen, type ImageFrame } from "../environment/ImageLayout";
import { lojaAberta, visualDaLoja, type EstadoPorta } from "../environment/StoreController";
import { LightingSystem } from "../systems/LightingSystem";
import { InteractionSystem } from "../systems/InteractionSystem";
import { EmployeeCard } from "../ui/EmployeeCard";
import { BG_TEXTURE_KEY } from "./BootScene";
import type { Cena, Personagem } from "../types";

const CAMADA = {
  background: 0,
  lighting: 10,
  objects: 20,
  characters: 30,
  debug: 90,
} as const;

export class OfficeScene extends Phaser.Scene {
  private background: Phaser.GameObjects.Image | null = null;
  private frame: ImageFrame = { offsetX: 0, offsetY: 0, scale: 1, displayWidth: 1440, displayHeight: 900 };

  private lighting!: LightingSystem;
  private interactions!: InteractionSystem;
  private card!: EmployeeCard;

  private readonly employees = new Map<number, EmployeeCharacter>();
  private ultimaCena: Cena | null = null;
  private estadoPorta: EstadoPorta = "CLOSED";

  private pronta = false;
  private pendente: Cena | null = null;

  constructor() {
    super("escritorio");
  }

  create(): void {
    const layerBg = this.add.container(0, 0).setDepth(CAMADA.background);
    const layerLight = this.add.container(0, 0).setDepth(CAMADA.lighting);
    const layerObjects = this.add.container(0, 0).setDepth(CAMADA.objects);
    this.add.container(0, 0).setDepth(CAMADA.characters); // reservada; personagens vão direto na cena com depth.

    this.frame = computeImageFrame(this.scale.width, this.scale.height, this.scale.width, this.scale.height);

    if (this.textures.exists(BG_TEXTURE_KEY)) {
      this.background = this.add.image(this.frame.offsetX, this.frame.offsetY, BG_TEXTURE_KEY);
      this.background.setOrigin(0, 0);
      this.background.setDisplaySize(this.frame.displayWidth, this.frame.displayHeight);
      layerBg.add(this.background);
    }

    this.lighting = new LightingSystem(this, layerLight);
    this.lighting.build(this.frame);

    const cardHost = (this.game.registry.get("cardHost") as HTMLElement | undefined) ?? document.body;
    this.card = new EmployeeCard(cardHost);

    this.interactions = new InteractionSystem(this, layerObjects, this.card);
    this.interactions.build(this.frame);

    if (this.sys.game.config.parent && typeof window !== "undefined" && window.location.search.includes("debugZonas=1")) {
      this.desenharDebug();
    }

    this.pronta = true;
    if (this.pendente) {
      const c = this.pendente;
      this.pendente = null;
      this.aplicar(c);
    }
  }

  private desenharDebug(): void {
    const g = this.add.graphics().setDepth(CAMADA.debug);
    g.lineStyle(2, 0x00ffcc, 0.9);
    for (const zone of OFFICE_ZONES) {
      const r = rectToScreen(this.frame, zone.rect);
      g.strokeRect(r.x, r.y, r.width, r.height);
    }
    g.fillStyle(0xff00ff, 1);
    for (const key of Object.keys(OFFICE_POINTS)) {
      const p = pointToScreen(this.frame, OFFICE_POINTS[key]);
      g.fillCircle(p.x, p.y, 5);
      this.add.text(p.x + 6, p.y - 6, key, { fontSize: "11px", color: "#ff00ff" }).setDepth(CAMADA.debug);
    }
  }

  aplicar(cena: Cena): void {
    if (!this.pronta) { this.pendente = cena; return; }

    const visual = visualDaLoja(cena, this.estadoPorta);
    const primeiraVez = this.ultimaCena === null;
    this.lighting.apply(lojaAberta(visual.estado), visual.acesos as Set<OfficeRoomId>, primeiraVez);
    this.estadoPorta = visual.porta;

    this.atualizarFuncionarias(cena.personagens);
    this.ultimaCena = cena;
  }

  private atualizarFuncionarias(personagens: Personagem[]): void {
    const vistos = new Set<number>();

    // Assentos do refeitório: por ordem de chegada (id), não por nome.
    const naCafeteria = personagens.filter((p) => p.sala === "cafeteria").sort((a, b) => a.id - b.id);
    const assentoPorId = new Map<number, number>();
    naCafeteria.forEach((p, i) => assentoPorId.set(p.id, i));

    for (const p of personagens) {
      vistos.add(p.id);
      const alvoNormalizado = this.pontoAlvo(p, assentoPorId.get(p.id));
      const alvoTela = alvoNormalizado ? pointToScreen(this.frame, alvoNormalizado) : null;

      let ator = this.employees.get(p.id);
      if (!ator) {
        const paleta = paletaDoSlug(p.personagem);
        const inicial = alvoTela ?? pointToScreen(this.frame, OFFICE_POINTS.entrance_outside);
        ator = new EmployeeCharacter(this, p, paleta, inicial.x, inicial.y);
        ator.gameObject.setDepth(CAMADA.characters);
        ator.salaAtual = p.sala;
        this.employees.set(p.id, ator);
        this.interactions.registerEmployee(ator, () => this.ultimaCena?.personagens.find((x) => x.id === p.id));
        ator.aplicar(p);
        if (alvoTela) ator.mostrar(true);
        continue;
      }

      ator.aplicar(p);
      this.moverPara(ator, p, alvoNormalizado, alvoTela);
    }

    for (const [id, ator] of this.employees) {
      if (vistos.has(id)) continue;
      ator.destruir();
      this.employees.delete(id);
    }
  }

  /** Ponto normalizado onde a personagem deveria estar, ou `null` (fora de cena). */
  private pontoAlvo(p: Personagem, indiceCafeteria: number | undefined) {
    if (!p.sala) return null;
    if (p.sala === "cafeteria") {
      const i = indiceCafeteria ?? 0;
      return CAFETERIA_SEATS[i % CAFETERIA_SEATS.length];
    }
    const posto = WORK_SPOTS[p.personagem];
    if (posto) return posto;
    const zona = zonaDaSala(p.sala as OfficeRoomId);
    if (!zona) return null;
    return { x: zona.rect.x + zona.rect.width / 2, y: zona.rect.y + zona.rect.height * 0.6 };
  }

  private moverPara(
    ator: EmployeeCharacter, p: Personagem,
    alvoNormalizado: { x: number; y: number } | null, alvoTela: { x: number; y: number } | null,
  ): void {
    if (!alvoNormalizado || !alvoTela || !p.sala) {
      if (!ator.estaVisivel) { ator.salaAtual = null; return; }
      const saida = pointToScreen(this.frame, OFFICE_POINTS.entrance_outside);
      const rotaNorm = buildWalkPath(ator.salaAtual as OfficeRoomId | null, this.paraNormalizado(ator.posicao), null, OFFICE_POINTS.entrance_outside);
      ator.salaAtual = null;
      ator.caminharPor(rotaNorm.map((pt) => pointToScreen(this.frame, pt)), EmployeeCharacter.duracaoPara(this.distanciaTela(ator.posicao, saida)), () => ator.esconder());
      return;
    }

    if (!ator.estaVisivel) {
      const entrada = pointToScreen(this.frame, OFFICE_POINTS.entrance_outside);
      ator.posicionar(entrada);
      ator.mostrar();
      const rotaNorm = buildWalkPath(null, OFFICE_POINTS.entrance_outside, p.sala as OfficeRoomId, alvoNormalizado);
      ator.salaAtual = p.sala;
      const pontosTela = rotaNorm.map((pt) => pointToScreen(this.frame, pt));
      ator.caminharPor(pontosTela, EmployeeCharacter.duracaoPara(this.somaDistancias(entrada, pontosTela)));
      return;
    }

    const salaAnterior = ator.salaAtual as OfficeRoomId | null;
    ator.salaAtual = p.sala;

    if (salaAnterior === p.sala) {
      const d = this.distanciaTela(ator.posicao, alvoTela);
      if (d > 4) ator.caminharPor([alvoTela], EmployeeCharacter.duracaoPara(d));
      return;
    }

    const rotaNorm = buildWalkPath(salaAnterior, this.paraNormalizado(ator.posicao), p.sala as OfficeRoomId, alvoNormalizado);
    const pontosTela = rotaNorm.map((pt) => pointToScreen(this.frame, pt));
    ator.caminharPor(pontosTela, EmployeeCharacter.duracaoPara(this.somaDistancias(ator.posicao, pontosTela)));
  }

  private paraNormalizado(p: { x: number; y: number }) {
    return {
      x: (p.x - this.frame.offsetX) / this.frame.displayWidth,
      y: (p.y - this.frame.offsetY) / this.frame.displayHeight,
    };
  }

  private distanciaTela(a: { x: number; y: number }, b: { x: number; y: number }): number {
    return Phaser.Math.Distance.Between(a.x, a.y, b.x, b.y);
  }

  private somaDistancias(origem: { x: number; y: number }, pontos: Array<{ x: number; y: number }>): number {
    let total = 0;
    let anterior = origem;
    for (const p of pontos) { total += this.distanciaTela(anterior, p); anterior = p; }
    return total;
  }

  // ── acesso para testes ───────────────────────────────────────────────────

  opacidadeDaLuz(room: OfficeRoomId): number | null {
    return this.lighting.opacidadeDe(room);
  }

  elenco(): Map<number, EmployeeCharacter> {
    return this.employees;
  }

  frameAtual(): ImageFrame {
    return this.frame;
  }
}

/** Mantido para compatibilidade com qualquer import antigo pelo nome anterior. */
export { OfficeScene as CenaEscritorio };
