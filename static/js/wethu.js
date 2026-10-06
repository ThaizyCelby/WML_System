/*
 * Wethu Micro Lenders — shared front-end helpers.
 * Handles HTMX toasts, a simple modal, and CSRF header injection.
 */
(function () {
  'use strict';

  // ---- CSRF token from <meta name="csrf-token"> ----
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : null;

  document.body.addEventListener('htmx:configRequest', function (evt) {
    if (csrfToken) {
      evt.detail.headers['X-CSRFToken'] = csrfToken;
    }
  });

  // ---- Toast helper ----
  function showToast(message, level) {
    const box = document.getElementById('htmx-toast');
    if (!box) return;
    const colors = {
      success: 'bg-emerald-600',
      error:   'bg-red-600',
      warning: 'bg-amber-500',
      info:    'bg-slate-700',
    };
    const el = document.createElement('div');
    el.className =
      'rounded-lg px-4 py-3 text-sm text-white shadow-lg transition-opacity duration-300 ' +
      (colors[level] || colors.info);
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 300);
    }, 4000);
  }

  // HTMX: server can send `HX-Trigger: {"toast":{"message":"...","level":"success"}}`
  document.body.addEventListener('toast', function (evt) {
    const d = evt.detail || {};
    showToast(d.message || d.value || 'Done', d.level || 'info');
  });

  // HTMX errors → red toast
  document.body.addEventListener('htmx:responseError', function (evt) {
    showToast('Request failed (' + evt.detail.xhr.status + ')', 'error');
  });

  // ---- Simple modal ----
  window.wethuOpenModal = function (html) {
    const m = document.getElementById('htmx-modal');
    if (!m) return;
    m.innerHTML =
      '<div class="absolute inset-0 flex items-center justify-center p-4">' +
      '<div class="bg-white dark:bg-slate-900 rounded-xl shadow-xl max-w-lg w-full p-6">' +
      html +
      '</div></div>';
    m.classList.remove('hidden');
    m.addEventListener('click', function (e) {
      if (e.target === m) window.wethuCloseModal();
    });
  };

  window.wethuCloseModal = function () {
    const m = document.getElementById('htmx-modal');
    if (!m) return;
    m.classList.add('hidden');
    m.innerHTML = '';
  };
})();

