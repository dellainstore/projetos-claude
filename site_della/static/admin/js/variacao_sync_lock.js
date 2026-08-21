/**
 * Bloqueia/libera os campos `estoque` e `preco` em cada linha de variação
 * conforme os checkboxes `usa_sync_bling` e `usa_sync_preco_bling`. Espelha
 * o comportamento server-side do form VariacaoInlineForm para que o admin
 * não precise salvar antes de editar.
 */
(function () {
    'use strict';

    const PARES_SYNC = [
        { checkbox: 'usa_sync_bling', campo: 'estoque', hint: '🔒 Sincronizado pelo Bling' },
        { checkbox: 'usa_sync_preco_bling', campo: 'preco', hint: '🔒 Preço sincronizado pelo Bling' },
    ];

    function findRowFor(checkbox) {
        return checkbox.closest('tr') || checkbox.closest('.form-row') || checkbox.closest('.inline-related');
    }

    function findCampoInput(row, campo) {
        if (!row) return null;
        return row.querySelector(`input[name$="-${campo}"]`);
    }

    function isLinhaExistente(row) {
        // Linha nova (extra do formset ou clonada) tem o hidden "-id" vazio.
        // Só trava campo em linha que já existe salva no banco — travar uma
        // linha nova faz o campo obrigatório sumir do POST, o Django acha que
        // a linha "mudou" e tenta validar até cor/tamanho vazios (bloqueando
        // o salvamento inteiro do formset por causa de uma linha em branco
        // que nem era pra ser considerada).
        if (!row) return false;
        const hiddenId = row.querySelector('input[type="hidden"][name$="-id"]');
        return !!(hiddenId && hiddenId.value);
    }

    function applyLock(checkbox, par) {
        const row = findRowFor(checkbox);
        const input = findCampoInput(row, par.campo);
        if (!input) return;

        const locked = checkbox.checked && isLinhaExistente(row);
        // disabled strips the value from POST; server-side clean() trata o campo ausente.
        input.disabled = locked;
        input.readOnly = false;
        input.style.background = locked ? '#f5f5f5' : '';
        input.style.cursor = locked ? 'not-allowed' : '';
        input.title = locked ? par.hint : '';

        const hintClass = `sync-lock-hint-${par.campo}`;
        let hint = input.parentElement.querySelector(`.${hintClass}`);
        if (locked && !hint) {
            hint = document.createElement('div');
            hint.className = `sync-lock-hint ${hintClass}`;
            hint.style.cssText = 'font-size:11px;color:#888;margin-top:2px;';
            hint.textContent = par.hint;
            input.parentElement.appendChild(hint);
        } else if (!locked && hint) {
            hint.remove();
        }
    }

    function bindAll(scope) {
        const root = scope || document;
        PARES_SYNC.forEach((par) => {
            root.querySelectorAll(`input[type="checkbox"][name$="-${par.checkbox}"]`).forEach((cb) => {
                const bindKey = `syncLockBound_${par.checkbox}`;
                if (cb.dataset[bindKey]) return;
                cb.dataset[bindKey] = '1';
                cb.addEventListener('change', () => applyLock(cb, par));
                applyLock(cb, par);
            });
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
