/**
 * Cena 2D do escritorio.
 *
 * A planta inteira vem da API (`salas`): sala nova no banco vira sala nova no
 * mapa, sem tocar aqui. As personagens sao posicionadas pelo estado que o
 * servidor devolveu, e SO por ele. A cena nunca deriva estado proprio: se uma
 * personagem esta andando e chega uma resposta dizendo outra coisa, a
 * caminhada e' cancelada e ela vai para onde o servidor mandou.
 */

import Phaser from "phaser";

import type { Cena, Personagem, Sala } from "../types";
import {
  caminho,
  corredorY,
  distancia,
  limitesDoMundo,
  vagasPorPersonagem,
  type Ponto,
} from "./mapa";
import { CENARIO, clarear, escurecer, hex } from "./paleta";
import { Personagem2D } from "./personagem";

const PROFUNDIDADE = {
  piso: 0,
  sala: 1,
  movel: 2,
  personagem: 10,
  escuridao: 20,
  hud: 30,
} as const;

const ROTULO_LOJA: Record<Cena["loja"]["estado"], string> = {
  CLOSED: "Loja fechada",
  OPENING: "Abrindo a loja",
  OPEN: "Loja aberta",
  OPEN_LUNCH_ONLY: "Horário de almoço",
  CLOSED_WITH_PENDING: "Fechada · há registro para conferir",
};

export class CenaEscritorio extends Phaser.Scene {
  private salas: Sala[] = [];
  private assinaturaSalas = "";
  private corredor: number | null = null;

  private camadaMapa!: Phaser.GameObjects.Container;
  private camadaAtores!: Phaser.GameObjects.Container;
  private escuridao!: Phaser.GameObjects.Rectangle;
  private porta!: Phaser.GameObjects.Rectangle;
  private faixa!: Phaser.GameObjects.Text;

  private readonly personagens = new Map<number, Personagem2D>();
  private pendente: Cena | null = null;
  private pronta = false;

  constructor() {
    super("escritorio");
  }

  create(): void {
    this.cameras.main.setBackgroundColor(hex(CENARIO.fundo));
    // Duas camadas: redesenhar o mapa (`removeAll(true)`) nao pode destruir as
    // personagens, que vivem na camada de cima.
    this.camadaMapa = this.add.container(0, 0);
    this.camadaAtores = this.add.container(0, 0);
    this.camadaAtores.setDepth(PROFUNDIDADE.personagem);

    // O preenchimento fica opaco e quem varia e' o alpha do objeto (que e' o
    // que o tween anima). Nascer com `fillAlpha: 0` faria a escuridao nunca
    // aparecer, por mais que o alpha subisse.
    this.escuridao = this.add.rectangle(0, 0, 10, 10, CENARIO.luzApagada, 1);
    this.escuridao.setOrigin(0, 0);
    this.escuridao.setAlpha(0);
    this.escuridao.setDepth(PROFUNDIDADE.escuridao);

    this.faixa = this.add.text(12, 10, "", {
      fontFamily: "system-ui, sans-serif",
      fontSize: "13px",
      color: hex(CENARIO.texto),
      backgroundColor: "#ffffffcc",
      padding: { x: 8, y: 4 },
    });
    this.faixa.setDepth(PROFUNDIDADE.hud);

    this.pronta = true;
    if (this.pendente) {
      const guardada = this.pendente;
      this.pendente = null;
      this.aplicar(guardada);
    }
  }

  /** Ponto de entrada unico: recebe a resposta da API e reflete na cena. */
  aplicar(dados: Cena): void {
    if (!this.pronta) {
      this.pendente = dados;
      return;
    }
    this.garantirMapa(dados.salas);
    this.aplicarLoja(dados);
    this.aplicarPersonagens(dados);
  }

  // ── mapa ───────────────────────────────────────────────────────────────

  private garantirMapa(salas: Sala[]): void {
    const assinatura = JSON.stringify(
      salas.map((s) => [s.slug, s.pos_x, s.pos_y, s.largura, s.altura, s.nome]),
    );
    if (assinatura === this.assinaturaSalas) return;
    this.assinaturaSalas = assinatura;
    this.salas = salas;
    this.corredor = corredorY(salas);
    this.desenharMapa();
  }

