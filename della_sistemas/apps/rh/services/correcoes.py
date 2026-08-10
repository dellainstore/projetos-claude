"""Correções de ponto propostas pelo funcionário e aprovadas pelo gestor."""

from datetime import date, datetime, time

from django.utils import timezone

from apps.rh.models import BatidaPonto, CorrecaoPonto


def _aware(d: date, t: time):
    return timezone.make_aware(datetime.combine(d, t))


def sem_almoco_aprovado(colaborador, dia: date) -> bool:
    """True se há uma correção aprovada declarando que o dia não teve almoço."""
    return CorrecaoPonto.objects.filter(
        colaborador=colaborador, data=dia, status="aprovada", sem_almoco=True
    ).exists()


def horarios_em_ordem(sem_almoco: bool, e, sa, va, s) -> bool:
    """True se os horários preenchidos estão em ordem cronológica crescente.

    Um dia com só 1 batida real (ex.: só a saída) recebe o tipo "entrada" pela
    posição (ver reordenar_tipos_do_dia) — sem essa checagem, uma correção que
    mantém esse valor no campo errado gera um dia com "entrada às 18h, saída às
    9h" sem avisar ninguém."""
    seq = [e, None if sem_almoco else sa, None if sem_almoco else va, s]
    preenchidos = [v for v in seq if v is not None]
    return all(preenchidos[i] < preenchidos[i + 1] for i in range(len(preenchidos) - 1))


def aplicar_correcao(corr: CorrecaoPonto, usuario) -> None:
    """Aplica os horários propostos como batidas do dia e marca a correção aprovada.

    Com 'sem almoço', cria só entrada e saída (o almoço fica em branco → conta como
    1h a mais trabalhada, já que não há intervalo para descontar)."""
    c, dia = corr.colaborador, corr.data

    if corr.sem_almoco:
        alvo = {"entrada": corr.prop_entrada, "saida": corr.prop_saida}
    else:
        alvo = {
            "entrada": corr.prop_entrada,
            "saida_almoco": corr.prop_saida_almoco,
            "volta_almoco": corr.prop_volta_almoco,
            "saida": corr.prop_saida,
        }

    # Loja padrão: a única do colaborador, se houver exatamente uma.
    lojas = list(c.lojas_ponto.filter(ativo=True).values_list("id", flat=True))
    loja_padrao = lojas[0] if len(lojas) == 1 else None

    # Reencaixa pelo HORÁRIO, não pelo `tipo` já gravado: num dia parcial (ex.:
    # só 1 batida do app no dia todo) o tipo foi atribuído por posição e pode
    # estar errado (a única batida vira "entrada" mesmo sendo a saída real). Ao
    # casar pelo valor, preserva a origem/ajustado_por de quem bateu de fato —
    # só cria como "manual" o horário que não corresponde a nenhuma batida
    # existente.
    restantes = list(BatidaPonto.objects.filter(colaborador=c, momento__date=dia))

    aplicados: list[str] = []
    for tipo in ("entrada", "saida_almoco", "volta_almoco", "saida"):
        hora = alvo.get(tipo)
        if hora is None:
            continue
        momento = _aware(dia, hora)
        # Comparação por minuto: o form só envia HH:MM (sem segundos), mas a
        # batida real do app grava o momento exato (com segundos) — uma
        # comparação exata nunca bateria e apagaria/recriaria como "manual"
        # até as batidas que vieram do app sem alteração nenhuma.
        casada = next(
            (b for b in restantes if b.momento.replace(second=0, microsecond=0) == momento),
            None,
        )
        if casada:
            restantes.remove(casada)
            if casada.tipo != tipo:
                # Só o rótulo interno (tipo) estava errado — a batida em si
                # (horário, origem, ajustado_por) não mudou, então não conta
                # como "aplicado" nesta aprovação (ver histórico/campos_aplicados).
                casada.tipo = tipo
                casada.save(update_fields=["tipo"])
        else:
            BatidaPonto.objects.create(
                colaborador=c, momento=momento, tipo=tipo, loja_id=loja_padrao,
                dentro_raio=True, origem="manual", ajustado_por=usuario,
            )
            aplicados.append(tipo)

    # Batidas do dia que sobraram sem par no formulário (horário movido de
    # campo, ou descartado) → substituídas pelo conjunto acima.
    for b in restantes:
        b.delete()

    corr.status = "aprovada"
    corr.avaliado_por = usuario
    corr.avaliado_em = timezone.now()
    corr.campos_aplicados = ",".join(aplicados)
    corr.save(update_fields=["status", "avaliado_por", "avaliado_em", "campos_aplicados"])

    # Regenera a pendência do dia (vai resolver, já que o dia ficou completo).
    from apps.rh.services.notificacoes import gerar_pendencias_do_dia
    gerar_pendencias_do_dia(dia)
