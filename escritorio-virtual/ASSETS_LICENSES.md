# Assets do Escritório Virtual — origem e licença

## `della_sistemas/static/escritorio/office-bg.png` (arte oficial do cenário)

- **Origem:** fornecida pelo dono do projeto nesta conversa (arquivo salvo
  como `ChatGPT Image 19 de set. de 2026, 10_23_18.png`, 1536×1024px),
  gerada por ferramenta de IA de geração de imagem (indicado pelo nome do
  arquivo).
- **Uso neste projeto:** fundo único da cena, carregado como textura do
  Phaser (`BootScene`), exibido sem edição/recorte — a planta (Show Room,
  Anacã, Refeitório, corredor, entrada) e a arte inteira são as originais
  fornecidas.
- **Responsabilidade sobre a licença:** este arquivo não foi gerado, baixado
  nem obtido por mim (Claude) de nenhuma fonte externa — foi entregue
  diretamente pelo dono do projeto como "a base visual oficial". Eu não
  tenho como verificar os termos de uso da ferramenta de geração usada nem
  confirmar direitos de uso comercial da imagem resultante. **Recomendação:**
  confirmar com os termos de serviço da ferramenta que gerou a imagem se o
  uso pretendido (painel interno da empresa, não redistribuído a terceiros)
  está coberto antes de considerar este asset definitivo.

## `della_sistemas/static/escritorio/office-bg-placeholder.svg`

- **Origem:** criado por mim (Claude) inteiramente do zero — retângulos e
  texto coloridos via SVG simples, sem base em nenhuma arte de terceiros.
- **Licença:** mesma do restante do código deste repositório (uso interno
  da D'ELLA). Livre para editar/remover.
- **Papel:** fallback automático enquanto `office-bg.png` não existisse no
  repositório (ver `apps/escritorio_virtual/views/diagnostico.py::_bg_estatico`).
  Com `office-bg.png` já presente, o placeholder não é mais servido, mas
  fica no repositório como rede de segurança caso o arquivo oficial seja
  removido por engano.

## Personagens (Tina, Sara, Michelle) — pixel art PROCEDURAL

- **Origem:** desenhadas por código, pixel a pixel, em
  `src/actors/EmployeeCharacter.ts` (função `desenharPersonagem`) — blocos de
  cor sólida com contorno escuro, sem anti-aliasing, renderizados num canvas
  20×30px e ampliados com filtro NEAREST (sem borrão). **Não é um
  spritesheet desenhado à mão, nem arte de terceiros.**
- **Por que não uma reprodução das fotos da Tina e da Sara:** nesta
  conversa, apenas a imagem do cenário limpo chegou de fato como arquivo. A
  "imagem conceitual com Tina, Sara e Philip" e as fotos da Tina e da Sara
  mencionadas no pedido **não chegaram** (nem como arquivo, nem
  visualmente) — só o texto do pedido as descreve. Não é possível usar como
  referência visual algo que não foi recebido. As paletas de cor em
  `src/config/employees.ts` são originais, escolhidas para serem
  visualmente distintas entre si e combinarem com a cor de cada ambiente
  (Show Room em tons de vinho, Anacã em verde) — não uma tentativa de
  reproduzir a aparência real de ninguém.
- **Licença:** código do próprio projeto (uso interno da D'ELLA).

## Marcadores dos objetos interativos (computador, arara, cafeteira, geladeira, mesa)

- **Origem:** círculos coloridos gerados via Phaser Graphics
  (`src/systems/InteractionSystem.ts`) — não emoji (que depende de fonte
  instalada no sistema; o ambiente de captura automatizada, por exemplo, não
  tem fonte de emoji e mostrava quadrados vazios) nem imagem externa.
- **Licença:** código do próprio projeto.

---

## Especificação exata para os spritesheets reais (quando/se forem produzidos)

Caso decidam substituir a pixel art procedural por spritesheets desenhados à
mão (ou gerados por IA especificamente para as personagens), a especificação
abaixo é o que faria a substituição em `EmployeeCharacter.ts` ser direta,
sem mudar mais nada no resto do projeto:

| Item | Especificação |
|---|---|
| **Formato do arquivo** | PNG com transparência (fundo alfa), um spritesheet por personagem OU um atlas único com todas |
| **Tamanho de cada frame** | 32×48px (proporção 2:3, compatível com a escala atual de exibição) |
| **Direções** | 4: baixo (frente), cima (costas), esquerda, direita — **ou** 2 (frente/costas) + espelhamento automático para esquerda/direita, como já é feito hoje |
| **Frames por direção — parada** | 1 frame (idle) |
| **Frames por direção — andando** | 2 a 4 frames (ciclo de caminhada) |
| **Frames extras desejáveis** | 1 frame "trabalhando" (ex.: mexendo no computador ou organizando arara) e 1 frame "sentada/almoço", se possível |
| **Total mínimo por personagem** | 4 direções × (1 idle + 2 andando) = 12 frames, ou 2 direções × 3 = 6 frames se optar por espelhamento |
| **Grade do spritesheet** | Frames em grade uniforme (ex.: 4 colunas × N linhas), para carregar via `this.load.spritesheet(key, url, { frameWidth: 32, frameHeight: 48 })` |
| **Nomenclatura sugerida dos arquivos** | `tina.png`, `sara.png`, `michelle.png` em `della_sistemas/static/escritorio/characters/` |
| **Onde plugar** | `BootScene.preload()` carrega os spritesheets; `EmployeeCharacter` troca a textura procedural pelos frames reais — o contrato (`posicionar`, `caminharPor`, `aplicar`, `mostrar`, `esconder`) não muda |

Nenhuma dessas imagens foi gerada nesta rodada — a pixel art procedural
descrita acima é o que está em produção enquanto isso não existir.
