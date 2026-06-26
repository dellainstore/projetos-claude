/**
 * Bloqueia/libera o campo `estoque` em cada linha de variação conforme o
 * checkbox `usa_sync_bling`. Espelha o comportamento server-side do form
 * VariacaoInlineForm para que o admin não precise salvar antes de editar.
 */
(function () {
    'use strict';

    const FIELD_SYNC = 'usa_sync_bling';
    const FIELD_ESTOQUE = 'estoque';
    const HELP_TEXT = '🔒 Sincronizado pelo Bling';

    function findRowFor(checkbox) {
        return checkbox.closest('tr') || checkbox.closest('.form-row') || checkbox.closest('.inline-related');
    }

    function findEstoqueInput(row) {
        if (!row) return null;
        return row.querySelector(`input[name$="-${FIELD_ESTOQUE}"]`);
    }

    function applyLock(checkbox) {
        const row = findRowFor(checkbox);
        const input = findEstoqueInput(row);
        if (!input) return;

        const locked = checkbox.checked;
        // disabled strips the value from POST; server-side clean() trata o campo ausente.
        input.disabled = locked;
        input.readOnly = false;
        input.style.background = locked ? '#f5f5f5' : '';
        input.style.cursor = locked ? 'not-allowed' : '';
        input.title = locked ? HELP_TEXT : '';

        let hint = input.parentElement.querySelector('.sync-lock-hint');
        if (locked && !hint) {
            hint = document.createElement('div');
            hint.className = 'sync-lock-hint';
            hint.style.cssText = 'font-size:11px;color:#888;margin-top:2px;';
            hint.textContent = HELP_TEXT;
            input.parentElement.appendChild(hint);
        } else if (!locked && hint) {
            hint.remove();
        }
    }

    function bindAll(scope) {
        const root = scope || document;
        root.querySelectorAll(`input[type="checkbox"][name$="-${FIELD_SYNC}"]`).forEach((cb) => {
            if (cb.dataset.syncLockBound) return;
            cb.dataset.syncLockBound = '1';
            cb.addEventListener('change', () => applyLock(cb));
            applyLock(cb);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindAll();

        // Django dispara este evento quando uma nova linha de inline é adicionada.
        if (typeof django !== 'undefined' && django.jQuery) {
            django.jQuery(document).on('formset:added', (_event, $row) => {
                bindAll($row[0]);
            });
        }

        // Fallback: observa novas linhas inseridas dinamicamente sem evento.
        const tbody = document.querySelector('.inline-group tbody, .tabular tbody');
        if (tbody && 'MutationObserver' in window) {
            new MutationObserver((mutations) => {
                mutations.forEach((m) => m.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) bindAll(node);
                }));
            }).observe(tbody, { childList: true });
        }
    });
})();