  private desenharMapa(): void {
    this.camadaMapa.removeAll(true);
    const mundo = limitesDoMundo(this.salas);
    const margem = 24;
    const largura = mundo.largura + margem * 2;
    const altura = mundo.altura + margem * 2 + 28;
    this.scale.setGameSize(largura, altura);
    this.camadaMapa.setPosition(margem, margem + 28);
    this.camadaAtores.setPosition(margem, margem + 28);

    this.escuridao.setPosition(0, 0);
    this.escuridao.setSize(largura, altura);

    const piso = this.add.graphics();
    piso.fillStyle(CENARIO.piso, 1);
    piso.fillRoundedRect(-12, -12, mundo.largura + 24, mundo.altura + 24, 14);
    piso.lineStyle(2, CENARIO.parede, 1);
    piso.strokeRoundedRect(-12, -12, mundo.largura + 24, mundo.altura + 24, 14);
    piso.setDepth(PROFUNDIDADE.piso);
    this.camadaMapa.add(piso);

    for (const sala of this.salas) this.desenharSala(sala);

    // Porta da loja: na borda esquerda da sala de entrada, ou do mapa.
    const entrada = this.salas.find((s) => s.slug === "store-entrance") ?? this.salas[0];
    const py = entrada ? entrada.pos_y + entrada.altura / 2 : mundo.altura / 2;
    this.porta = this.add.rectangle(-12, py, 8, 52, CENARIO.porta);
    this.porta.setOrigin(0.5, 0.5);
    this.porta.setDepth(PROFUNDIDADE.movel);
    this.camadaMapa.add(this.porta);
  }

  private desenharSala(sala: Sala): void {
    const g = this.add.graphics();
    g.fillStyle(CENARIO.sala, 1);
    g.fillRoundedRect(sala.pos_x, sala.pos_y, sala.largura, sala.altura, 10);
    g.lineStyle(2, CENARIO.salaBorda, 1);
    g.strokeRoundedRect(sala.pos_x, sala.pos_y, sala.largura, sala.altura, 10);
    g.setDepth(PROFUNDIDADE.sala);

    const titulo = this.add.text(sala.pos_x + 10, sala.pos_y + 8, sala.nome, {
      fontFamily: "system-ui, sans-serif",
      fontSize: "11px",
      color: hex(CENARIO.textoFraco),
    });
    titulo.setDepth(PROFUNDIDADE.sala);

    this.camadaMapa.add([g, titulo, ...this.desenharMoveis(sala)]);
  }

  /** Moveis por tipo de sala. Sala desconhecida ganha o basico. */
  private desenharMoveis(sala: Sala): Phaser.GameObjects.GameObject[] {
    const g = this.add.graphics();
    g.setDepth(PROFUNDIDADE.movel);
    const cx = sala.pos_x + sala.largura / 2;
    const base = sala.pos_y + sala.altura;

    if (sala.slug === "cafeteria") {
      // Mesa com duas cadeiras.
      g.fillStyle(CENARIO.movelEscuro, 1);
      g.fillRoundedRect(cx - 46, base - 58, 92, 30, 6);
      g.fillStyle(CENARIO.movel, 1);
      g.fillRoundedRect(cx - 46, base - 62, 92, 10, 5);
      g.fillStyle(CENARIO.movelEscuro, 1);
      g.fillRoundedRect(cx - 66, base - 52, 14, 16, 4);
      g.fillRoundedRect(cx + 52, base - 52, 14, 16, 4);
      return [g];
    }

    if (sala.slug === "store-entrance") {
      // Tapete de entrada.
      g.fillStyle(escurecer(CENARIO.piso, 0.08), 1);
      g.fillRoundedRect(sala.pos_x + 14, base - 40, sala.largura - 28, 24, 6);
      return [g];
    }

    // Showroom: duas araras e um espelho.
    g.fillStyle(CENARIO.movelEscuro, 1);
    g.fillRect(sala.pos_x + 26, sala.pos_y + 44, sala.largura - 52, 4);
    g.fillRect(sala.pos_x + 26, sala.pos_y + 44, 3, 34);
    g.fillRect(sala.pos_x + sala.largura - 29, sala.pos_y + 44, 3, 34);
    g.fillStyle(clarear(CENARIO.movel, 0.2), 1);
    for (let i = 0; i < 6; i += 1) {
      const x = sala.pos_x + 36 + i * ((sala.largura - 72) / 5);
      g.fillRoundedRect(x - 5, sala.pos_y + 48, 10, 22, 3);
    }
    g.fillStyle(0xdfe7ec, 1);
    g.fillRoundedRect(sala.pos_x + sala.largura - 30, base - 66, 16, 48, 6);
    return [g];
  }

  // ── loja ───────────────────────────────────────────────────────────────

