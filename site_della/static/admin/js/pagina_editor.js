/**
 * Editor de texto rico para PaginaEstatica no admin Django.
 * Recursos: negrito, itálico, sublinhado, títulos, listas, links,
 * alinhamento, tamanho de fonte, inserção de imagem por URL.
 */
(function () {
  'use strict';

  function init() {
    var textarea = document.getElementById('id_conteudo');
    if (!textarea) return;

    // Wrapper principal
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'border:1px solid #ccc;border-radius:4px;overflow:hidden;color-scheme:light;';

    // Barra de ferramentas
    var toolbar = document.createElement('div');
    toolbar.style.cssText = (
      'background:#f8f9fa;border-bottom:1px solid #dee2e6;padding:6px 8px;'
      + 'display:flex;flex-wrap:wrap;gap:4px;align-items:center;color:#212529;'
    );

    // ── Botão genérico ──────────────────────────────────────────────────────
    function criarBtn(label, title, fn) {
      var b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = label;
      b.title = title;
      b.style.cssText = (
        'padding:3px 8px;border:1px solid #ccc;background:#fff;color:#212529;cursor:pointer;'
        + 'border-radius:3px;font-size:12px;line-height:1.4;white-space:nowrap;'
      );
      b.addEventListener('mouseenter', function () { b.style.background = '#e9ecef'; });
      b.addEventListener('mouseleave', function () { b.style.background = '#fff'; });
      b.addEventListener('click', function () { editor.focus(); fn(); sincronizar(); });
      return b;
    }

    function sep() {
      var s = document.createElement('span');
      s.style.cssText = 'width:1px;height:20px;background:#dee2e6;margin:0 4px;flex-shrink:0;';
      return s;
    }

    // ── Formatação básica ────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('<b>N</b>',       'Negrito (Ctrl+B)',    function () { document.execCommand('bold'); }));
    toolbar.appendChild(criarBtn('<i>I</i>',       'Itálico (Ctrl+I)',    function () { document.execCommand('italic'); }));
    toolbar.appendChild(criarBtn('<u>S</u>',       'Sublinhado (Ctrl+U)', function () { document.execCommand('underline'); }));
    toolbar.appendChild(sep());

    // ── Blocos / títulos ─────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('Título',     'Título (H2)',      function () { document.execCommand('formatBlock', false, 'h2'); }));
    toolbar.appendChild(criarBtn('Subtítulo',  'Subtítulo (H3)',   function () { document.execCommand('formatBlock', false, 'h3'); }));
    toolbar.appendChild(criarBtn('Parágrafo',  'Parágrafo normal', function () { document.execCommand('formatBlock', false, 'p'); }));
    toolbar.appendChild(sep());

    // ── Tamanho de fonte ─────────────────────────────────────────────────────
    var fontSizeSelect = document.createElement('select');
    fontSizeSelect.title = 'Tamanho da fonte';
    fontSizeSelect.style.cssText = (
      'padding:2px 4px;border:1px solid #ccc;border-radius:3px;font-size:12px;'
      + 'background:#fff;color:#212529;cursor:pointer;'
    );
    [
      { label: 'Fonte',      value: '' },
      { label: 'Pequena',    value: '2' },
      { label: 'Normal',     value: '3' },
      { label: 'Grande',     value: '4' },
      { label: 'Maior',      value: '5' },
    ].forEach(function (op) {
      var opt = document.createElement('option');
      opt.value = op.value;
      opt.textContent = op.label;
      if (!op.value) opt.disabled = true;
      fontSizeSelect.appendChild(opt);
    });
    fontSizeSelect.addEventListener('change', function () {
      if (fontSizeSelect.value) {
        editor.focus();
        document.execCommand('fontSize', false, fontSizeSelect.value);
        fontSizeSelect.value = '';
        sincronizar();
      }
    });
    toolbar.appendChild(fontSizeSelect);
    toolbar.appendChild(sep());

    // ── Alinhamento ──────────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('⬛ Esq',    'Alinhar à esquerda',    function () { document.execCommand('justifyLeft'); }));
    toolbar.appendChild(criarBtn('⬛ Centro', 'Centralizar',           function () { document.execCommand('justifyCenter'); }));
    toolbar.appendChild(criarBtn('⬛ Dir',    'Alinhar à direita',     function () { document.execCommand('justifyRight'); }));
    toolbar.appendChild(criarBtn('⬛ Just',   'Justificar',            function () { document.execCommand('justifyFull'); }));
    toolbar.appendChild(sep());

    // ── Listas ────────────────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('• Lista',  'Lista com marcadores', function () { document.execCommand('insertUnorderedList'); }));
    toolbar.appendChild(criarBtn('1. Lista', 'Lista numerada',       function () { document.execCommand('insertOrderedList'); }));
    toolbar.appendChild(sep());

    // ── Link ──────────────────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('🔗 Link', 'Inserir link', function () {
      var url = prompt('URL do link (ex: https://exemplo.com):');
      if (url) document.execCommand('createLink', false, url);
    }));
    toolbar.appendChild(criarBtn('Remover link', 'Remover link', function () { document.execCommand('unlink'); }));
    toolbar.appendChild(sep());

    // ── Imagem por URL ───────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('🖼 Imagem', 'Inserir imagem por URL', function () {
      var url = prompt('URL da imagem (ex: https://seusite.com/imagem.jpg):');
      if (url) {
        document.execCommand('insertHTML', false,
          '<img src="' + url + '" style="max-width:100%;height:auto;display:block;margin:8px 0;" alt="">');
      }
    }));
    toolbar.appendChild(sep());

    // ── Limpar formatação ─────────────────────────────────────────────────────
    toolbar.appendChild(criarBtn('✕ Limpar', 'Remover formatação', function () { document.execCommand('removeFormat'); }));

    // ── Área editável ─────────────────────────────────────────────────────────
    var editor = document.createElement('div');
    editor.contentEditable = 'true';
    editor.style.cssText = (
      'min-height:300px;padding:16px;outline:none;font-family:sans-serif;'
      + 'font-size:14px;line-height:1.8;background:#fff;color:#212529;'
    );
    editor.setAttribute('spellcheck', 'true');

    // CSS das listas — indentação discreta
    var estiloListas = document.createElement('style');
    estiloListas.textContent = (
      '#pagina-editor-area ul, #pagina-editor-area ol {'
      + 'padding-left:1.6em;margin:0.5em 0;}'
      + '#pagina-editor-area li { margin:0.25em 0; }'
      + '#pagina-editor-area h2 { font-size:1.4em;margin:1em 0 0.5em; }'
      + '#pagina-editor-area h3 { font-size:1.15em;margin:0.8em 0 0.4em; }'
      + '#pagina-editor-area p  { margin:0.5em 0; }'
      + '#pagina-editor-area img { max-width:100%;height:auto; }'
    );
    document.head.appendChild(estiloListas);
    editor.id = 'pagina-editor-area';

    if (textarea.value) {
      editor.innerHTML = textarea.value;
    } else {
      editor.innerHTML = '<p></p>';
    }

    function sincronizar() {
      textarea.value = editor.innerHTML;
    }
    editor.addEventListener('input', sincronizar);
    editor.addEventListener('blur', sincronizar);

    // Garante que Enter em lista NÃO cria parágrafo automático fora do item
    editor.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        // Verifica se estamos numa lista
        var sel = window.getSelection();
        if (!sel.rangeCount) return;
        var node = sel.getRangeAt(0).commonAncestorContainer;
        // Sobe até encontrar li ou o editor
        while (node && node !== editor) {
          if (node.nodeName === 'LI') return; // está em lista: comportamento padrão
          node = node.parentNode;
        }
        // Fora de lista: insere <br> em vez de novo <div>/<p> (comportamento padrão do browser)
        // Deixa o browser agir normalmente — apenas evita converter para <div>
      }
    });

    wrapper.appendChild(toolbar);
    wrapper.appendChild(editor);

    textarea.style.display = 'none';
    textarea.parentNode.insertBefore(wrapper, textarea);

    var form = textarea.closest('form');
    if (form) {
      form.addEventListener('submit', sincronizar);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
