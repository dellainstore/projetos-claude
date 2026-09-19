"""Testes da projeção do escritório virtual.

Todos os cenários são montados com fixtures próprias, em banco de teste
isolado (o runner do Django cria um SQLite separado). Nenhum dado real é
tocado.
"""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.escritorio_virtual.models import (
    ParametrosEscritorio,
    PersonagemEscritorio,
    SalaEscritorio,
)
from apps.escritorio_virtual.services import salas as svc_salas
from apps.escritorio_virtual.services.projecao import (
    EstadoLoja,
    EstadoPersonagem,
    Motivo,
    projetar_cena,
)
from apps.rh.models import (
    AbonoPonto,
    Afastamento,
    BatidaPonto,
    Colaborador,
    Escala,
    EscalaDia,
    LocalEmpresa,
    ParametrosPonto,
)

# Datas de referência (conferidas contra o calendário real):
#   2026-09-14 seg  -> variante A (sem sábado): 09:00-19:00, almoço 12:00-13:00
#   2026-09-12 sáb  -> variante B: 10:00-14:00, sem almoço (2 batidas)
#   2026-09-13 dom  -> sem jornada
#   2026-09-07 seg  -> feriado (Independência)
SEGUNDA_A = date(2026, 9, 14)
SABADO_B  = date(2026, 9, 12)
DOMINGO   = date(2026, 9, 13)
FERIADO   = date(2026, 9, 7)
ANCORA_B  = date(2026, 7, 4)


def aware(dia: date, hora: int, minuto: int = 0, segundo: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto, segundo)))


@contextmanager
def hoje_fixo(dia: date):
    """Congela `timezone.localdate()` para testar um dia "em andamento"."""
    with patch("django.utils.timezone.localdate", return_value=dia):
        yield


@contextmanager
def instante_fixo(dia: date, hora: int, minuto: int = 0):
    """Congela o dia E o instante. Necessário quando o código sob teste chama
    `projetar_cena()` sem argumentos (a API), que resolve os dois sozinha."""
    momento = aware(dia, hora, minuto)
    with patch("django.utils.timezone.localdate", return_value=dia), \
         patch("django.utils.timezone.now", return_value=momento):
        yield momento


