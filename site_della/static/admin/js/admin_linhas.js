/**
 * admin_linhas.js — Torna as linhas da listagem do admin clicáveis.
 * Ao clicar em qualquer parte da linha (exceto links/botões/checkboxes),
 * navega para a página de edição do objeto.
 */
(function () {
  'use strict';

  function init() {
    var linhas = document.querySelectorAll('#result_list tbody tr');

    linhas.forEach(function (tr) {
      // Pega o primeiro link de edição da linha (gerado pelo Django em list_display_links)
      var linkEdicao = tr.querySelector('a[href]');
      if (!linkEdicao) return;
      var href = linkEdicao.getAttribute('href');

      tr.style.cursor = 'pointer';

      tr.addEventListener('click', function (e) {
        // Ignora cliques em links, botões, inputs e selects já presentes na linha
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

      // Destaque visual ao passar o mouse
      tr.addEventListener('mouseenter', function () {
        tr.style.background = 'rgba(201,169,110,0.08)';
      });
      tr.addEventListener('mouseleave', function () {
        tr.style.background = '';
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
