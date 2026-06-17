/**
 * Editor rico para descrição e composição do Produto no admin.
 * Mantém a escrita mais maleável sem trocar o backend do campo.
 */
(function () {
  'use strict';

  const FIELD_CONFIG = {
    id_descricao: {
      areaId: 'produto-editor-descricao',
      minHeight: 280,
    },
    id_composicao: {
      areaId: 'produto-editor-composicao',
      minHeight: 220,
    },
  };

  function createButton(label, title, onClick, editor) {
    const button = document.createElement('button');
    button.type = 'button';
    button.innerHTML = label;
    button.title = title;
    button.style.cssText = [
      'padding:4px 8px',
      'border:1px solid #ccc',
      'background:#fff',
      'color:#212529',
      'cursor:pointer',
      'border-radius:3px',
      'font-size:12px',
      'line-height:1.4',
      'white-space:nowrap',
    ].join(';');
    button.addEventListener('mouseenter', function () {
      button.style.background = '#e9ecef';
    });
    button.addEventListener('mouseleave', function () {
      button.style.background = '#fff';
    });
    button.addEventListener('click', function () {
      editor.focus();
      onClick();
      sync(editor);
    });
    return button;
  }

  function createSeparator() {
    const separator = document.createElement('span');
    separator.style.cssText = 'width:1px;height:20px;background:#dee2e6;margin:0 4px;flex-shrink:0;';
    return separator;
  }

  function sync(editor) {
    const textarea = editor._linkedTextarea;
    textarea.value = editor.innerHTML;
  }

  function normalizeFontTags(editor) {
    editor.querySelectorAll('font').forEach(function (fontEl) {
      const span = document.createElement('span');
      const sizeMap = {
        '1': '0.75rem',
        '2': '0.875rem',
        '3': '1rem',
        '4': '1.125rem',
        '5': '1.3rem',
        '6': '1.55rem',
        '7': '1.8rem',
      };
      const size = fontEl.getAttribute('size');
      const color = fontEl.getAttribute('color');
      const face = fontEl.getAttribute('face');

      if (size && sizeMap[size]) span.style.fontSize = sizeMap[size];
      if (color) span.style.color = color;
      if (face) span.style.fontFamily = face;

      while (fontEl.firstChild) span.appendChild(fontEl.firstChild);
      fontEl.replaceWith(span);
    });
  }

  function buildEditor(textarea, config) {
    if (!textarea || textarea.dataset.richEditorReady === '1') return;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'border:1px solid #ccc;border-radius:4px;overflow:hidden;color-scheme:light;';

    const toolbar = document.createElement('div');
    toolbar.style.cssText = [
      'background:#f8f9fa',
      'border-bottom:1px solid #dee2e6',
      'padding:6px 8px',
      'display:flex',
      'flex-wrap:wrap',
      'gap:4px',
      'align-items:center',
      'color:#212529',
    ].join(';');

    const editor = document.createElement('div');
    editor.contentEditable = 'true';
    editor.id = config.areaId;
    editor._linkedTextarea = textarea;
    editor.style.cssText = [
      'min-height:' + config.minHeight + 'px',
      'padding:16px',
      'outline:none',
      'font-family:sans-serif',
      'font-size:14px',
      'line-height:1.8',
      'background:#fff',
      'color:#212529',
    ].join(';');
    editor.setAttribute('spellcheck', 'true');
    editor.innerHTML = textarea.value || '<p></p>';

    toolbar.appendChild(createButton('<b>N</b>', 'Negrito', function () {
      document.execCommand('bold');
    }, editor));
    toolbar.appendChild(createButton('<i>I</i>', 'Itálico', function () {
      document.execCommand('italic');
    }, editor));
    toolbar.appendChild(createButton('<u>S</u>', 'Sublinhado', function () {
      document.execCommand('underline');
    }, editor));
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('Título', 'Título H2', function () {
      document.execCommand('formatBlock', false, 'h2');
    }, editor));
    toolbar.appendChild(createButton('Subtítulo', 'Título H3', function () {
      document.execCommand('formatBlock', false, 'h3');
    }, editor));
    toolbar.appendChild(createButton('Parágrafo', 'Parágrafo normal', function () {
      document.execCommand('formatBlock', false, 'p');
    }, editor));
    toolbar.appendChild(createSeparator());

    const fontSizeSelect = document.createElement('select');
    fontSizeSelect.title = 'Tamanho da fonte';
    fontSizeSelect.style.cssText = 'padding:2px 4px;border:1px solid #ccc;border-radius:3px;font-size:12px;background:#fff;color:#212529;cursor:pointer;';
    [
      { label: 'Fonte', value: '' },
      { label: 'Pequena', value: '2' },
      { label: 'Normal', value: '3' },
      { label: 'Grande', value: '4' },
      { label: 'Maior', value: '5' },
      { label: 'Destaque', value: '6' },
    ].forEach(function (optionData) {
      const option = document.createElement('option');
      option.value = optionData.value;
      option.textContent = optionData.label;
      if (!optionData.value) option.disabled = true;
      fontSizeSelect.appendChild(option);
    });
    fontSizeSelect.addEventListener('change', function () {
      if (!fontSizeSelect.value) return;
      editor.focus();
      document.execCommand('fontSize', false, fontSizeSelect.value);
      normalizeFontTags(editor);
      fontSizeSelect.value = '';
      sync(editor);
    });
    toolbar.appendChild(fontSizeSelect);
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('Esq', 'Alinhar à esquerda', function () {
      document.execCommand('justifyLeft');
    }, editor));
    toolbar.appendChild(createButton('Centro', 'Centralizar', function () {
      document.execCommand('justifyCenter');
    }, editor));
    toolbar.appendChild(createButton('Dir', 'Alinhar à direita', function () {
      document.execCommand('justifyRight');
    }, editor));
    toolbar.appendChild(createButton('Just', 'Justificar', function () {
      document.execCommand('justifyFull');
    }, editor));
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('Recuar', 'Aumentar margem à esquerda', function () {
      document.execCommand('indent');
    }, editor));
    toolbar.appendChild(createButton('Voltar', 'Diminuir margem à esquerda', function () {
      document.execCommand('outdent');
    }, editor));
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('• Lista', 'Lista com marcadores', function () {
      document.execCommand('insertUnorderedList');
    }, editor));
    toolbar.appendChild(createButton('1. Lista', 'Lista numerada', function () {
      document.execCommand('insertOrderedList');
    }, editor));
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('Link', 'Inserir link', function () {
      const url = window.prompt('URL do link:');
      if (url) document.execCommand('createLink', false, url);
    }, editor));
    toolbar.appendChild(createButton('Sem link', 'Remover link', function () {
      document.execCommand('unlink');
    }, editor));
    toolbar.appendChild(createSeparator());

    toolbar.appendChild(createButton('Limpar', 'Remover formatação', function () {
      document.execCommand('removeFormat');
    }, editor));

    const style = document.createElement('style');
    style.textContent = [
      '#produto-editor-descricao ul, #produto-editor-descricao ol, #produto-editor-composicao ul, #produto-editor-composicao ol { padding-left: 1.6em; margin: 0.5em 0; }',
      '#produto-editor-descricao li, #produto-editor-composicao li { margin: 0.25em 0; }',
      '#produto-editor-descricao h2, #produto-editor-composicao h2 { font-size: 1.4em; margin: 1em 0 0.5em; }',
      '#produto-editor-descricao h3, #produto-editor-composicao h3 { font-size: 1.15em; margin: 0.8em 0 0.4em; }',
      '#produto-editor-descricao p, #produto-editor-composicao p { margin: 0.5em 0; }',
      '#produto-editor-descricao blockquote, #produto-editor-composicao blockquote { margin: 0.75em 0 0.75em 1.2em; padding-left: 0.9em; border-left: 2px solid #d7c39a; }',
    ].join('');
    document.head.appendChild(style);

    editor.addEventListener('input', function () {
      normalizeFontTags(editor);
      sync(editor);
    });
    editor.addEventListener('blur', function () {
      normalizeFontTags(editor);
      sync(editor);
    });

    wrapper.appendChild(toolbar);
    wrapper.appendChild(editor);

    textarea.style.display = 'none';
    textarea.parentNode.insertBefore(wrapper, textarea);
    textarea.dataset.richEditorReady = '1';

    const form = textarea.closest('form');
    if (form && !form.dataset.produtoRichSyncBound) {
      form.addEventListener('submit', function () {
        Object.keys(FIELD_CONFIG).forEach(function (fieldId) {
          const field = document.getElementById(fieldId);
          if (field && field.dataset.richEditorReady === '1') {
            const richAreaId = FIELD_CONFIG[fieldId].areaId;
            const richArea = document.getElementById(richAreaId);
            if (richArea) {
              normalizeFontTags(richArea);
              sync(richArea);
            }
          }
        });
      });
      form.dataset.produtoRichSyncBound = '1';
    }
  }

  function init() {
    Object.keys(FIELD_CONFIG).forEach(function (fieldId) {
      buildEditor(document.getElementById(fieldId), FIELD_CONFIG[fieldId]);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
