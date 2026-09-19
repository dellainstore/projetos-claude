# Referência visual

Coloque aqui a imagem de referência do escritório, com este nome:

```
escritorio-virtual-referencia.png
```

**Esta pasta não entra no bundle.** O Vite só empacota o que está em `src/`,
então a imagem fica no repositório para comparação e não é baixada por
ninguém que abrir a página.

## Por que o arquivo não está aqui

A imagem foi enviada no chat, e eu não consigo gravar em disco um anexo de
conversa. Salve o original você mesmo nesta pasta. Não edite nem
sobrescreva o arquivo que você enviou: ele é a referência, não um asset.

## O que foi reproduzido a partir dela

| Elemento da referência | Onde está no código |
|---|---|
| Planta (Show Room à esquerda, Anacã à direita, refeitório no topo, entrada embaixo) | `della_sistemas/apps/escritorio_virtual/migrations/0003_planta_integrada.py` |
| Proporção 1440x900 (a referência tem 1462x907) | mesma migration, com teste em `tests/geometry.test.ts` |
| Corredor central ligando tudo | sala `corredor` na mesma migration |
| Portas entre os cômodos | deduzidas da geometria em `src/environment/geometry.ts` |
| Paleta (carvão, creme, dourado, rosa queimado) | `src/config/rooms.ts`, objeto `COR` |
| Mobiliário de cada ambiente | `src/config/rooms.ts`, `MOBILIARIO` |
| Placas "SHOW ROOM" / "ANACÃ" / "REFEITÓRIO" | `src/scenes/OfficeScene.ts`, `desenharPlaca` |
| Iluminação por ambiente | `src/environment/LightingController.ts` |
| Porta dupla da entrada | `src/environment/DoorController.ts` |

**As funcionárias da referência não viraram cenário.** Elas são entidades
independentes (`src/actors/Character.ts`), posicionadas pelo estado que vem
do ponto, e entram, andam, almoçam e saem. Nada delas está desenhado no
fundo.
