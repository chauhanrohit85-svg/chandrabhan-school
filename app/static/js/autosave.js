/**
 * autosave.js — LocalStorage auto-save for all teacher data-entry forms.
 * Fires every 3 seconds on input events AND on beforeunload.
 * Key format: "autosave_<formId>_<YYYY-MM-DD>"
 */

(function () {
  'use strict';

  const SAVE_INTERVAL_MS = 3000;
  const today = new Date().toISOString().split('T')[0];

  /** Collect all form field values into a plain object */
  function serializeForm(form) {
    const data = {};
    const elements = form.querySelectorAll('input, select, textarea');
    elements.forEach(el => {
      if (!el.name) return;
      if (el.type === 'checkbox') {
        data[el.name] = el.checked ? '1' : '0';
      } else if (el.type === 'radio') {
        if (el.checked) data[el.name] = el.value;
      } else {
        data[el.name] = el.value;
      }
    });
    return data;
  }

  /** Restore previously saved form data from localStorage */
  function restoreForm(form) {
    const key = `autosave_${form.id}_${today}`;
    const saved = localStorage.getItem(key);
    if (!saved) return;

    let data;
    try { data = JSON.parse(saved); } catch (e) { return; }

    const elements = form.querySelectorAll('input, select, textarea');
    elements.forEach(el => {
      if (!el.name || !(el.name in data)) return;
      if (el.type === 'checkbox') {
        el.checked = data[el.name] === '1';
      } else if (el.type === 'radio') {
        el.checked = (el.value === data[el.name]);
      } else {
        el.value = data[el.name];
      }
    });

    showIndicator(form, 'saved');
    console.log(`[AutoSave] Restored form "${form.id}" from localStorage (${today})`);
  }

  /** Show autosave state indicator */
  function showIndicator(form, state) {
    const indicator = document.getElementById('autosave-indicator');
    if (!indicator) return;
    indicator.className = `autosave-indicator ${state}`;
    const textEl = indicator.querySelector('.autosave-text');
    if (textEl) {
      textEl.textContent = state === 'saving' ? 'Saving…' : '✓ Draft saved';
    }
  }

  /** Save form data to localStorage */
  function saveForm(form) {
    if (!form.id) return;
    const key = `autosave_${form.id}_${today}`;
    const data = serializeForm(form);
    try {
      localStorage.setItem(key, JSON.stringify(data));
      showIndicator(form, 'saved');
      console.log(`[AutoSave] Saved form "${form.id}"`, data);
    } catch (e) {
      console.warn('[AutoSave] localStorage write failed:', e);
    }
  }

  /** Clear saved data after successful form submission */
  function clearSavedForm(form) {
    if (!form.id) return;
    const key = `autosave_${form.id}_${today}`;
    localStorage.removeItem(key);
    console.log(`[AutoSave] Cleared "${key}" after submission`);
  }

  /** Initialise auto-save on all forms with data-autosave attribute */
  function init() {
    const forms = document.querySelectorAll('form[data-autosave]');
    if (!forms.length) return;

    forms.forEach(form => {
      // Restore on load
      restoreForm(form);

      // Save on any input change
      let timer = null;
      form.addEventListener('input', () => {
        showIndicator(form, 'saving');
        clearTimeout(timer);
        timer = setTimeout(() => saveForm(form), SAVE_INTERVAL_MS);
      });

      // Save on change (selects, checkboxes)
      form.addEventListener('change', () => {
        showIndicator(form, 'saving');
        clearTimeout(timer);
        timer = setTimeout(() => saveForm(form), 500);
      });

      // Clear on successful submit
      form.addEventListener('submit', () => {
        clearSavedForm(form);
      });
    });

    // Emergency save before page unload
    window.addEventListener('beforeunload', () => {
      forms.forEach(form => saveForm(form));
    });

    console.log(`[AutoSave] Initialized on ${forms.length} form(s)`);
  }

  // Run after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
