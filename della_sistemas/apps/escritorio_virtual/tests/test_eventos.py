"""Testes dos eventos derivados das batidas."""

from datetime import timedelta

from apps.escritorio_virtual.services.eventos import (
    FONTE,
    Evento,
    eventos_das_batidas,
    evento_da_batida,
    evento_recente,
    primeiro_clock_in,
)
from apps.escritorio_virtual.tests.test_projecao import (
    SEGUNDA_A,
    BaseEscritorioTestCase,
    aware,
)


class EventoDaBatidaTests(BaseEscritorioTestCase):

    def test_event_id_deriva_do_id_da_batida(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        e = evento_da_batida(b)
        self.assertEqual(e.event_id, f"ponto_{b.pk}")
        self.assertEqual(e.employee_id, self.colab.pk)
        self.assertEqual(e.event, "CLOCK_IN")

    def test_nome_da_pessoa_nao_entra_no_evento(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        payload = evento_da_batida(b).como_dict()
        self.assertNotIn("nome", payload)
        self.assertEqual(payload["source"], FONTE)
        self.assertEqual(payload["employeeId"], self.colab.pk)
        # Chave técnica é o id, nunca o nome.
        self.assertNotIn("TINA", str(payload).upper())

    def test_todos_os_quatro_tipos_viram_evento(self):
        self.dia_completo(SEGUNDA_A)
        from apps.rh.models import BatidaPonto
        eventos = eventos_das_batidas(list(BatidaPonto.objects.all()))
        self.assertEqual(
            [e.event for e in eventos],
            ["CLOCK_IN", "LUNCH_START", "LUNCH_END", "CLOCK_OUT"],
        )

    def test_tipo_desconhecido_nao_quebra(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        b.tipo = "tipo_que_ainda_nao_existe"
        self.assertIsNone(evento_da_batida(b))
        self.assertEqual(eventos_das_batidas([b]), [])

    def test_occurred_at_sai_em_iso_no_fuso_local(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        iso = evento_da_batida(b).como_dict()["occurredAt"]
        self.assertTrue(iso.startswith("2026-09-14T09:00:00"))
        self.assertTrue(iso.endswith("-03:00"))


class EventoRecenteTests(BaseEscritorioTestCase):

    def _eventos(self):
        from apps.rh.models import BatidaPonto
        return eventos_das_batidas(list(BatidaPonto.objects.order_by("momento")))

    def test_dentro_da_janela(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        e = evento_recente(self._eventos(), aware(SEGUNDA_A, 9, 1), 120)
        self.assertIsNotNone(e)
        self.assertEqual(e.event, "CLOCK_IN")

    def test_fora_da_janela(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.assertIsNone(evento_recente(self._eventos(), aware(SEGUNDA_A, 9, 5), 120))

    def test_lunch_start_nao_dispara_transicao(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
        self.assertIsNone(
            evento_recente(self._eventos(), aware(SEGUNDA_A, 12, 0, 30), 120),
            "ir para o almoço é a própria animação de LUNCH, não uma transição à parte",
        )

    def test_janela_zerada_desliga_animacao(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.assertIsNone(evento_recente(self._eventos(), aware(SEGUNDA_A, 9, 0, 10), 0))

    def test_evento_no_futuro_nao_conta(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.assertIsNone(evento_recente(self._eventos(), aware(SEGUNDA_A, 8, 59), 120))

    def test_lista_vazia(self):
        self.assertIsNone(evento_recente([], aware(SEGUNDA_A, 9, 0), 120))


class PrimeiroClockInTests(BaseEscritorioTestCase):

    def test_encontra_a_primeira_entrada(self):
        self.dia_completo(SEGUNDA_A)
        from apps.rh.models import BatidaPonto
        eventos = eventos_das_batidas(list(BatidaPonto.objects.all()))
        primeiro = primeiro_clock_in(eventos)
        self.assertEqual(primeiro.event, "CLOCK_IN")
        self.assertEqual(primeiro.occurred_at, aware(SEGUNDA_A, 9, 0))

    def test_sem_entrada_retorna_none(self):
        self.bater(SEGUNDA_A, 12, 0, "saida_almoco")
        from apps.rh.models import BatidaPonto
        eventos = eventos_das_batidas(list(BatidaPonto.objects.all()))
        self.assertIsNone(primeiro_clock_in(eventos))


class EventoIdEstavelTests(BaseEscritorioTestCase):
    """O mesmo eventId entre leituras é o que evita animação repetida."""

    def test_event_id_nao_muda_entre_leituras(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        primeiro = evento_da_batida(b).event_id
        b.refresh_from_db()
        self.assertEqual(evento_da_batida(b).event_id, primeiro)

    def test_batida_recriada_gera_event_id_novo(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        antigo = evento_da_batida(b).event_id
        b.delete()
        nova = self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.assertNotEqual(evento_da_batida(nova).event_id, antigo)


class DataclassEventoTests(BaseEscritorioTestCase):

    def test_evento_e_imutavel(self):
        e = Evento(
            event_id="ponto_1", employee_id=1, event="CLOCK_IN",
            occurred_at=aware(SEGUNDA_A, 9, 0),
        )
        with self.assertRaises(Exception):
            e.event = "CLOCK_OUT"

    def test_ordem_cronologica_independe_da_ordem_de_entrada(self):
        b1 = self.bater(SEGUNDA_A, 19, 0, "saida")
        b2 = self.bater(SEGUNDA_A, 9, 0, "entrada")
        eventos = eventos_das_batidas([b1, b2])
        self.assertEqual([e.event for e in eventos], ["CLOCK_IN", "CLOCK_OUT"])
        self.assertLess(
            eventos[0].occurred_at, eventos[1].occurred_at - timedelta(hours=1),
        )
