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
    initInlineDeleteButtons();
  }

  function initInlineDeleteButtons() {
    // Renderiza o botão × em células ainda sem ele
    document.querySelectorAll('.tabular.inline-related tbody td.delete').forEach(function (cell) {
      if (cell.querySelector('.della-inline-remove')) return;
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'della-inline-remove';
      button.setAttribute('aria-label', 'Remover linha');
      button.textContent = '×';
      cell.appendChild(button);
    });

    if (window.__dellaInlineDeleteObserverStarted) return;
    window.__dellaInlineDeleteObserverStarted = true;

    // Observer só para criar botões em linhas novas — o clique é tratado por delegação
    var observer = new MutationObserver(function () {
      initInlineDeleteButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // Delegação de evento: um único listener no document captura cliques em qualquer botão ×,
    // independentemente de quando ele foi criado
    document.addEventListener('click', function (e) {
      if (!e.target.matches('.della-inline-remove')) return;
      var cell = e.target.closest('td.delete');
      if (!cell) return;
      var row = e.target.closest('tr');
      if (!row) return;
      var checkbox = cell.querySelector('input[type="checkbox"]');
      if (checkbox) {
        checkbox.checked = true;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      }
      var deleteLink = cell.querySelector('.inline-deletelink');
      if (deleteLink) {
        row.classList.add('della-inline-marked-delete');
        deleteLink.click();
        return;
      }
      row.classList.add('della-inline-marked-delete');
      row.style.display = 'none';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