class BaseEscritorioTestCase(TestCase):
    """Cenário mínimo: duas lojas, quatro salas, uma escala que alterna sábado
    e uma colaboradora que bate ponto."""

    def setUp(self):
        ParametrosPonto.objects.create(
            pk=1, tolerancia_minutos=10, intervalo_minimo_minutos=5,
            data_inicio=date(2026, 7, 1),
        )
        ParametrosEscritorio.objects.create(pk=1)

        self.loja_sp = LocalEmpresa.objects.create(
            nome="Show Room SP", latitude=Decimal("-23.5"), longitude=Decimal("-46.6"),
        )
        self.loja_anaca = LocalEmpresa.objects.create(
            nome="Loja Anacã", latitude=Decimal("-23.4"), longitude=Decimal("-46.5"),
        )

        # As salas já vêm da migration de dados (0002_salas_iniciais); aqui só
        # completamos o vínculo com as lojas, que naquele momento não existiam.
        self.entrada, _ = SalaEscritorio.objects.update_or_create(
            slug=svc_salas.SLUG_ENTRADA,
            defaults={"nome": "Entrada", "ordem": 0, "ativo": True, "loja": None},
        )
        self.showroom1, _ = SalaEscritorio.objects.update_or_create(
            slug="showroom-1",
            defaults={"nome": "Showroom 1", "ordem": 1, "ativo": True, "loja": self.loja_sp},
        )
        self.showroom2, _ = SalaEscritorio.objects.update_or_create(
            slug="showroom-2",
            defaults={"nome": "Showroom 2", "ordem": 2, "ativo": True, "loja": self.loja_anaca},
        )
        self.refeitorio, _ = SalaEscritorio.objects.update_or_create(
            slug=svc_salas.SLUG_REFEITORIO,
            defaults={"nome": "Refeitório", "ordem": 3, "ativo": True, "loja": None},
        )

        self.escala = Escala.objects.create(nome="SHOW ROOM SP", alterna_sabado=True)
        for dia_semana in range(0, 4):  # seg a qui
            EscalaDia.objects.create(
                escala=self.escala, variante="A", dia_semana=dia_semana, trabalha=True,
                hora_entrada=time(9, 0), hora_saida_almoco=time(12, 0),
                hora_volta_almoco=time(13, 0), hora_saida=time(19, 0),
            )
        EscalaDia.objects.create(
            escala=self.escala, variante="A", dia_semana=4, trabalha=True,
            hora_entrada=time(9, 0), hora_saida_almoco=time(12, 0),
            hora_volta_almoco=time(13, 0), hora_saida=time(18, 0),
        )
        for dia_semana in (5, 6):
            EscalaDia.objects.create(
                escala=self.escala, variante="A", dia_semana=dia_semana, trabalha=False,
            )
        for dia_semana in range(0, 5):  # seg a sex, semana COM sábado
            EscalaDia.objects.create(
                escala=self.escala, variante="B", dia_semana=dia_semana, trabalha=True,
                hora_entrada=time(10, 0), hora_saida_almoco=time(13, 0),
                hora_volta_almoco=time(14, 0), hora_saida=time(19, 0),
            )
        EscalaDia.objects.create(  # sábado sem almoço: só 2 batidas
            escala=self.escala, variante="B", dia_semana=5, trabalha=True,
            hora_entrada=time(10, 0), hora_saida=time(14, 0),
        )
        EscalaDia.objects.create(
            escala=self.escala, variante="B", dia_semana=6, trabalha=False,
        )

        self.colab = Colaborador.objects.create(
            nome="TINA MARIA DA COSTA DIAS", cargo="COORDENADORA",
            escala=self.escala, escala_ancora_b=ANCORA_B,
            carga_horaria_diaria=Decimal("8"), registra_ponto=True, ativo=True,
        )
        self.colab.lojas_ponto.set([self.loja_sp, self.loja_anaca])

        self.personagem = PersonagemEscritorio.objects.create(
            colaborador=self.colab, tipo_ator=PersonagemEscritorio.HUMAN_EMPLOYEE,
            personagem="tina", sala_padrao=self.showroom1, pos_x=320, pos_y=180,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def bater(self, dia, hora, minuto=0, tipo="entrada", loja="sp", origem="app"):
        lojas = {"sp": self.loja_sp, "anaca": self.loja_anaca, None: None}
        return BatidaPonto.objects.create(
            colaborador=self.colab, momento=aware(dia, hora, minuto), tipo=tipo,
            loja=lojas[loja], dentro_raio=True, origem=origem,
        )

    def dia_completo(self, dia, loja="sp"):
        """Quatro batidas de um dia normal da variante A."""
        self.bater(dia, 9, 0, "entrada", loja)
        self.bater(dia, 12, 0, "saida_almoco", loja)
        self.bater(dia, 13, 0, "volta_almoco", loja)
        self.bater(dia, 19, 0, "saida", loja)

    def ator(self, dia=None, agora=None):
        cena = projetar_cena(dia=dia, agora=agora)
        self.assertEqual(len(cena.atores), 1)
        return cena.atores[0]


class DiaEncerradoTests(BaseEscritorioTestCase):
    """Dias já fechados (passado). A autoridade é `dia_incompleto()`."""

    def test_dia_normal_com_quatro_batidas(self):
        self.dia_completo(SEGUNDA_A)
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.OFF_SHIFT)
        self.assertEqual(ator.motivo, Motivo.DIA_ENCERRADO)
        self.assertIsNone(ator.inconsistencia)
        self.assertIsNone(ator.sala.sala, "quem já saiu não fica em cena")

    def test_sabado_com_duas_batidas_fecha_o_dia(self):
        self.bater(SABADO_B, 10, 0, "entrada")
        self.bater(SABADO_B, 14, 0, "saida")
        ator = self.ator(dia=SABADO_B)
        self.assertEqual(ator.estado, EstadoPersonagem.OFF_SHIFT)
        self.assertIsNone(ator.inconsistencia)

    def test_domingo_sem_jornada_prevista(self):
        ator = self.ator(dia=DOMINGO)
        self.assertEqual(ator.estado, EstadoPersonagem.DAY_OFF)
        self.assertEqual(ator.motivo, Motivo.FOLGA_ESCALA)

    def test_feriado_sem_batida(self):
        ator = self.ator(dia=FERIADO)
        self.assertEqual(ator.estado, EstadoPersonagem.DAY_OFF)
        self.assertEqual(ator.motivo, Motivo.FERIADO)

    def test_numero_impar_de_batidas_vira_missing_punch(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.MISSING_PUNCH)
        self.assertEqual(ator.inconsistencia, EstadoPersonagem.MISSING_PUNCH)

    def test_sem_retorno_do_almoco(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.MISSING_PUNCH)

    def test_sem_saida_final(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
        self.bater(SEGUNDA_A, 13, 0, "volta_almoco")
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.MISSING_PUNCH)

    def test_ausencia_em_dia_previsto(self):
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.ABSENT)
        self.assertEqual(ator.motivo, Motivo.SEM_REGISTRO)
        self.assertEqual(ator.inconsistencia, EstadoPersonagem.ABSENT)

    def test_abono_do_gestor_encerra_o_dia(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        AbonoPonto.objects.create(
            colaborador=self.colab, data=SEGUNDA_A, saldo_abonado=Decimal("0"),
            motivo="saída autorizada",
        )
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.DAY_OFF)
        self.assertEqual(ator.motivo, Motivo.DIA_RESOLVIDO)
        self.assertIsNone(ator.inconsistencia)

    def test_afastamento_integral(self):
        Afastamento.objects.create(
            colaborador=self.colab, tipo="ferias",
            data_inicio=SEGUNDA_A, data_fim=SEGUNDA_A, dia_inteiro=True,
        )
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.DAY_OFF)
        self.assertEqual(ator.motivo, Motivo.AFASTAMENTO_DIA_INTEIRO)

    def test_folga_lancada_como_afastamento(self):
        Afastamento.objects.create(
            colaborador=self.colab, tipo="folga",
            data_inicio=SEGUNDA_A, data_fim=SEGUNDA_A, dia_inteiro=True,
        )
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.DAY_OFF)

    def test_antes_do_inicio_do_controle_nao_acusa_nada(self):
        dia = date(2026, 6, 15)  # anterior a ParametrosPonto.data_inicio
        ator = self.ator(dia=dia)
        self.assertEqual(ator.motivo, Motivo.ANTES_DO_CONTROLE)
        self.assertIsNone(ator.inconsistencia)

    def test_batida_excluida_muda_a_projecao(self):
        self.dia_completo(SEGUNDA_A)
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.OFF_SHIFT)
        BatidaPonto.objects.filter(colaborador=self.colab, tipo="saida").delete()
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.MISSING_PUNCH)

    def test_batida_alterada_muda_a_projecao(self):
        self.dia_completo(SEGUNDA_A)
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.OFF_SHIFT)
        saida = BatidaPonto.objects.get(colaborador=self.colab, tipo="saida")
        saida.momento = aware(SEGUNDA_A, 18, 0)
        saida.save(update_fields=["momento"])
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.OFF_SHIFT)
        self.assertEqual(timezone.localtime(ator.desde).hour, 18)

    def test_dia_com_almoco_previsto_e_so_duas_batidas_fica_pendente(self):
        # Regra oficial do ponto (dia_incompleto): segunda da variante A espera
        # 4 batidas. Entrada + saída, sem almoço, é dia incompleto.
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.bater(SEGUNDA_A, 19, 0, "saida")
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.MISSING_PUNCH)

    def test_correcao_aprovada_reconcilia_o_dia(self):
        from apps.rh.models import CorrecaoPonto
        from apps.rh.services.correcoes import aplicar_correcao
        from django.contrib.auth import get_user_model

        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.assertEqual(self.ator(dia=SEGUNDA_A).estado, EstadoPersonagem.MISSING_PUNCH)

        gestor = get_user_model().objects.create_user(username="gestor", password="x")
        corr = CorrecaoPonto.objects.create(
            colaborador=self.colab, data=SEGUNDA_A,
            prop_entrada=time(9, 0), prop_saida_almoco=time(12, 0),
            prop_volta_almoco=time(13, 0), prop_saida=time(19, 0),
        )
        aplicar_correcao(corr, gestor)

        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.OFF_SHIFT)
        self.assertIsNone(ator.inconsistencia)


