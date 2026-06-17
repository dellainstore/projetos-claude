// Substitui handlers inline (`onclick="return confirm(...)"`) e `<script>` IIFE
// que existiam em templates do admin para permitir CSP sem 'unsafe-inline'.
//
// Uso no markup:
//   <a href="..." data-confirm="Excluir este item?">Excluir</a>
//   <form ... data-confirm="Tem certeza?">...</form>
//
// Funcionalidades:
//   1. Persistencia do scroll do menu lateral (#nav-sidebar) entre paginas.
//   2. Modal HTML customizado para data-confirm (substitui window.confirm,
//      que e bloqueado silenciosamente em callbacks async por navegadores modernos).

(function () {
  'use strict';

  // ─── 1. Sidebar scroll persistido ────────────────────────────────────────
  function initSidebarScroll() {
    var KEY = 'admin_sidebar_scroll';
    var nav = document.getElementById('nav-sidebar');
    if (!nav) return;

    var saved = sessionStorage.getItem(KEY);
    if (saved) nav.scrollTop = parseInt(saved, 10) || 0;

    nav.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        sessionStorage.setItem(KEY, nav.scrollTop);
      });
    });

    window.addEventListener('beforeunload', function () {
      sessionStorage.setItem(KEY, nav.scrollTop);
    });
  }

  // ─── 2. Modal HTML customizado para confirmacao ───────────────────────────
  // window.confirm() dentro de callbacks async (fetch.then, setTimeout, etc.)
  // e bloqueado silenciosamente pelo Chrome e outros navegadores modernos.
  // A solucao definitiva e um modal DOM puro, que funciona em qualquer contexto.

  var _modal = null;
  var _pendingHref = null;
  var _pendingForm = null;

  function criarModal() {
    if (_modal) return;

    var overlay = document.createElement('div');
    overlay.id = 'della-confirm-overlay';
    overlay.style.cssText = [
      'display:none',
      'position:fixed',
      'inset:0',
      'z-index:99999',
      'background:rgba(0,0,0,0.55)',
      'align-items:center',
      'justify-content:center',
    ].join(';');

    var box = document.createElement('div');
    box.id = 'della-confirm-box';
    box.style.cssText = [
      'background:#fff',
      'border-radius:10px',
      'padding:28px 32px 22px',
      'max-width:380px',
      'width:90%',
      'box-shadow:0 8px 32px rgba(0,0,0,0.22)',
      'font-family:Jost,sans-serif',
      'text-align:center',
    ].join(';');

    var icone = document.createElement('div');
    icone.textContent = '!';
    icone.style.cssText = [
      'width:44px',
      'height:44px',
      'border-radius:50%',
      'background:#fef3e2',
      'color:#c87a00',
      'font-size:22px',
      'font-weight:700',
      'line-height:44px',
      'margin:0 auto 14px',
    ].join(';');

    var msg = document.createElement('p');
    msg.id = 'della-confirm-msg';
    msg.style.cssText = [
      'font-size:15px',
      'color:#1a1a1a',
      'margin:0 0 22px',
      'line-height:1.5',
    ].join(';');

    var acoes = document.createElement('div');
    acoes.style.cssText = 'display:flex;gap:10px;justify-content:center;';

    var btnOk = document.createElement('button');
    btnOk.id = 'della-confirm-ok';
    btnOk.type = 'button';
    btnOk.textContent = 'Excluir';
    btnOk.style.cssText = [
      'background:#c0392b',
      'color:#fff',
      'border:none',
      'border-radius:6px',
      'padding:9px 24px',
      'font-size:13px',
      'font-weight:600',
      'cursor:pointer',
      'font-family:Jost,sans-serif',
      'letter-spacing:0.03em',
    ].join(';');

    var btnCancel = document.createElement('button');
    btnCancel.id = 'della-confirm-cancel';
    btnCancel.type = 'button';
    btnCancel.textContent = 'Cancelar';
    btnCancel.style.cssText = [
      'background:#f0f0ee',
      'color:#1a1a1a',
      'border:none',
      'border-radius:6px',
      'padding:9px 22px',
      'font-size:13px',
      'font-weight:500',
      'cursor:pointer',
      'font-family:Jost,sans-serif',
    ].join(';');

    acoes.appendChild(btnOk);
    acoes.appendChild(btnCancel);
    box.appendChild(icone);
    box.appendChild(msg);
    box.appendChild(acoes);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    _modal = overlay;

    btnOk.addEventListener('click', function () {
      var href = _pendingHref;
      var form = _pendingForm;
      fecharModal();
      if (href) {
        window.location.href = href;
      } else if (form) {
        form.submit();
      }
    });

    btnCancel.addEventListener('click', fecharModal);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) fecharModal();
    });

    document.addEventListener('keydown', function (e) {
      if (_modal && _modal.style.display !== 'none') {
        if (e.key === 'Escape') fecharModal();
        if (e.key === 'Enter') btnOk.click();
      }
    });
  }

  function abrirModal(mensagem, href, form) {
    criarModal();
    document.getElementById('della-confirm-msg').textContent = mensagem;
    _pendingHref = href || null;
    _pendingForm = form || null;
    _modal.style.display = 'flex';
    document.getElementById('della-confirm-cancel').focus();
  }

  function fecharModal() {
    if (_modal) _modal.style.display = 'none';
    _pendingHref = null;
    _pendingForm = null;
  }

  // ─── 3. Delegation de cliques e submits com data-confirm ─────────────────
  function initConfirmDelegation() {
    document.addEventListener('click', function (e) {
      var el = e.target.closest('[data-confirm]');
      if (!el || el.tagName === 'FORM') return;

      var msg = el.getAttribute('data-confirm');
      if (!msg) return;

      e.preventDefault();
      e.stopPropagation();

      abrirModal(msg, el.href || null, null);
    }, true);

    document.addEventListener('submit', function (e) {
      var form = e.target.closest('form[data-confirm]');
      if (!form) return;
      var msg = form.getAttribute('data-confirm');
      if (!msg) return;
      e.preventDefault();
      e.stopPropagation();
      abrirModal(msg, null, form);
    }, true);
  }

  function init() {
    initSidebarScroll();
    initConfirmDelegation();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
