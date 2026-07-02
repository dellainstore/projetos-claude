"""Afastamentos: conversão de anexos de imagem para WebP e consultas por dia."""

import io
import os
from datetime import date

from django.core.files.base import ContentFile

from apps.rh.models import Afastamento

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
    """Dias de férias já lançados (afastamentos tipo férias + gozos legados)."""
    afast = sum(
        a.dias for a in Afastamento.objects.filter(periodo_ferias=periodo, tipo="ferias")
    )
    legado = sum(g.dias for g in periodo.gozos.all())
    return afast + legado
