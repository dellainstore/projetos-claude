/* Della Instore: /links (bio do Instagram)
 * Versao enxuta e auto-contida do consentimento de cookies (LGPD) e carregamento
 * condicional de GA4, Microsoft Clarity e Meta Pixel. Replica exatamente a logica
 * de della.js (mesmo cookie `della_consent` v1), para que a escolha feita aqui
 * valha em todo o dominio. Nao depende do della.js (a pagina nao o carrega).
 * CSP: este arquivo e servido de 'self' (nada de <script> inline).
 */
document.addEventListener('DOMContentLoaded', function () {
  var gaMeasurementId  = document.body.dataset.gaMeasurementId || '';
  var clarityProjectId = document.body.dataset.clarityProjectId || '';

  function carregarGA() {
    if (!gaMeasurementId || window._gaCarregado) return;
    window._gaCarregado = true;
    var script = document.createElement('script');
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + gaMeasurementId;
    script.async = true;
    document.head.appendChild(script);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', gaMeasurementId);
  }

  function carregarClarity() {
    if (!clarityProjectId || window._clarityCarregado) return;
    window._clarityCarregado = true;
    (function (c, l, a, r, i, t, y) {
      c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
      t = l.createElement(r); t.async = 1; t.src = 'https://www.clarity.ms/tag/' + i;
      y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
    })(window, document, 'clarity', 'script', clarityProjectId);
  }

  function carregarMetaPixel() {
    if (window.fbq) return;
    var pixelId = document.body.dataset.metaPixelId;
    if (!pixelId) return;
    !function (f, b, e, v, n, t, s) {
      if (f.fbq) return; n = f.fbq = function () {
        n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
      };
      if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = '2.0';
      n.queue = []; t = b.createElement(e); t.async = !0;
      t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
    }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', pixelId);
    fbq('track', 'PageView');
  }

  // ─── Cookie Consent (LGPD) ──────────────────────────────────────────────────
  var COOKIE_NAME = 'della_consent';
  var COOKIE_VERSION = 1;
  var VALID_DAYS = 180;

  function lerConsent() {
    var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + COOKIE_NAME + '=([^;]+)'));
    if (!m) return null;
    try {
      var data = JSON.parse(decodeURIComponent(m[1]));
      if (data.v !== COOKIE_VERSION) return null;
      return data;
    } catch (e) { return null; }
  }

  function salvarConsent(prefs) {
    var data = {
      v: COOKIE_VERSION,
      necessary: true,
      analytics: !!prefs.analytics,
      marketing: !!prefs.marketing,
      ts: Math.floor(Date.now() / 1000),
    };
    var expira = new Date(Date.now() + VALID_DAYS * 86400 * 1000);
    var secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = COOKIE_NAME + '=' + encodeURIComponent(JSON.stringify(data))
      + '; path=/; expires=' + expira.toUTCString()
      + '; SameSite=Lax' + secure;
    window.dellaConsent = data;
    document.dispatchEvent(new CustomEvent('della:consent', { detail: data }));
  }

  var banner      = document.getElementById('della-cookie-banner');
  var modal       = document.getElementById('della-cookie-modal');
  var tgAnalytics = document.getElementById('della-cookie-tg-analytics');
  var tgMarketing = document.getElementById('della-cookie-tg-marketing');

  function abrirBanner() { if (banner) banner.style.display = 'block'; }
  function fecharBanner() { if (banner) banner.style.display = 'none'; }
  function abrirModal(prefs) {
    if (!modal) return;
    if (tgAnalytics) tgAnalytics.checked = !!(prefs && prefs.analytics);
    if (tgMarketing) tgMarketing.checked = !!(prefs && prefs.marketing);
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  function fecharModal() {
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }

  var existente = lerConsent();
  if (existente) {
    window.dellaConsent = existente;
    if (existente.analytics) { carregarGA(); carregarClarity(); }
    if (existente.marketing) carregarMetaPixel();
  } else {
    abrirBanner();
  }

  document.addEventListener('della:consent', function (e) {
    if (!e.detail) return;
    if (e.detail.analytics) { carregarGA(); carregarClarity(); }
    if (e.detail.marketing) carregarMetaPixel();
  });

  var btnAceitarTudo = document.getElementById('della-cookie-aceitar-tudo');
  if (btnAceitarTudo) btnAceitarTudo.addEventListener('click', function () {
    salvarConsent({ analytics: true, marketing: true });
    fecharBanner();
  });

  var btnCustomizar = document.getElementById('della-cookie-customizar');
  if (btnCustomizar) btnCustomizar.addEventListener('click', function () {
    abrirModal(lerConsent() || { analytics: false, marketing: false });
  });

  var btnFecharModal = document.getElementById('della-cookie-modal-fechar');
  if (btnFecharModal) btnFecharModal.addEventListener('click', fecharModal);

  var btnNecess = document.getElementById('della-cookie-apenas-necessarios');
  if (btnNecess) btnNecess.addEventListener('click', function () {
    salvarConsent({ analytics: false, marketing: false });
    fecharModal();
    fecharBanner();
  });

  var btnSalvar = document.getElementById('della-cookie-salvar');
  if (btnSalvar) btnSalvar.addEventListener('click', function () {
    salvarConsent({
      analytics: tgAnalytics ? tgAnalytics.checked : false,
      marketing: tgMarketing ? tgMarketing.checked : false,
    });
    fecharModal();
    fecharBanner();
  });

  if (modal) modal.addEventListener('click', function (e) {
    if (e.target === modal) fecharModal();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal && modal.style.display === 'flex') fecharModal();
  });

  var linkPrefs = document.getElementById('della-cookie-preferencias-link');
  if (linkPrefs) linkPrefs.addEventListener('click', function (e) {
    e.preventDefault();
    abrirModal(lerConsent() || { analytics: false, marketing: false });
  });
});
