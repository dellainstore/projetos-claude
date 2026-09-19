"""Testes da API interna: autenticação, permissão, contrato, ETag e 304."""

import json

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.urls import reverse

from apps.escritorio_virtual.services.projecao import EstadoPersonagem
from apps.escritorio_virtual.services.serializacao import (
    VERSAO_CONTRATO,
    etag_corresponde,
)
from apps.escritorio_virtual.tests.test_projecao import (
    SEGUNDA_A,
    BaseEscritorioTestCase,
    instante_fixo,
)
from apps.rh.models import BatidaPonto, NotificacaoPonto

User = get_user_model()


@override_settings(
    # A feature nasce desligada em produção (ver config/settings.py); os testes
    # ligam explicitamente.
    ESCRITORIO_ATIVO=True,
    # Em produção o painel força HTTPS (SECURE_SSL_REDIRECT). O test client
    # fala HTTP, o que viraria 301 antes de chegar na view.
    SECURE_SSL_REDIRECT=False,
    # Hash rápido: estes testes criam vários usuários e o PBKDF2 real domina
    # o tempo de execução sem testar nada.
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class BaseApiTestCase(BaseEscritorioTestCase):

    def setUp(self):
        super().setUp()
        self.url = reverse("escritorio:api_estado")
        self.autorizado = User.objects.create_user(
            username="espectador", password="segredo-de-teste",
            permissoes={"escritorio": {"ver": True}},
        )
        self.sem_permissao = User.objects.create_user(
            username="outro", password="segredo-de-teste",
            permissoes={"rh": {"ponto_bater": True}},
        )

    def get(self, user=None, **extra):
        if user is not None:
            self.client.force_login(user)
        return self.client.get(self.url, **extra)


class AcessoTests(BaseApiTestCase):

    def test_anonimo_recebe_401_em_json(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["erro"], "nao_autenticado")

    def test_autenticado_sem_permissao_recebe_403(self):
        r = self.get(self.sem_permissao)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["erro"], "sem_permissao")

    def test_autorizado_recebe_200(self):
        r = self.get(self.autorizado)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["versao"], VERSAO_CONTRATO)

    def test_metodos_de_escrita_sao_recusados(self):
        self.client.force_login(self.autorizado)
        for metodo in ("post", "put", "patch", "delete"):
            with self.subTest(metodo=metodo):
                r = getattr(self.client, metodo)(self.url)
                self.assertEqual(r.status_code, 405)

    def test_interruptor_desliga_a_rota(self):
        with override_settings(ESCRITORIO_ATIVO=False):
            self.assertEqual(self.get(self.autorizado).status_code, 404)

    def test_permissao_nova_nao_libera_usuario_existente(self):
        """Quem já tem `permissoes` preenchido não ganha acesso só porque o
        módulo passou a existir na árvore."""
        usuario_legado = User.objects.create_user(
            username="legado", password="x",
            permissoes={"rh": {"ponto_bater": True}, "tarefas": {"ver": True}},
        )
        self.assertFalse(usuario_legado.tem_perm("escritorio.ver"))
        self.assertFalse(usuario_legado.tem_perm("escritorio.configurar"))

    def test_papeis_nao_ganham_escritorio_por_fallback(self):
        from apps.core.permissions import DEFAULT_PERMS_BY_PAPEL
        for papel, perms in DEFAULT_PERMS_BY_PAPEL.items():
            with self.subTest(papel=papel):
                self.assertFalse(perms["escritorio"]["ver"])
                self.assertFalse(perms["escritorio"]["configurar"])

    def test_pagina_diagnostica_exige_permissao(self):
        url = reverse("escritorio:diagnostico")
        self.assertEqual(self.client.get(url).status_code, 302)  # manda pro login
        self.client.force_login(self.sem_permissao)
        self.assertEqual(self.client.get(url).status_code, 302)  # manda pra home
        self.client.force_login(self.autorizado)
        self.assertEqual(self.client.get(url).status_code, 200)


