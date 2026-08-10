"""Afastamentos: conversão de anexos de imagem para WebP e consultas por dia."""

import io
import os
from datetime import date, time
from decimal import Decimal

from django.core.files.base import ContentFile

from apps.rh.models import Afastamento

# Tipos de batida, na ordem esperada do dia (mesma ordem de apps/rh/services/ponto.py).
_SLOTS = ("entrada", "saida_almoco", "volta_almoco", "saida")

# Extensões de imagem que convertemos para WebP (PDF é mantido como está).
_IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp", ".heic", ".heif"}


def converter_anexo_para_webp(arquivo):
    """Recebe um UploadedFile. Se for imagem, devolve um ContentFile WebP (leve);
    se for PDF (ou qualquer não-imagem), devolve o arquivo original sem mexer.

    Retorna (conteudo, nome_final)."""
    nome = arquivo.name
    ext = os.path.splitext(nome)[1].lower()
    base = os.path.splitext(os.path.basename(nome))[0]

    if ext not in _IMG_EXT:
        return arquivo, nome  # PDF e afins: mantém

    from PIL import Image
    try:
        img = Image.open(arquivo)
        img.load()
    except Exception:
        # Não conseguiu abrir como imagem → mantém o original.
        arquivo.seek(0)
        return arquivo, nome

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=80, method=6)
    return ContentFile(buffer.getvalue()), f"{base}.webp"


def afastamento_no_dia(colaborador, dia: date) -> Afastamento | None:
    """Afastamento que cobre o dia (se houver)."""
    return (
        Afastamento.objects
        .filter(colaborador=colaborador, data_inicio__lte=dia, data_fim__gte=dia)
        .order_by("data_inicio")
        .first()
    )


def slots_dispensados_por_afastamento(colaborador, dia: date, af: Afastamento) -> set[str]:
    """Quais batidas do dia (entrada, saida_almoco, volta_almoco, saida) ficam
    dispensadas por causa do afastamento `af` (que já se sabe cobrir `dia`).

    Dia inteiro → dispensa as 4. Parcial → dispensa só as batidas cujo horário
    esperado (pela escala do colaborador) cai dentro de [hora_inicio, hora_fim].
    Sem referência de horário (sem escala, ou o dia da escala sem horários) →
    aproxima pelo meio-dia: intervalo até 12h dispensa a manhã (entrada + saída
    almoço), a partir de 12h dispensa a tarde (volta almoço + saída); um
    intervalo que atravessa o meio-dia sem referência melhor dispensa o dia
    todo (mais seguro não gerar pendência indevida do que cobrar em dobro)."""
    if af.dia_inteiro:
        return set(_SLOTS)
    if not af.hora_inicio or not af.hora_fim:
        return set(_SLOTS)

    from apps.rh.services.escala import tempos_esperados_no_dia
    tempos = tempos_esperados_no_dia(colaborador, dia)
    dispensados = {
        tipo for tipo, t in (tempos or {}).items()
        if t is not None and af.hora_inicio <= t <= af.hora_fim
    }
    if dispensados:
        return dispensados

    meio_dia = time(12, 0)
    if af.hora_fim <= meio_dia:
        return {"entrada", "saida_almoco"}
    if af.hora_inicio >= meio_dia:
        return {"volta_almoco", "saida"}
    return set(_SLOTS)


def horas_cobertas_por_afastamento(af: Afastamento, esperado: Decimal | None) -> Decimal:
    """Quantas horas da jornada esperada do dia o afastamento `af` cobre.

    Dia inteiro → cobre tudo (`esperado`). Parcial → a duração hora_fim − hora_inicio,
    nunca mais que `esperado` (evita "sobrar" crédito quando o intervalo informado
    é maior que a jornada do dia)."""
    esperado = esperado or Decimal("0")
    if af.dia_inteiro or not af.hora_inicio or not af.hora_fim:
        return esperado
    ini = af.hora_inicio.hour + af.hora_inicio.minute / 60
    fim = af.hora_fim.hour + af.hora_fim.minute / 60
    horas = Decimal(str(round(max(fim - ini, 0), 2)))
    return min(horas, esperado) if esperado else horas


def dias_afastados(colaborador, inicio: date, fim: date) -> dict[date, Afastamento]:
    """Mapa {dia: afastamento} para o período — usado na jornada e no banco de horas."""
    mapa: dict[date, Afastamento] = {}
    qs = Afastamento.objects.filter(
        colaborador=colaborador, data_inicio__lte=fim, data_fim__gte=inicio,
    )
    for af in qs:
        d = max(af.data_inicio, inicio)
        ultimo = min(af.data_fim, fim)
        while d <= ultimo:
            mapa.setdefault(d, af)
            d = date.fromordinal(d.toordinal() + 1)
    return mapa


def dias_ferias_gozados(periodo) -> int:
    """Dias de férias já lançados (afastamentos tipo férias + gozos legados).

    Todo GozoFerias lançado pelo módulo Férias já gera seu próprio Afastamento
    vinculado (campo `afastamento`) — só entram aqui os gozos antigos, sem
    vínculo, para não contar os dias em dobro."""
    afast = sum(
        a.dias for a in Afastamento.objects.filter(periodo_ferias=periodo, tipo="ferias")
    )
    legado = sum(g.dias for g in periodo.gozos.filter(afastamento__isnull=True))
    return afast + legado
