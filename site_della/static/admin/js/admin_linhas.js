/**
 * admin_linhas.js
 * - Torna as linhas da listagem clicáveis (navega para edição ao clicar na linha)
 * - Persiste scroll do menu lateral (nav-sidebar) entre navegações
 */
(function () {
  'use strict';

  // ── Linhas clicáveis ─────────────────────────────────────────────────────
  function initLinhas() {
    var linhas = document.querySelectorAll('#result_list tbody tr');

    linhas.forEach(function (tr) {
      var linkEdicao = tr.querySelector('a[href]');
      if (!linkEdicao) return;
      var href = linkEdicao.getAttribute('href');

      tr.style.cursor = 'pointer';

      tr.addEventListener('click', function (e) {
        var alvo = e.target;
        if (
          alvo.closest('a') ||
          alvo.closest('button') ||
          alvo.tagName === 'INPUT' ||
          alvo.tagName === 'SELECT' ||
          alvo.tagName === 'LABEL'
        ) {
          return;
        }
        window.location.href = href;
      });

      tr.addEventListener('mouseenter', function () {
        tr.style.background = 'rgba(201,169,110,0.08)';
      });
      tr.addEventListener('mouseleave', function () {
        tr.style.background = '';
      });
    });
  }

  // ── Persistência de scroll do menu lateral ───────────────────────────────
  var STORAGE_KEY = 'admin_sidebar_scroll';

  function initSidebarScroll() {
    // Tenta encontrar o container de scroll da sidebar do Django admin
    var sidebar = document.querySelector('#nav-sidebar') ||
                  document.querySelector('.sticky') ||
                  document.querySelector('#content-related') ||
                  document.querySelector('.module') && document.querySelector('#nav-sidebar');

    // Django admin 3.2+ tem #nav-sidebar
    var nav = document.getElementById('nav-sidebar');
    if (!nav) return;

    // Restaura posição salva
    var saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      nav.scrollTop = parseInt(saved, 10);
    }

    // Salva posição antes de sair da página
    window.addEventListener('beforeunload', function () {
      sessionStorage.setItem(STORAGE_KEY, nav.scrollTop);
    });

    // Também salva ao clicar em qualquer link dentro da sidebar
    nav.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        sessionStorage.setItem(STORAGE_KEY, nav.scrollTop);
      });
    });
  }

  function init() {
    initLinhas();
    initSidebarScroll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
