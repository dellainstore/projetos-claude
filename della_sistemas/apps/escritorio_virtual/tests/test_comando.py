"""Testes do comando de diagnóstico `escritorio_debug`."""

import json
from io import StringIO

from django.core.management import CommandError, call_command

from apps.escritorio_virtual.services.projecao import EstadoPersonagem
from apps.escritorio_virtual.tests.test_projecao import SEGUNDA_A, BaseEscritorioTestCase
from apps.rh.models import BatidaPonto, NotificacaoPonto


class EscritorioDebugTests(BaseEscritorioTestCase):

    def _rodar(self, *args):
        saida = StringIO()
        call_command("escritorio_debug", *args, stdout=saida)
        return saida.getvalue()

    def test_mostra_estado_sala_e_motivo(self):
        self.dia_completo(SEGUNDA_A)
        texto = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("OFF_SHIFT", texto)
        self.assertIn("showroom", texto)
        self.assertIn("dia_encerrado", texto)
        self.assertIn("Tina", texto)

    def test_mostra_batida_mais_recente(self):
        self.dia_completo(SEGUNDA_A)
        texto = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("batida + recente", texto)
        self.assertIn("19:00 CLOCK_OUT", texto)

    def test_diferencia_sala_da_loja_de_sala_fallback(self):
        self.dia_completo(SEGUNDA_A, loja="sp")
        com_loja = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("origem: loja", com_loja)
        self.assertNotIn("é fallback", com_loja)

        BatidaPonto.objects.all().delete()
        self.dia_completo(SEGUNDA_A, loja=None)
        sem_loja = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("origem: sala_padrao", sem_loja)
        self.assertIn("é fallback", sem_loja)

    def test_mostra_inconsistencia(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        texto = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn(EstadoPersonagem.MISSING_PUNCH, texto)
        self.assertIn("inconsistência", texto)

    def test_mostra_veredito_oficial_e_link_da_jornada(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        texto = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("dia_incompleto() = True", texto)
        self.assertIn(f"/rh/ponto/jornada/?colaborador={self.colab.pk}", texto)
        self.assertIn(f"inicio={SEGUNDA_A:%Y-%m-%d}", texto)

    def test_nao_imprime_gps(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        b.latitude, b.longitude, b.distancia_m = -23.5, -46.6, 12.5
        b.save()
        for texto in (
            self._rodar("--data", SEGUNDA_A.isoformat()),
            self._rodar("--data", SEGUNDA_A.isoformat(), "--json"),
        ):
            self.assertNotIn("-23.5", texto)
            self.assertNotIn("-46.6", texto)
            self.assertNotIn("latitude", texto.lower())
            self.assertNotIn("longitude", texto.lower())
            self.assertNotIn("distancia", texto.lower())

    def test_json_valido_com_campos_de_diagnostico(self):
        self.dia_completo(SEGUNDA_A)
        dados = json.loads(self._rodar("--data", SEGUNDA_A.isoformat(), "--json"))
        self.assertEqual(dados["data"], SEGUNDA_A.isoformat())
        self.assertEqual(len(dados["personagens"]), 1)
        p = dados["personagens"][0]
        self.assertEqual(p["estado"], EstadoPersonagem.OFF_SHIFT)
        self.assertEqual(p["sala_origem"], "loja")
        self.assertFalse(p["ponto_oficial_dia_incompleto"])
        self.assertEqual(len(p["eventos"]), 4)

    def test_filtra_por_colaborador(self):
        outro = type(self.colab).objects.create(
            nome="MICHELLE ALVES", registra_ponto=True, ativo=True,
        )
        from apps.escritorio_virtual.models import PersonagemEscritorio
        PersonagemEscritorio.objects.create(
            colaborador=outro, personagem="michelle", sala_padrao=self.showroom2,
        )
        todos = json.loads(self._rodar("--data", SEGUNDA_A.isoformat(), "--json"))
        self.assertEqual(len(todos["personagens"]), 2)

        um = json.loads(self._rodar(
            "--data", SEGUNDA_A.isoformat(), "--colaborador-id", str(self.colab.pk), "--json",
        ))
        self.assertEqual(len(um["personagens"]), 1)
        self.assertEqual(um["personagens"][0]["colaborador_id"], self.colab.pk)

    def test_agora_controla_o_instante(self):
        from apps.escritorio_virtual.tests.test_projecao import hoje_fixo
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        with hoje_fixo(SEGUNDA_A):
            cedo = json.loads(self._rodar(
                "--data", SEGUNDA_A.isoformat(), "--agora", "10:00", "--json",
            ))
            tarde = json.loads(self._rodar(
                "--data", SEGUNDA_A.isoformat(), "--agora", "21:00", "--json",
            ))
        self.assertEqual(cedo["personagens"][0]["estado"], EstadoPersonagem.WORKING)
        self.assertEqual(tarde["personagens"][0]["estado"], EstadoPersonagem.MISSING_PUNCH)

    def test_data_invalida_reclama(self):
        with self.assertRaises(CommandError):
            self._rodar("--data", "18/09/2026")

    def test_comando_nao_escreve_nada(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        antes = (BatidaPonto.objects.count(), NotificacaoPonto.objects.count())
        self._rodar("--data", SEGUNDA_A.isoformat())
        self._rodar("--data", SEGUNDA_A.isoformat(), "--json")
        depois = (BatidaPonto.objects.count(), NotificacaoPonto.objects.count())
        self.assertEqual(antes, depois)
        self.assertEqual(NotificacaoPonto.objects.count(), 0)

    def test_sem_personagem_avisa_em_vez_de_quebrar(self):
        self.personagem.delete()
        texto = self._rodar("--data", SEGUNDA_A.isoformat())
        self.assertIn("Nenhuma personagem ativa configurada", texto)


class EscritorioPersonagemCommandTests(BaseEscritorioTestCase):

    def _rodar(self, *args):
        saida = StringIO()
        call_command("escritorio_personagem", *args, stdout=saida)
        return saida.getvalue()

    def test_lista_elenco(self):
        texto = self._rodar("--listar")
        self.assertIn("tina", texto)
        self.assertIn("showroom", texto)

    def test_lista_colaboradores_com_id(self):
        texto = self._rodar("--colaboradores")
        self.assertIn(f"[{self.colab.pk}]", texto)
        self.assertIn("já tem personagem", texto)

    def test_e_idempotente(self):
        from apps.escritorio_virtual.models import PersonagemEscritorio
        for _ in range(2):
            self._rodar(
                "--colaborador-id", str(self.colab.pk),
                "--personagem", "tina", "--sala", "anaca",
            )
        self.assertEqual(PersonagemEscritorio.objects.count(), 1)
        self.assertEqual(
            PersonagemEscritorio.objects.get().sala_padrao.slug, "anaca",
        )

    def test_sala_inexistente_reclama(self):
        with self.assertRaises(CommandError):
            self._rodar(
                "--colaborador-id", str(self.colab.pk),
                "--personagem", "tina", "--sala", "nao-existe",
            )

    def test_nao_toca_no_ponto(self):
        self.dia_completo(SEGUNDA_A)
        antes = BatidaPonto.objects.count()
        self._rodar("--colaborador-id", str(self.colab.pk), "--personagem", "tina")
        self._rodar("--colaborador-id", str(self.colab.pk), "--desativar")
        self.assertEqual(BatidaPonto.objects.count(), antes)