  private aplicarLoja(dados: Cena): void {
    const alvo = dados.loja.luzesAcesas ? 0 : 0.58;
    if (Math.abs(this.escuridao.alpha - alvo) > 0.01) {
      this.tweens.killTweensOf(this.escuridao);
      this.tweens.add({
        targets: this.escuridao,
        alpha: alvo,
        duration: 700,
        ease: "Sine.easeInOut",
      });
    }

    if (this.porta) {
      const aberta = dados.loja.portaAberta;
      this.tweens.killTweensOf(this.porta);
      this.tweens.add({
        targets: this.porta,
        scaleY: aberta ? 0.25 : 1,
        duration: 500,
        ease: "Cubic.easeInOut",
      });
    }

    const pendencia = dados.loja.pendencias > 0;
    this.faixa.setText(ROTULO_LOJA[dados.loja.estado] ?? dados.loja.estado);
    this.faixa.setColor(hex(pendencia ? CENARIO.alerta : CENARIO.texto));
  }

  // ── personagens ────────────────────────────────────────────────────────

  private aplicarPersonagens(dados: Cena): void {
    const vagas = vagasPorPersonagem(
      dados.salas,
      dados.personagens.map((p) => ({ id: p.id, sala: p.sala })),
    );
    const porSlug = new Map(dados.salas.map((s) => [s.slug, s]));
    const vistos = new Set<number>();

    for (const p of dados.personagens) {
      vistos.add(p.id);
      const vaga = vagas.get(p.id);
      let ator = this.personagens.get(p.id);

      if (ator && ator.precisaRecriar(p)) {
        ator.destruir();
        this.personagens.delete(p.id);
        ator = undefined;
      }

      if (!ator) {
        const inicial = vaga ?? this.pontoDeEntrada();
        ator = new Personagem2D(this, p, inicial);
        ator.anexarEm(this.camadaAtores);
        ator.salaAtual = p.sala;
        this.personagens.set(p.id, ator);
        ator.aplicar(p);
        if (vaga) ator.mostrar(true);
        continue;
      }

      ator.aplicar(p);
      this.moverPara(ator, p, vaga ?? null, porSlug);
    }

    for (const [id, ator] of this.personagens) {
      if (vistos.has(id)) continue;
      ator.destruir();
      this.personagens.delete(id);
    }
  }

  private moverPara(
    ator: Personagem2D,
    dados: Personagem,
    vaga: Ponto | null,
    porSlug: Map<string, Sala>,
  ): void {
    // Sem sala: saiu de cena (folga, ausência, batida faltando, fim do dia).
    if (vaga === null || dados.sala === null) {
      ator.salaAtual = null;
      ator.esconder();
      return;
    }

    const salaDestino = porSlug.get(dados.sala) ?? null;
    const salaOrigem = ator.salaAtual ? porSlug.get(ator.salaAtual) ?? null : null;

    // Entrando em cena agora: aparece na porta e caminha até o lugar.
    if (!ator.estaVisivel) {
      const entrada = this.pontoDeEntrada();
      ator.posicionar(entrada);
      ator.mostrar();
      ator.salaAtual = dados.sala;
      const pontos = caminho(entrada, vaga, this.salaDeEntrada(), salaDestino, this.corredor);
      ator.caminharPor(pontos, Personagem2D.duracaoPara(distancia(entrada, pontos)));
      return;
    }

    const mudouDeSala = ator.salaAtual !== dados.sala;
    ator.salaAtual = dados.sala;

    if (!mudouDeSala) {
      // Mesma sala: só acomoda a vaga (entrou ou saiu alguém do ambiente).
      const longe = Phaser.Math.Distance.Between(ator.x, ator.y, vaga.x, vaga.y) > 4;
      if (longe) {
        ator.caminharPor([vaga], Personagem2D.duracaoPara(
          Phaser.Math.Distance.Between(ator.x, ator.y, vaga.x, vaga.y),
        ));
      }
      return;
    }

    const pontos = caminho(ator.posicao, vaga, salaOrigem, salaDestino, this.corredor);
    ator.caminharPor(pontos, Personagem2D.duracaoPara(distancia(ator.posicao, pontos)));
  }

  private salaDeEntrada(): Sala | null {
    return this.salas.find((s) => s.slug === "store-entrance") ?? this.salas[0] ?? null;
  }

  private pontoDeEntrada(): Ponto {
    const entrada = this.salaDeEntrada();
    if (!entrada) return { x: 0, y: 0 };
    return { x: entrada.pos_x + 16, y: entrada.pos_y + entrada.altura * 0.62 };
  }
}
