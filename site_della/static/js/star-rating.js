(function () {
  'use strict';

  function paint(widget, value) {
    const stars = widget.querySelectorAll('.star-rating__star');
    const current = parseInt(value || '0', 10);
    stars.forEach((star) => {
      const starValue = parseInt(star.dataset.value || '0', 10);
      star.classList.toggle('is-active', starValue <= current);
    });
  }

  function init(widget) {
    if (!widget || widget.dataset.starReady === '1') return;

    const input = widget.querySelector('.star-rating__control');
    const stars = widget.querySelectorAll('.star-rating__star');
    if (!input || !stars.length) return;

    const sync = (value) => {
      input.value = value;
      paint(widget, value);
    };

    stars.forEach((star) => {
      const value = star.dataset.value;
      star.addEventListener('mouseenter', () => paint(widget, value));
      star.addEventListener('click', () => sync(value));
      star.addEventListener('focus', () => paint(widget, value));
    });

    widget.addEventListener('mouseleave', () => paint(widget, input.value));
    widget.addEventListener('focusout', () => {
      window.setTimeout(() => paint(widget, input.value), 0);
    });

    paint(widget, input.value || widget.dataset.current || '');
    widget.dataset.starReady = '1';
  }

  function boot() {
    document.querySelectorAll('.js-star-rating').forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
