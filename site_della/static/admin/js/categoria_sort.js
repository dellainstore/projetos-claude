(function () {
  'use strict';

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var parts = cookies[i].split('=');
      var key = parts.shift();
      if (key === name) {
        return decodeURIComponent(parts.join('='));
      }
    }
    return '';
  }

  function closestBefore(container, y, selector, dragged) {
    var items = Array.prototype.slice.call(container.querySelectorAll(selector)).filter(function (item) {
      return item !== dragged;
    });

    var closest = null;
    var closestOffset = Number.NEGATIVE_INFINITY;

    items.forEach(function (item) {
      var box = item.getBoundingClientRect();
      var offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closestOffset) {
        closestOffset = offset;
        closest = item;
      }
    });

    return closest;
  }

  function initCategoriaSort() {
    var app = document.getElementById('categoria-sort-app');
    if (!app) return;

    var root = document.getElementById('categoria-sort-root');
    var saveButton = document.getElementById('categoria-sort-save');
    var status = document.getElementById('categoria-sort-status');
    var draggedGroup = null;
    var draggedChild = null;
    var activeHandle = null;

    function setStatus(message, type) {
      if (!status) return;
      status.textContent = message || '';
      status.classList.remove('is-ok', 'is-error', 'is-loading');
      if (type) status.classList.add(type);
    }

    root.querySelectorAll('.categoria-sort-handle').forEach(function (handle) {
      handle.setAttribute('draggable', 'true');

      handle.addEventListener('mousedown', function (event) {
        activeHandle = event.currentTarget;
      });

      handle.addEventListener('mouseup', function () {
        activeHandle = null;
      });

      handle.addEventListener('dragstart', function (event) {
        activeHandle = event.currentTarget;
      });
    });

    root.querySelectorAll('.categoria-sort-row-click').forEach(function (row) {
      row.addEventListener('click', function (event) {
        var target = event.target;
        if (
          target.closest('a') ||
          target.closest('button') ||
          target.closest('.categoria-sort-handle')
        ) {
          return;
        }
        var url = row.dataset.editUrl;
        if (url) window.location.href = url;
      });
    });

    root.querySelectorAll('.categoria-sort-toggle').forEach(function (toggle) {
      if (toggle.classList.contains('categoria-sort-toggle-placeholder')) return;
      toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        var group = toggle.closest('.categoria-sort-group');
        var children = group.querySelector('.categoria-sort-children');
        if (!children) return;
        var collapsed = children.classList.toggle('is-collapsed');
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      });
    });

    root.querySelectorAll('.categoria-sort-group').forEach(function (group) {
      group.addEventListener('dragstart', function (event) {
        if (!activeHandle || !group.contains(activeHandle)) return;
        if (!event.target.closest('.categoria-sort-parent') && !activeHandle.closest('.categoria-sort-parent')) return;
        draggedGroup = group;
        group.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', group.dataset.categoryId || '');
      });

      group.addEventListener('dragend', function () {
        group.classList.remove('is-dragging');
        draggedGroup = null;
        activeHandle = null;
      });
    });

    root.addEventListener('dragover', function (event) {
      if (!draggedGroup) return;
      event.preventDefault();
      var before = closestBefore(root, event.clientY, '.categoria-sort-group', draggedGroup);
      if (before) {
        root.insertBefore(draggedGroup, before);
      } else {
        root.appendChild(draggedGroup);
      }
    });

    root.querySelectorAll('.categoria-sort-child').forEach(function (child) {
      child.addEventListener('dragstart', function (event) {
        if (!activeHandle || !child.contains(activeHandle)) return;
        draggedChild = child;
        child.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', child.dataset.categoryId || '');
      });

      child.addEventListener('dragend', function () {
        child.classList.remove('is-dragging');
        draggedChild = null;
        activeHandle = null;
      });
    });

    root.querySelectorAll('.categoria-sort-children').forEach(function (container) {
      container.addEventListener('dragover', function (event) {
        if (!draggedChild) return;
        if (draggedChild.dataset.parentId !== container.dataset.parentId) return;
        event.preventDefault();
        var empty = container.querySelector('.categoria-sort-empty');
        if (empty) empty.remove();
        var before = closestBefore(container, event.clientY, '.categoria-sort-child', draggedChild);
        if (before) {
          container.insertBefore(draggedChild, before);
        } else {
          container.appendChild(draggedChild);
        }
      });
    });

    saveButton.addEventListener('click', function () {
      var payload = { parents: [], children: {} };

      root.querySelectorAll('.categoria-sort-group').forEach(function (group) {
        var parentId = parseInt(group.dataset.categoryId, 10);
        payload.parents.push(parentId);
        payload.children[parentId] = Array.prototype.slice.call(
          group.querySelectorAll('.categoria-sort-child')
        ).map(function (child) {
          return parseInt(child.dataset.categoryId, 10);
        });
      });

      saveButton.disabled = true;
      setStatus('Salvando...', 'is-loading');

      fetch(app.dataset.saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) {
              throw new Error(data.error || 'Nao foi possivel salvar a ordenacao.');
            }
            return data;
          });
        })
        .then(function () {
          setStatus('Ordem salva com sucesso.', 'is-ok');
          window.setTimeout(function () {
            window.location.reload();
          }, 500);
        })
        .catch(function (error) {
          setStatus(error.message || 'Erro ao salvar a ordenacao.', 'is-error');
        })
        .finally(function () {
          saveButton.disabled = false;
        });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCategoriaSort);
  } else {
    initCategoriaSort();
  }
})();
