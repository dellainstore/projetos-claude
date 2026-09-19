# apps.escritorio_virtual

Projeção visual do controle de ponto. **Somente leitura.**

O ponto (`apps.rh`) continua sendo a fonte oficial. Este app não cria, não
altera e não apaga `BatidaPonto`, `Afastamento`, `AbonoPonto` nem
`CorrecaoPonto`. Não existe rota de escrita aqui, e a projeção nem sequer usa
`get_or_create` em tabelas de parâmetro (um GET de API não pode gravar nada).

## Por que projeção derivada, e não eventos

O estado de cada personagem é recalculado a cada leitura a partir de
`BatidaPonto` + escala + exceções de escala + feriados + afastamentos +
abonos + `ParametrosPonto`. Com isso, de graça:

| Exigência | Como é atendida |
|---|---|
| Idempotência | Recalcular é a operação normal, não um caso de erro |
| Só depois de confirmado no banco | A leitura só enxerga o que já foi commitado |
| `PUNCH_CORRECTED` / `PUNCH_DELETED` | A leitura seguinte já reflete; não há evento a processar |
| Reconciliação | Não existe estado duplicado para reconciliar |
| Retry, fila, outbox | Não há entrega que possa falhar |

O vocabulário de eventos (`CLOCK_IN`, `LUNCH_START`, `LUNCH_END`,
`CLOCK_OUT`) existe em `services/eventos.py`, derivado das batidas, com
`eventId = "ponto_<id>"`. Serve para animação e para o futuro replay, não
como mecanismo de transporte.

## Estados

### Personagem

| Estado | Quando | Persistido |
|---|---|---|
| `OFFLINE` | Sem batida e ainda dentro da janela normal de chegada; ator sem fonte de estado | derivado |
| `ARRIVING` | `CLOCK_IN` há menos de `evento_recente_segundos` | **efêmero** |
| `WORKING` | Última batida é `entrada` ou `volta_almoco` | derivado |
| `LUNCH` | Última batida é `saida_almoco` | derivado |
| `RETURNING_FROM_LUNCH` | `LUNCH_END` recente | **efêmero** |
| `LEAVING` | `CLOCK_OUT` recente | **efêmero** |
| `MISSING_PUNCH` | Dia encerrado e `rh.services.ponto.dia_incompleto()` verdadeiro, com batidas | derivado |
| `DAY_OFF` | Afastamento de dia inteiro, feriado, folga da escala, ou dia já abonado | derivado |
| `AWAY` | Afastamento parcial cobrindo o instante atual | derivado |
| `ABSENT` | Dia previsto, zero batidas, passou de `hora_entrada` + tolerância | derivado |
| `OFF_SHIFT` | Saiu normalmente e o dia está encerrado | derivado |

`AWAY`, `ABSENT` e `OFF_SHIFT` não estavam na lista original: existem para
não inventar sequência quando os dados estão incompletos. Sem eles, um
atestado de meio período ou uma falta viraria `MISSING_PUNCH` indevidamente,
e quem já foi embora ficaria igual a quem ainda não chegou.

Os três efêmeros derivam da idade da última batida, não de memória do
cliente. Por isso abrir a página 30 segundos depois de uma batida mostra a
animação, e abrir 10 minutos depois mostra a cena já parada no lugar certo.

### Loja

| Estado | Quando | Luzes |
|---|---|---|
| `CLOSED` | Ninguém presente, fora da janela | apagadas |
| `OPENING` | Todos os presentes acabaram de chegar | acesas |
| `OPEN` | Ao menos uma em `WORKING` ou `AWAY` | acesas |
| `OPEN_LUNCH_ONLY` | Todas as presentes no almoço | **acesas** |
| `CLOSED_WITH_PENDING` | Janela vencida e há `MISSING_PUNCH` | apagadas |

`OPEN_LUNCH_ONLY` é a distinção pedida: loja sem ninguém trabalhando no
momento não é loja encerrada.

## A loja não fica acesa a madrugada toda

Não há cron para isso. A regra é aplicada na leitura:

```
janela_fechamento = hora_saida (escala do dia) + margem_fechamento_minutos
                  ou hora_limite_absoluta, quando não há escala com saída
```

Passado esse instante sem `CLOCK_OUT`, a personagem vai para `MISSING_PUNCH`
e a loja para `CLOSED_WITH_PENDING`. **Nenhuma batida é inventada, alterada
ou corrigida**: só a representação visual muda, e a inconsistência fica
marcada. A pendência formal continua sendo gerada pelo job que já existe
(`verificar_ponto`, 00:10 BRT), e a correção só acontece em
`/rh/ponto/jornada/`, por quem tem `rh.ponto_gerir`.

O limite absoluto é **fallback**, não teto da margem: uma escala que sai às
19:00 com margem de 90 min fecha às 20:30, e não às 23:00.