class DiaEmAndamentoTests(BaseEscritorioTestCase):
    """Dia corrente, com o instante controlado."""

    def test_trabalhando_antes_do_almoco(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 10, 30))
        self.assertEqual(ator.estado, EstadoPersonagem.WORKING)
        self.assertEqual(ator.sala.slug, "showroom-1")

    def test_no_almoco_vai_para_o_refeitorio(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 12, 30))
        self.assertEqual(ator.estado, EstadoPersonagem.LUNCH)
        self.assertEqual(ator.sala.slug, svc_salas.SLUG_REFEITORIO)
        self.assertEqual(ator.sala_trabalho.slug, "showroom-1")

    def test_retorno_do_almoco_anima_e_depois_estabiliza(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
            self.bater(SEGUNDA_A, 13, 0, "volta_almoco")
            logo_depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 13, 0, 30))
            bem_depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 15, 0))
        self.assertEqual(logo_depois.estado, EstadoPersonagem.RETURNING_FROM_LUNCH)
        self.assertEqual(logo_depois.estado_estavel, EstadoPersonagem.WORKING)
        self.assertIsNotNone(logo_depois.evento_recente)
        self.assertEqual(logo_depois.evento_recente.event, "LUNCH_END")
        self.assertEqual(bem_depois.estado, EstadoPersonagem.WORKING)
        self.assertIsNone(bem_depois.evento_recente)

    def test_chegada_anima_arriving(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 9, 0, 20))
        self.assertEqual(ator.estado, EstadoPersonagem.ARRIVING)
        self.assertEqual(ator.estado_estavel, EstadoPersonagem.WORKING)
        self.assertEqual(ator.sala.slug, svc_salas.SLUG_ENTRADA)

    def test_saida_anima_leaving_e_depois_sai_de_cena(self):
        with hoje_fixo(SEGUNDA_A):
            self.dia_completo(SEGUNDA_A)
            saindo = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 19, 0, 30))
            depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 19, 10))
        self.assertEqual(saindo.estado, EstadoPersonagem.LEAVING)
        self.assertEqual(saindo.sala.slug, svc_salas.SLUG_ENTRADA)
        self.assertEqual(depois.estado, EstadoPersonagem.OFF_SHIFT)
        self.assertIsNone(depois.sala.sala)

    def test_offline_antes_do_horario_previsto(self):
        with hoje_fixo(SEGUNDA_A):
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 8, 30))
        self.assertEqual(ator.estado, EstadoPersonagem.OFFLINE)
        self.assertEqual(ator.motivo, Motivo.AGUARDANDO_ENTRADA)

    def test_absent_depois_da_tolerancia_sem_bater(self):
        with hoje_fixo(SEGUNDA_A):
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 9, 30))
        self.assertEqual(ator.estado, EstadoPersonagem.ABSENT)

    def test_atraso_com_entrada_posterior_volta_a_trabalhar(self):
        with hoje_fixo(SEGUNDA_A):
            self.assertEqual(
                self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 9, 40)).estado,
                EstadoPersonagem.ABSENT,
            )
            self.bater(SEGUNDA_A, 9, 45, "entrada")
            ator = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 10, 0))
        self.assertEqual(ator.estado, EstadoPersonagem.WORKING)

    def test_afastamento_parcial_vira_away(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            Afastamento.objects.create(
                colaborador=self.colab, tipo="atestado",
                data_inicio=SEGUNDA_A, data_fim=SEGUNDA_A,
                dia_inteiro=False, hora_inicio=time(10, 0), hora_fim=time(11, 30),
            )
            durante = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 10, 30))
            depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 11, 45))
        self.assertEqual(durante.estado, EstadoPersonagem.AWAY)
        self.assertEqual(durante.motivo, Motivo.AFASTAMENTO_PARCIAL)
        self.assertEqual(depois.estado, EstadoPersonagem.WORKING)

    def test_margem_de_fechamento_vira_missing_punch(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            # saída prevista 19:00 + margem 90 min = 20:30
            antes = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 20, 0))
            depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 20, 45))
        self.assertEqual(antes.estado, EstadoPersonagem.WORKING)
        self.assertEqual(depois.estado, EstadoPersonagem.MISSING_PUNCH)

    def test_limite_absoluto_quando_nao_ha_escala(self):
        self.colab.escala = None
        self.colab.save(update_fields=["escala"])
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            antes = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 22, 30))
            depois = self.ator(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 23, 30))
        self.assertEqual(antes.estado, EstadoPersonagem.WORKING)
        self.assertEqual(depois.estado, EstadoPersonagem.MISSING_PUNCH)

    def test_dia_futuro_fica_offline(self):
        futuro = SEGUNDA_A + timedelta(days=7)
        with hoje_fixo(SEGUNDA_A):
            ator = self.ator(dia=futuro, agora=aware(SEGUNDA_A, 10, 0))
        self.assertEqual(ator.estado, EstadoPersonagem.OFFLINE)
        self.assertEqual(ator.motivo, Motivo.DIA_FUTURO)