class ContratoDoPayloadTests(BaseApiTestCase):

    def test_estrutura_minima(self):
        dados = self.get(self.autorizado).json()
        self.assertEqual(
            set(dados),
            {"preview", "versao", "data", "geradoEm", "pollSegundos", "loja",
             "salas", "personagens", "avisos"},
        )
        self.assertEqual(
            set(dados["loja"]),
            {"estado", "luzesAcesas", "portaAberta", "pendencias"},
        )

    def test_campos_do_personagem_sao_lista_fechada(self):
        dados = self.get(self.autorizado).json()
        self.assertEqual(
            set(dados["personagens"][0]),
            {"id", "personagem", "nome", "tipoAtor", "estado", "estadoEstavel",
             "desde", "sala", "salaTrabalho", "salaOrigem", "posX", "posY",
             "evento", "inconsistencia"},
        )

    def test_datas_em_iso_8601_com_fuso(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.client.force_login(self.autorizado)
        with instante_fixo(SEGUNDA_A, 10, 30):
            dados = self.client.get(self.url).json()
        self.assertRegex(dados["data"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(dados["geradoEm"].endswith("-03:00"))

    def test_nao_expoe_gps(self):
        b = self.bater(SEGUNDA_A, 9, 0, "entrada")
        b.latitude, b.longitude, b.distancia_m = -23.512345, -46.612345, 42.5
        b.save()
        bruto = self.get(self.autorizado).content.decode()
        for proibido in ("latitude", "longitude", "distancia", "dentro_raio",
                         "-23.51", "-46.61", "42.5"):
            self.assertNotIn(proibido, bruto)

    def test_nao_expoe_dado_trabalhista_nem_afastamento(self):
        from datetime import time
        from apps.rh.models import Afastamento
        Afastamento.objects.create(
            colaborador=self.colab, tipo="atestado",
            data_inicio=SEGUNDA_A, data_fim=SEGUNDA_A,
            dia_inteiro=False, hora_inicio=time(9, 0), hora_fim=time(11, 0),
            observacao="consulta médica",
        )
        bruto = self.get(self.autorizado).content.decode().lower()
        for proibido in ("atestado", "ferias", "férias", "falta", "afastamento",
                         "saldo", "banco de horas", "motivo", "consulta"):
            self.assertNotIn(proibido, bruto)

    def test_expoe_so_o_primeiro_nome(self):
        dados = self.get(self.autorizado).json()
        self.assertEqual(dados["personagens"][0]["nome"], "Tina")
        self.assertNotIn("MARIA DA COSTA", self.get(self.autorizado).content.decode())

    def test_desde_so_aparece_em_estado_de_presenca(self):
        self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.client.force_login(self.autorizado)
        with instante_fixo(SEGUNDA_A, 10, 30):
            trabalhando = self.client.get(self.url).json()["personagens"][0]
        self.assertEqual(trabalhando["estado"], EstadoPersonagem.WORKING)
        self.assertIsNotNone(trabalhando["desde"])

        # O instante também é fixado aqui: sem isso o teste passaria ou
        # falharia conforme o dia da semana em que rodasse (num sábado a
        # colaboradora está de folga, e folga não é ausência).
        BatidaPonto.objects.all().delete()
        with instante_fixo(SEGUNDA_A, 21, 0):
            ausente = self.client.get(self.url).json()["personagens"][0]
        self.assertEqual(ausente["estado"], EstadoPersonagem.ABSENT)
        self.assertIsNone(ausente["desde"], "ausência não precisa carimbar horário")

    def test_evento_recente_traz_o_event_id(self):
        batida = self.bater(SEGUNDA_A, 9, 0, "entrada")
        self.client.force_login(self.autorizado)
        with instante_fixo(SEGUNDA_A, 9, 1):
            personagem = self.client.get(self.url).json()["personagens"][0]
        self.assertEqual(personagem["estado"], EstadoPersonagem.ARRIVING)
        self.assertEqual(personagem["evento"]["eventId"], f"ponto_{batida.pk}")
        self.assertEqual(personagem["evento"]["event"], "CLOCK_IN")

    def test_salas_vem_com_layout(self):
        dados = self.get(self.autorizado).json()
        slugs = {s["slug"] for s in dados["salas"]}
        self.assertIn("showroom", slugs)
        self.assertIn("cafeteria", slugs)
        self.assertEqual(
            set(dados["salas"][0]),
            {"slug", "nome", "ordem", "pos_x", "pos_y", "largura", "altura"},
        )


class EtagTests(BaseApiTestCase):

    def test_etag_presente_e_estavel(self):
        r1 = self.get(self.autorizado)
        r2 = self.client.get(self.url)
        self.assertTrue(r1["ETag"])
        self.assertEqual(r1["ETag"], r2["ETag"], "mesma cena, mesmo ETag")

    def test_if_none_match_devolve_304_sem_corpo(self):
        r1 = self.get(self.autorizado)
        r2 = self.client.get(self.url, HTTP_IF_NONE_MATCH=r1["ETag"])
        self.assertEqual(r2.status_code, 304)
        self.assertEqual(r2.content, b"")
        self.assertEqual(r2["ETag"], r1["ETag"])

    def test_etag_muda_quando_a_cena_muda(self):
        self.client.force_login(self.autorizado)
        with instante_fixo(SEGUNDA_A, 10, 30):
            antes = self.client.get(self.url)["ETag"]
            self.bater(SEGUNDA_A, 9, 0, "entrada")
            depois = self.client.get(self.url)["ETag"]
        self.assertNotEqual(antes, depois)

    def test_etag_ignora_apenas_o_campo_volatil(self):
        """`geradoEm` muda a cada requisição; se entrasse no ETag, nunca
        haveria 304."""
        from apps.escritorio_virtual.services.serializacao import calcular_etag
        base = {"versao": 1, "geradoEm": "2026-09-19T09:00:00-03:00", "loja": {"estado": "OPEN"}}
        outro = dict(base, geradoEm="2026-09-19T09:10:00-03:00")
        self.assertEqual(calcular_etag(base), calcular_etag(outro))
        mudou = dict(base, loja={"estado": "CLOSED"})
        self.assertNotEqual(calcular_etag(base), calcular_etag(mudou))

    def test_etag_aceita_prefixo_fraco_e_lista(self):
        etag = '"abc123"'
        self.assertTrue(etag_corresponde('W/"abc123"', etag))
        self.assertTrue(etag_corresponde('"outro", "abc123"', etag))
        self.assertTrue(etag_corresponde("*", etag))
        self.assertFalse(etag_corresponde('"outro"', etag))
        self.assertFalse(etag_corresponde(None, etag))
        self.assertFalse(etag_corresponde("", etag))

    def test_cabecalhos_de_cache_privados(self):
        r = self.get(self.autorizado)
        self.assertEqual(r["Cache-Control"], "private, no-cache")
        self.assertEqual(r["Vary"], "Cookie")


class ApiNaoEscreveTests(BaseApiTestCase):

    def test_get_repetido_nao_altera_nada(self):
        self.dia_completo(SEGUNDA_A)
        from apps.escritorio_virtual.models import ParametrosEscritorio
        from apps.rh.models import AbonoPonto, ParametrosPonto
        antes = (
            BatidaPonto.objects.count(),
            NotificacaoPonto.objects.count(),
            AbonoPonto.objects.count(),
            ParametrosPonto.objects.count(),
            ParametrosEscritorio.objects.count(),
        )
        self.client.force_login(self.autorizado)
        for _ in range(5):
            self.client.get(self.url)
        depois = (
            BatidaPonto.objects.count(),
            NotificacaoPonto.objects.count(),
            AbonoPonto.objects.count(),
            ParametrosPonto.objects.count(),
            ParametrosEscritorio.objects.count(),
        )
        self.assertEqual(antes, depois)

    def test_batida_nao_e_criada_nem_apagada(self):
        self.dia_completo(SEGUNDA_A)
        ids_antes = set(BatidaPonto.objects.values_list("pk", flat=True))
        momentos_antes = list(BatidaPonto.objects.order_by("pk").values_list("momento", flat=True))
        self.client.force_login(self.autorizado)
        self.client.get(self.url)
        self.assertEqual(set(BatidaPonto.objects.values_list("pk", flat=True)), ids_antes)
        self.assertEqual(
            list(BatidaPonto.objects.order_by("pk").values_list("momento", flat=True)),
            momentos_antes,
        )

    def test_payload_e_json_serializavel_de_ponta_a_ponta(self):
        r = self.get(self.autorizado)
        self.assertEqual(r["Content-Type"], "application/json")
        json.loads(r.content)


class PaginaDiagnosticaTests(BaseApiTestCase):
    """A página só entrega o container e o bundle; todo o dado vem da API."""

    def test_container_traz_a_configuracao_do_poller(self):
        self.client.force_login(self.autorizado)
        html = self.client.get(reverse("escritorio:diagnostico")).content.decode()
        self.assertIn('id="escritorio-diagnostico"', html)
        self.assertIn('data-api-url="/escritorio/api/estado/"', html)
        self.assertIn('data-poll-segundos="10"', html)
        self.assertIn("escritorio/escritorio.js", html)
        self.assertIn('data-ev="palco"', html, "o canvas do Phaser precisa de um destino")

    def test_pagina_nao_traz_dado_de_ponto_no_html(self):
        """Nada de estado renderizado no servidor: a tabela nasce vazia e é
        preenchida pelo JS a partir da API. Se o bundle não carregar, a página
        não mostra dado nenhum em vez de vazar estado."""
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)
        html = self.client.get(reverse("escritorio:diagnostico")).content.decode()

        corpo = html.split('<tbody data-ev="corpo">')[1].split("</tbody>")[0]
        self.assertIn("carregando", corpo)
        self.assertNotIn("Tina", corpo)
        self.assertNotIn("showroom", corpo)
        # O nome civil completo não aparece em lugar nenhum da página.
        self.assertNotIn("MARIA DA COSTA", html.upper())

    def test_usa_placeholder_quando_a_arte_oficial_nao_existe(self):
        self.client.force_login(self.autorizado)
        html = self.client.get(reverse("escritorio:diagnostico")).content.decode()
        self.assertIn("office-bg-placeholder.svg", html)
        self.assertNotIn('data-bg-url="/static/escritorio/office-bg.png', html)

    def test_usa_a_arte_oficial_quando_o_arquivo_existe(self):
        import pathlib as _pathlib
        from django.conf import settings as _settings
        caminho = _pathlib.Path(_settings.BASE_DIR) / "static" / "escritorio" / "office-bg.png"
        caminho.write_bytes(b"PNG-fake-so-para-o-teste")
        self.addCleanup(caminho.unlink)
        self.client.force_login(self.autorizado)
        html = self.client.get(reverse("escritorio:diagnostico")).content.decode()
        self.assertIn("office-bg.png", html)
        self.assertNotIn("office-bg-placeholder.svg", html)

    def test_interruptor_desliga_a_pagina(self):
        self.client.force_login(self.autorizado)
        with override_settings(ESCRITORIO_ATIVO=False):
            r = self.client.get(reverse("escritorio:diagnostico"))
        self.assertEqual(r.status_code, 404)


class PreviewTests(BaseApiTestCase):
    """Pré-visualização de um instante passado, com as batidas REAIS do dia.

    Existe porque fora do expediente a cena fica vazia, e inventar batida de
    teste no banco corromperia o ponto (entraria no banco de horas, geraria
    pendência e apareceria no espelho de ponto da colaboradora)."""

    def test_sem_parametro_fica_ao_vivo(self):
        dados = self.get(self.autorizado).json()
        self.assertFalse(dados["preview"]["ativo"])

    def test_sugere_um_dia_com_expediente_completo(self):
        self.dia_completo(SEGUNDA_A)
        dados = self.get(self.autorizado).json()
        self.assertEqual(dados["preview"]["diaSugerido"], SEGUNDA_A.isoformat())

    def test_prefere_o_dia_com_almoco_ao_dia_mais_recente(self):
        """Sugerir só "o último dia com batida" engana: num dia em que
        ninguém bateu almoço a cena fica igual das 9h às 19h e a
        pré-visualização parece quebrada. Foi o que aconteceu de verdade em
        18/09/2026, onde só uma das três bateu almoço."""
        from datetime import timedelta
        completo = SEGUNDA_A
        self.dia_completo(completo)

        # Dia seguinte, mais recente, mas só com entrada e saída.
        magro = completo + timedelta(days=1)
        self.bater(magro, 9, 0, "entrada")
        self.bater(magro, 19, 0, "saida")

        dados = self.get(self.autorizado).json()
        self.assertEqual(
            dados["preview"]["diaSugerido"], completo.isoformat(),
            "deveria sugerir o dia em que dá para ver movimento",
        )

    def test_sem_batida_nenhuma_nao_sugere_data(self):
        dados = self.get(self.autorizado).json()
        self.assertIsNone(dados["preview"]["diaSugerido"])

    def test_sem_personagem_cadastrada_nao_sugere_data(self):
        self.dia_completo(SEGUNDA_A)
        self.personagem.delete()
        dados = self.get(self.autorizado).json()
        self.assertIsNone(dados["preview"]["diaSugerido"])

    def test_data_e_hora_projetam_o_instante_escolhido(self):
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)

        manha = self.client.get(
            self.url, {"data": SEGUNDA_A.isoformat(), "hora": "10:30"},
        ).json()
        self.assertTrue(manha["preview"]["ativo"])
        self.assertEqual(manha["preview"]["data"], SEGUNDA_A.isoformat())
        self.assertEqual(manha["preview"]["hora"], "10:30")
        self.assertEqual(manha["personagens"][0]["estado"], EstadoPersonagem.WORKING)
        self.assertEqual(manha["loja"]["estado"], "OPEN")

        almoco = self.client.get(
            self.url, {"data": SEGUNDA_A.isoformat(), "hora": "12:30"},
        ).json()
        self.assertEqual(almoco["personagens"][0]["estado"], EstadoPersonagem.LUNCH)
        self.assertEqual(almoco["personagens"][0]["sala"], "cafeteria")

        noite = self.client.get(
            self.url, {"data": SEGUNDA_A.isoformat(), "hora": "21:00"},
        ).json()
        self.assertEqual(noite["personagens"][0]["estado"], EstadoPersonagem.OFF_SHIFT)
        self.assertEqual(noite["loja"]["estado"], "CLOSED")

    def test_so_a_data_projeta_o_fim_daquele_dia(self):
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)
        dados = self.client.get(self.url, {"data": SEGUNDA_A.isoformat()}).json()
        self.assertTrue(dados["preview"]["ativo"])
        self.assertIsNone(dados["preview"]["hora"])
        self.assertEqual(dados["personagens"][0]["estado"], EstadoPersonagem.OFF_SHIFT)

    def test_horas_diferentes_tem_etag_diferente(self):
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)
        manha = self.client.get(self.url, {"data": SEGUNDA_A.isoformat(), "hora": "10:00"})
        tarde = self.client.get(self.url, {"data": SEGUNDA_A.isoformat(), "hora": "15:00"})
        self.assertNotEqual(manha["ETag"], tarde["ETag"])

    def test_mesmo_instante_devolve_304(self):
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)
        params = {"data": SEGUNDA_A.isoformat(), "hora": "10:00"}
        primeira = self.client.get(self.url, params)
        segunda = self.client.get(self.url, params, HTTP_IF_NONE_MATCH=primeira["ETag"])
        self.assertEqual(segunda.status_code, 304)

    def test_data_no_futuro_e_recusada(self):
        from datetime import timedelta
        self.client.force_login(self.autorizado)
        amanha = (timezone.localdate() + timedelta(days=1)).isoformat()
        r = self.client.get(self.url, {"data": amanha})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["erro"], "parametro_invalido")

    def test_data_malformada_e_recusada(self):
        self.client.force_login(self.autorizado)
        r = self.client.get(self.url, {"data": "14/09/2026"})
        self.assertEqual(r.status_code, 400)

    def test_hora_malformada_e_recusada(self):
        self.client.force_login(self.autorizado)
        r = self.client.get(self.url, {"data": SEGUNDA_A.isoformat(), "hora": "meio-dia"})
        self.assertEqual(r.status_code, 400)

    def test_preview_exige_a_mesma_permissao(self):
        params = {"data": SEGUNDA_A.isoformat(), "hora": "10:00"}
        self.assertEqual(self.client.get(self.url, params).status_code, 401)
        self.client.force_login(self.sem_permissao)
        self.assertEqual(self.client.get(self.url, params).status_code, 403)

    def test_preview_nao_escreve_nada(self):
        self.dia_completo(SEGUNDA_A)
        antes = BatidaPonto.objects.count()
        ids_antes = set(BatidaPonto.objects.values_list("pk", flat=True))
        self.client.force_login(self.autorizado)
        for hora in ("08:00", "10:00", "12:30", "15:00", "19:30"):
            self.client.get(self.url, {"data": SEGUNDA_A.isoformat(), "hora": hora})
        self.assertEqual(BatidaPonto.objects.count(), antes)
        self.assertEqual(set(BatidaPonto.objects.values_list("pk", flat=True)), ids_antes)
        self.assertEqual(NotificacaoPonto.objects.count(), 0)

    def test_preview_nao_expoe_mais_do_que_o_ao_vivo(self):
        self.dia_completo(SEGUNDA_A)
        self.client.force_login(self.autorizado)
        bruto = self.client.get(
            self.url, {"data": SEGUNDA_A.isoformat(), "hora": "10:00"},
        ).content.decode()
        for proibido in ("latitude", "longitude", "distancia", "motivo", "MARIA DA COSTA"):
            self.assertNotIn(proibido, bruto)
