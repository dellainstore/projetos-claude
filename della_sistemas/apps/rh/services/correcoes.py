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

    # Só marca como "manual" o que a correção de fato criou/alterou — os slots já
    # batidos pelo app (travados no form) chegam com o mesmo horário e não podem
    # ter a origem sobrescrita, senão o histórico mente sobre quem bateu o quê.
    aplicados: list[str] = []
    for tipo in ("entrada", "saida_almoco", "volta_almoco", "saida"):
        hora = alvo.get(tipo)
        existente = BatidaPonto.objects.filter(
            colaborador=c, momento__date=dia, tipo=tipo
        ).first()
        if hora is None:
            if existente:
                existente.delete()
            continue
        momento = _aware(dia, hora)
        if existente:
            if existente.momento != momento:
                existente.momento = momento
                existente.origem = "manual"
                existente.ajustado_por = usuario
                existente.save(update_fields=["momento", "origem", "ajustado_por"])
                aplicados.append(tipo)
        else:
            BatidaPonto.objects.create(
                colaborador=c, momento=momento, tipo=tipo, loja_id=loja_padrao,
                dentro_raio=True, origem="manual", ajustado_por=usuario,
            )
            aplicados.append(tipo)

    corr.status = "aprovada"
    corr.avaliado_por = usuario
    corr.avaliado_em = timezone.now()
    corr.campos_aplicados = ",".join(aplicados)
    corr.save(update_fields=["status", "avaliado_por", "avaliado_em", "campos_aplicados"])

    # Regenera a pendência do dia (vai resolver, já que o dia ficou completo).
    from apps.rh.services.notificacoes import gerar_pendencias_do_dia
    gerar_pendencias_do_dia(dia)