class EstadoDaLojaTests(BaseEscritorioTestCase):

    def test_loja_fechada_sem_ninguem(self):
        with hoje_fixo(SEGUNDA_A):
            cena = projetar_cena(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 7, 0))
        self.assertEqual(cena.estado_loja, EstadoLoja.CLOSED)
        self.assertFalse(cena.luzes_acesas)

    def test_loja_abrindo_na_primeira_entrada(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            cena = projetar_cena(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 9, 0, 20))
        self.assertEqual(cena.estado_loja, EstadoLoja.OPENING)
        self.assertTrue(cena.luzes_acesas)
        self.assertTrue(cena.porta_aberta)

    def test_loja_aberta_com_alguem_trabalhando(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            cena = projetar_cena(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 10, 0))
        self.assertEqual(cena.estado_loja, EstadoLoja.OPEN)
        self.assertTrue(cena.luzes_acesas)

    def test_todas_no_almoco_nao_fecha_a_loja(self):
        with hoje_fixo(SEGUNDA_A):
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
            cena = projetar_cena(dia=SEGUNDA_A, agora=aware(SEGUNDA_A, 12, 30))
        self.assertEqual(cena.estado_loja, EstadoLoja.OPEN_LUNCH_ONLY)
        self.assertTrue(cena.luzes_acesas, "almoço não apaga as luzes")

    def test_fechada_com_pendencia_apaga_as_luzes(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        cena = projetar_cena(dia=SEGUNDA_A)
        self.assertEqual(cena.estado_loja, EstadoLoja.CLOSED_WITH_PENDING)
        self.assertFalse(cena.luzes_acesas, "loja não fica acesa a madrugada toda")

    def test_fechada_no_fim_do_dia_normal(self):
        self.dia_completo(SEGUNDA_A)
        cena = projetar_cena(dia=SEGUNDA_A)
        self.assertEqual(cena.estado_loja, EstadoLoja.CLOSED)


class ProjecaoSomenteLeituraTests(BaseEscritorioTestCase):

    def test_projetar_nao_escreve_no_banco(self):
        self.dia_completo(SEGUNDA_A)
        antes = {
            "batidas": BatidaPonto.objects.count(),
            "abonos": AbonoPonto.objects.count(),
            "afastamentos": Afastamento.objects.count(),
            "salas": SalaEscritorio.objects.count(),
            "personagens": PersonagemEscritorio.objects.count(),
            "params_ponto": ParametrosPonto.objects.count(),
            "params_escritorio": ParametrosEscritorio.objects.count(),
        }
        for _ in range(3):
            projetar_cena(dia=SEGUNDA_A)
        depois = {
            "batidas": BatidaPonto.objects.count(),
            "abonos": AbonoPonto.objects.count(),
            "afastamentos": Afastamento.objects.count(),
            "salas": SalaEscritorio.objects.count(),
            "personagens": PersonagemEscritorio.objects.count(),
            "params_ponto": ParametrosPonto.objects.count(),
            "params_escritorio": ParametrosEscritorio.objects.count(),
        }
        self.assertEqual(antes, depois)

    def test_sem_parametros_no_banco_usa_defaults_sem_criar_linha(self):
        ParametrosEscritorio.objects.all().delete()
        ParametrosPonto.objects.all().delete()
        projetar_cena(dia=SEGUNDA_A)
        self.assertEqual(ParametrosEscritorio.objects.count(), 0)
        self.assertEqual(ParametrosPonto.objects.count(), 0)

    def test_notificacao_de_ponto_nao_e_criada(self):
        from apps.rh.models import NotificacaoPonto
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        projetar_cena(dia=SEGUNDA_A)
        self.assertEqual(NotificacaoPonto.objects.count(), 0)


class AtorNaoHumanoTests(BaseEscritorioTestCase):

    def test_agente_de_ia_fica_offline_sem_fonte_de_estado(self):
        PersonagemEscritorio.objects.create(
            tipo_ator=PersonagemEscritorio.AI_AGENT, personagem="bot",
            sala_padrao=self.showroom2,
        )
        cena = projetar_cena(dia=SEGUNDA_A)
        bot = next(a for a in cena.atores if a.personagem.personagem == "bot")
        self.assertEqual(bot.estado, EstadoPersonagem.OFFLINE)
        self.assertEqual(bot.motivo, Motivo.ATOR_NAO_HUMANO)

    def test_colaborador_inativo_nao_entra_em_cena(self):
        self.colab.ativo = False
        self.colab.save(update_fields=["ativo"])
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.estado, EstadoPersonagem.OFFLINE)
        self.assertEqual(ator.motivo, Motivo.COLABORADOR_INATIVO)

    def test_nome_exibicao_usa_so_o_primeiro_nome(self):
        ator = self.ator(dia=SEGUNDA_A)
        self.assertEqual(ator.nome_exibicao, "Tina")
