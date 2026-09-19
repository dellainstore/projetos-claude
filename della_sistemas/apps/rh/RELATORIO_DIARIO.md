# Relatório diário do ponto (decisões aprovadas, **ainda não implementado**)

Nada deste documento existe em código. Nenhum model foi criado, nenhum cron
foi agendado e nenhuma notificação foi enviada. É o registro das decisões
aprovadas em 2026-09-19, para a fase em que o relatório for construído.

O cálculo e a fonte dos dados ficam aqui, em `apps.rh` (é lógica de ponto e
reutiliza `services/ponto.banco_de_horas()`). O escritório virtual só poderá
exibir um selo com link, nunca calcular nada por conta própria.

---

## 1. Autorização e destinatário são conceitos diferentes

Esta é a correção mais importante ao plano original.

| Conceito | O que controla | Onde vive |
|---|---|---|
| **Autorização** | Quem **pode abrir** o relatório no painel | permissão `rh.relatorio_diario` |
| **Destinatário** | Quem **recebe** a notificação | inscrição explícita, tabela própria |

A permissão **não** inscreve ninguém automaticamente. Conceder acesso a uma
gestora nova no futuro deve deixá-la ver o relatório sem passar a mandar
mensagem para ela. As duas coisas mudam por caminhos separados, de propósito.

Inicialmente a destinatária será Adriana, mas **nenhum id, nome, e-mail,
telefone ou chat id pode ficar hardcoded** (nem em código, nem em `.env`). A
inscrição é um registro de banco, criado na tela de configuração.

Contexto que motivou a separação, levantado na auditoria:

- `papel="gestor"` não identifica a gestora: Tina, Sara e Michelle também são
  `gestor`;
- Adriana (usuário `Drica`) está hoje com **todas** as permissões de RH em
  `False`, inclusive `rh.ponto_gerir`.

## 2. Relatório e entregas são tabelas separadas

Um único campo `canal`, `status` ou `enviado_em` dentro do relatório **não
serve**: o mesmo relatório pode ser entregue pelo sino interno e pelo
Telegram, com resultados diferentes em cada canal.

### `RelatorioPontoDiario` (conteúdo calculado)

```
id
data              DATE UNIQUE    -- idempotência estrutural do cálculo
gerado_em         DATETIME
payload           JSON           -- relatório congelado da data
resumo            CHAR(400)      -- texto curto da notificação
```

Reexecutar o job para a mesma data recalcula o `payload` (`update_or_create`
por `data`) e **não** dispara envio.

### `EntregaRelatorioPontoDiario` (uma linha por destino e canal)

```
id
relatorio       FK -> RelatorioPontoDiario
destinatario    FK -> core.User
canal           CHAR             -- interno | telegram | email
status          CHAR             -- pendente | enviado | erro
tentativas      INT DEFAULT 0
ultimo_erro     CHAR(500)
enviado_em      DATETIME NULL
reenvio_manual  BOOL DEFAULT False
reenviado_por   FK -> core.User NULL
criado_em       DATETIME

UNIQUE (relatorio, destinatario, canal)
```

A constraint de unicidade é o que garante a idempotência do **envio**: rodar
o job de novo não cria uma segunda entrega para o mesmo par. Um reenvio é uma
ação explícita, que marca `reenvio_manual` e registra `reenviado_por`.

### Inscrição de destinatários

Tabela própria (ex.: `InscricaoRelatorioDiario`), com
`UNIQUE (usuario, canal)` e um campo `ativo`. É daqui que o job monta a lista
de entregas, nunca de `papel` nem da permissão.

## 3. Regras de cálculo já levantadas

Reutilizar, sem reimplementar: `banco_de_horas()`, `horas_esperadas_no_dia()`,
`tempos_esperados_no_dia()`, `batidas_esperadas_no_dia()`,
`afastamento_no_dia()`, `feriados()`, `dia_incompleto()`, `obs_do_dia()`.

| Parâmetro | Valor aprovado | Origem |
|---|---|---|
| Horário de envio | 08:00 `America/Sao_Paulo` (`0 11 * * *` UTC) | configurável |
| Tolerância de atraso | a mesma de `ParametrosPonto` (hoje 10 min) | reutilizada, não duplicada |
| Almoço mínimo | 60 min, configurável | parâmetro novo |
| Almoço máximo | **desativado** até existir regra empresarial | parâmetro novo |

O servidor roda em UTC e o Brasil não tem horário de verão desde 2019, então
o deslocamento é fixo em três horas.

### Conceitos que **não** existem hoje no sistema

- **Atraso** e **saída antecipada** não existem como campo: seriam derivados
  comparando a batida real com `EscalaDia` mais a tolerância. São métricas
  novas e devem ser marcadas como tal.
- **Hora extra aprovada** não existe: não há fluxo de aprovação. O relatório
  precisa separar `tempo registrado`, `saldo calculado` e
  `hora extra potencial`, e sinalizar quando o dia foi zerado por
  `AbonoPonto` ou por afastamento remunerado. Nunca afirmar que houve hora
  extra reconhecida.
- **`ParametrosPonto.intervalo_minimo_minutos` não é o almoço mínimo.** Vale
  5 minutos e serve para bloquear clique duplo na tela de bater ponto.

### Limites estruturais a respeitar

- **Máximo de 4 batidas por dia.** `proximo_tipo()` devolve `None` na quinta e
  o grid da Jornada tem 4 colunas fixas: mais de um intervalo no mesmo dia
  **não é representável** hoje. O relatório informa "1 intervalo" ou "sem
  intervalo", nunca simula várias pausas.
- **Sábado da variante B não tem almoço** (`batidas_esperadas_no_dia()`
  devolve 2). A regra de almoço mínimo não pode disparar nesses dias.
- **Domingo e dias sem jornada**: `horas_esperadas_no_dia()` devolve 0 e
  `dia_incompleto()` devolve `False`. O relatório de segunda-feira diz "sem
  jornada prevista e sem ocorrências", sem gerar atraso nem ausência.
- **Batida ímpar**: `banco_de_horas()` devolve saldo 0 de propósito. O
  relatório mostra "registro incompleto" e **não inventa** horas nem saldo.
- **Antes de `ParametrosPonto.data_inicio`** (hoje 2026-07-01) nada é cobrado.

## 4. O que fica fora do relatório

Dado pessoal desnecessário. A notificação resumida leva contagens e um link;
o detalhamento por pessoa fica dentro do painel, atrás da permissão.
