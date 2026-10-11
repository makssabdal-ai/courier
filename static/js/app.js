if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

document.addEventListener('DOMContentLoaded', () => {

  // 1. Авто-скрытие сообщений через 4 сек
  document.querySelectorAll('.msg-auto').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.6s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 650);
    }, 4000);
  });

  // 2. Кнопки «Печать»
  document.querySelectorAll('.btn-print').forEach(btn => {
    btn.type = 'button';
    btn.addEventListener('click', e => {
      e.preventDefault();
      setTimeout(() => window.print(), 150);
    });
  });

  // 3. Маска трек-номера RU-XX-XXXXXXXXX
  const trackInput = document.getElementById('track_number');
  if (trackInput) initTrackMask(trackInput);

  // 4. Валидация телефона
  document.querySelectorAll('input[name="recipient_phone"]').forEach(el => {
    el.addEventListener('blur', () => validatePhoneInput(el));
  });

  // 5. Select-all чекбокс
  const selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.addEventListener('change', function () {
      document.querySelectorAll('.row-check').forEach(cb => { cb.checked = this.checked; });
    });
  }

  // 6. Подтверждение для накладной до 17:00
  const deliveryForm = document.getElementById('form-delivery-list');
  if (deliveryForm) {
    deliveryForm.addEventListener('submit', function (e) {
      const earlyField = document.getElementById('early_confirmed');
      if (earlyField && earlyField.value !== '1' && deliveryForm.dataset.canForm !== 'true') {
        e.preventDefault();
        if (confirm('Сейчас до 17:00. Подтвердить формирование накладной?')) {
          earlyField.value = '1';
          deliveryForm.submit();
        }
      }
    });
  }

  // 7. Подтверждение накладной возврата (менеджер)
  const returnForm = document.getElementById('form-confirm-return');
  if (returnForm) {
    returnForm.addEventListener('submit', function (e) {
      e.preventDefault();
      const count = parseInt(returnForm.dataset.count || '0', 10);
      if (confirm('Создать накладную на возврат для ' + count + ' посылок?')) {
        returnForm.submit();
      }
    });
  }

});

function initTrackMask(input) {
  const PREFIX = 'RU-';
  const MAX_DIGITS = 11;
  function digitsOnly(s) { return s.replace(/\D/g, '').slice(0, MAX_DIGITS); }
  function applyMask(d) {
    let r = PREFIX;
    if (d.length > 0) r += d.slice(0, 2);
    if (d.length > 2) r += '-' + d.slice(2);
    return r;
  }
  if (!input.value.startsWith(PREFIX)) input.value = PREFIX;
  input.addEventListener('focus', () => {
    if (!input.value.startsWith(PREFIX)) input.value = PREFIX;
    const l = input.value.length;
    setTimeout(() => input.setSelectionRange(l, l), 0);
  });
  input.addEventListener('keydown', e => {
    const pos = input.selectionStart || 0;
    if ((e.key === 'Backspace' || e.key === 'Delete') && pos <= PREFIX.length) e.preventDefault();
    const ok = ['Backspace','Delete','ArrowLeft','ArrowRight','Tab','Home','End'];
    if (!ok.includes(e.key) && !/^\d$/.test(e.key) && !e.ctrlKey && !e.metaKey) e.preventDefault();
  });
  input.addEventListener('input', () => {
    const raw = input.value.startsWith(PREFIX) ? input.value.slice(PREFIX.length) : input.value;
    input.value = applyMask(digitsOnly(raw));
  });
  input.addEventListener('paste', e => {
    e.preventDefault();
    const p = (e.clipboardData || window.clipboardData).getData('text');
    input.value = applyMask(digitsOnly(p.replace(/^RU-?/i, '')));
  });
}

function validatePhoneInput(input) {
  const val = input.value.trim();
  if (!val) { clearPhoneError(input); return; }
  if (!/^\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$/.test(val)) {
    input.style.borderColor = 'red';
    input.title = 'Неверный формат. Пример: +7 (900) 123-45-67';
  } else {
    clearPhoneError(input);
  }
}
function clearPhoneError(input) {
  input.style.borderColor = '';
  input.title = '';
}
