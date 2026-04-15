/**
 * Editor de texto rico simples para PaginaEstatica no admin Django.
 * Converte o textarea "conteudo" num editor WYSIWYG com barra de ferramentas.
 * Sem dependências externas.
 */
(function() {
  'use strict';

  function init() {
    const textarea = document.getElementById('id_conteudo');
    if (!textarea) return;

    // Cria o container
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'border:1px solid #ccc;border-radius:4px;overflow:hidden;';

    // Barra de ferramentas
    const toolbar = document.createElement('div');
    toolbar.style.cssText = (
      'background:#f8f9fa;border-bottom:1px solid #dee2e6;padding:6px 8px;'
      + 'display:flex;flex-wrap:wrap;gap:4px;align-items:center;'
    );

    const buttons = [
      { cmd: 'bold',          label: '<b>N</b>',        title: 'Negrito (Ctrl+B)' },
      { cmd: 'italic',        label: '<i>I</i>',        title: 'Itálico (Ctrl+I)' },
      { cmd: 'underline',     label: '<u>S</u>',        title: 'Sublinhado (Ctrl+U)' },
      { sep: true },
      { cmd: 'h2',            label: 'Título',          title: 'Título (H2)' },
      { cmd: 'h3',            label: 'Subtítulo',       title: 'Subtítulo (H3)' },
      { cmd: 'p',             label: 'Parágrafo',       title: 'Parágrafo normal' },
      { sep: true },
      { cmd: 'insertUnorderedList', label: '• Lista',   title: 'Lista com marcadores' },
      { cmd: 'insertOrderedList',   label: '1. Lista',  title: 'Lista numerada' },
      { sep: true },
      { cmd: 'createLink',    label: '🔗 Link',         title: 'Inserir link' },
      { cmd: 'unlink',        label: 'Remover link',    title: 'Remover link' },
      { sep: true },
      { cmd: 'removeFormat',  label: '✕ Limpar',        title: 'Remover formatação' },
    ];

    buttons.forEach(function(btn) {
      if (btn.sep) {
        const sep = document.createElement('span');
        sep.style.cssText = 'width:1px;height:20px;background:#dee2e6;margin:0 4px;';
        toolbar.appendChild(sep);
        return;
      }
      const b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = btn.label;
      b.title = btn.title;
      b.style.cssText = (
        'padding:3px 8px;border:1px solid #ccc;background:white;cursor:pointer;'
        + 'border-radius:3px;font-size:12px;line-height:1.4;'
      );
      b.addEventListener('mouseenter', function() { b.style.background = '#e9ecef'; });
      b.addEventListener('mouseleave', function() { b.style.background = 'white'; });

      b.addEventListener('click', function() {
        editor.focus();
        if (btn.cmd === 'h2' || btn.cmd === 'h3' || btn.cmd === 'p') {
          document.execCommand('formatBlock', false, btn.cmd);
        } else if (btn.cmd === 'createLink') {
          const url = prompt('URL do link (ex: https://exemplo.com):');
          if (url) document.execCommand('createLink', false, url);
        } else {
          document.execCommand(btn.cmd, false, null);
        }
        sincronizar();
      });
      toolbar.appendChild(b);
    });

    // Área editável
    const editor = document.createElement('div');
    editor.contentEditable = 'true';
    editor.style.cssText = (
      'min-height:300px;padding:12px;outline:none;font-family:sans-serif;'
      + 'font-size:14px;line-height:1.7;background:white;'
    );
    editor.setAttribute('spellcheck', 'true');

    // Carrega conteúdo atual do textarea
    if (textarea.value) {
      editor.innerHTML = textarea.value;
    } else {
      editor.innerHTML = '<p></p>';
    }

    // Sincroniza editor → textarea ao digitar
    function sincronizar() {
      textarea.value = editor.innerHTML;
    }
    editor.addEventListener('input', sincronizar);
    editor.addEventListener('blur', sincronizar);

    // Monta a estrutura
    wrapper.appendChild(toolbar);
    wrapper.appendChild(editor);

    // Oculta o textarea original mas mantém no DOM para o form submit
    textarea.style.display = 'none';
    textarea.parentNode.insertBefore(wrapper, textarea);

    // Antes do submit, garante sincronização
    const form = textarea.closest('form');
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