## Resolução de sala

O vínculo com a loja física mora em `SalaEscritorio.loja`
(`OneToOne` com `rh.LocalEmpresa`), não na personagem. Quem sabe onde a
pessoa está é a batida; quem sabe o que aquela loja representa no mapa é a
sala. A comparação em runtime é por chave estrangeira, nunca por texto.

Ordem (`services/salas.py`):

1. loja da batida válida mais recente do dia → sala mapeada (`origem: loja`);
2. sala padrão da personagem (`origem: sala_padrao`);
3. entrada da loja (`origem: fallback`) + aviso técnico;
4. sem sala (`origem: indefinida`) + aviso técnico.

Os avisos carregam só o id da personagem, nunca nome ou dado pessoal.

A sala **exibida** depende do estado: almoço leva ao refeitório, chegada e
saída ficam na entrada, e estados sem presença física não renderizam
personagem nenhuma.

## Comandos

```bash
# Diagnóstico (somente leitura, não gera notificação, não imprime GPS)
manage.py escritorio_debug
manage.py escritorio_debug --data 2026-09-18
manage.py escritorio_debug --colaborador-id 1 --agora 14:30
manage.py escritorio_debug --json

# Elenco (escreve só na tabela de personagens; não toca no ponto)
manage.py escritorio_personagem --colaboradores
manage.py escritorio_personagem --colaborador-id 1 --personagem tina --sala showroom-1
manage.py escritorio_personagem --listar
```

O `escritorio_debug` imprime, por personagem, o veredito oficial
(`dia_incompleto()`) e o link direto para a Jornada daquele dia, para
conferência lado a lado.

## API

`GET /escritorio/api/estado/` — sessão obrigatória + permissão
`escritorio.ver`. Anônimo recebe 401 em JSON, autenticado sem permissão
recebe 403, métodos de escrita recebem 405. Não existe endpoint público.

`ETag` determinístico, com suporte a `If-None-Match` e resposta 304. O campo
`geradoEm` fica fora do cálculo do ETag (muda a cada requisição sem
representar mudança de cena).

`services/serializacao.py` é a única função que monta o corpo da resposta, e
monta campo a campo a partir de uma lista fechada. Ficam fora, de propósito:
GPS, saldo de horas, tipo de afastamento, o `motivo` técnico da projeção e o
nome civil completo (vai só o primeiro nome).

**Limite conhecido da v1:** existe uma única permissão de leitura. Quem tem
`escritorio.ver` enxerga o estado de presença de todas as personagens,
inclusive `MISSING_PUNCH` e `ABSENT`. O recorte por perfil (funcionária vê só
o próprio, gestora vê tudo) e a visão pública sanitizada são fase posterior.
Enquanto isso, conceda a permissão deliberadamente.

## Interruptor

`ESCRITORIO_ATIVO` no `.env` (padrão **False**). Com False, todas as rotas de
`/escritorio/` respondem 404.

O padrão é desligado porque o gunicorn deste painel roda **sem `--preload`** e
com `--max-requests 500`: cada worker reciclado importa o código do disco
sozinho, então código novo entra em produção aos poucos, sem ninguém dar
restart. Com a feature desligada por padrão, nada aparece até alguém ligar
explicitamente, depois de aplicar a migration.

## Cenário 2D

O visual vive no workspace `projetos-claude/escritorio-virtual/` (Phaser 3 +
TypeScript, build only) e consome exclusivamente `GET /escritorio/api/estado/`.

O que o backend precisa garantir para a cena funcionar, e que os testes
travam:

- **as salas vão no payload com posição e tamanho.** A planta do mapa é a
  tabela `SalaEscritorio`, não uma constante no frontend. Mover ou acrescentar
  uma sala no banco muda o mapa e o trajeto das personagens sem deploy de JS;
- **`sala` é `null` para quem não está fisicamente presente** (folga, ausência,
  batida faltando, fim de expediente). O frontend usa isso para tirar a
  personagem de cena; é o que impede alguém aparecer trabalhando de madrugada;
- **os slugs `store-entrance` e `cafeteria` têm papel fixo**: a cena manda
  quem chega e quem sai para a entrada, e quem está em `LUNCH` para o
  refeitório. Renomear esses dois slugs quebra a encenação (as demais salas
  podem ter qualquer slug).

## Preparo para agentes de IA

`PersonagemEscritorio.tipo_ator` já distingue `HUMAN_EMPLOYEE`, `AI_AGENT` e
`SYSTEM_ACTOR`. Só o humano tem estado na v1 (vindo do ponto); os outros
ficam em `OFFLINE` com motivo `ator_nao_humano`. Nenhuma integração de IA foi
feita, e nenhuma é necessária para a modelagem evoluir.
