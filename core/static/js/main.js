/* EduCRM Pro — main.js */
'use strict';

// ── Theme ────────────────────────────────────────────────────────
const THEME_KEY = 'sargetcrm_theme';

function applyTheme(theme) {
  function doApply() {
    document.body.classList.toggle('light-mode', theme === 'light');
    // Update all theme toggle buttons (icon + label) so they stay in sync across pages
    document.querySelectorAll('.theme-toggle').forEach(btn => {
      const icon = btn.querySelector('.theme-icon');
      if (icon) icon.className = theme === 'light' ? 'theme-icon fas fa-moon' : 'theme-icon fas fa-sun';
      const label = btn.querySelector('.theme-label');
      if (label) label.textContent = theme === 'light' ? "Qora rejim" : "Yorug' rejim";
    });
  }

  if (document.body) doApply();
  else document.addEventListener('DOMContentLoaded', doApply);
}

function toggleTheme() {
  const current = localStorage.getItem(THEME_KEY) || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

(function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(saved);
})();

// ── Sidebar ──────────────────────────────────────────────────────
function initSidebar() {
  const toggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  if (!toggle || !sidebar) return;
  const mobileToggle = document.getElementById('mobileMenuToggle');
  const buttons = [toggle, mobileToggle].filter(Boolean);
  const mobile = window.matchMedia('(max-width: 900px)');
  const groups = [...sidebar.querySelectorAll('.nav-group')];
  function setGroup(group, open) {
    group.classList.toggle('expanded', open);
    group.querySelector('.nav-group-toggle').setAttribute('aria-expanded', String(open));
    group.querySelector('.nav-group-panel').inert = !open;
  }
  groups.forEach(group => {
    const links = [...group.querySelectorAll('a')];
    if (!links.length) {
      group.hidden = true;
      return;
    }
    const current = links.find(link => new URL(link.href).pathname === window.location.pathname);
    if (current) {
      current.classList.add('active');
      current.setAttribute('aria-current', 'page');
    }
    group.classList.toggle('has-active', links.some(link => link.classList.contains('active')));
    group.querySelector('.nav-group-toggle').addEventListener('click', () => {
      const open = !group.classList.contains('expanded');
      groups.forEach(other => setGroup(other, other === group && open));
    });
  });
  let desktopCollapsed = false;
  let lastTrigger = toggle;
  try { desktopCollapsed = localStorage.getItem('sargetcrm_sidebar_collapsed') === 'true'; } catch (e) { /* optional preference */ }

  function setSidebar(open, restoreFocus = false) {
    sidebar.classList.toggle('open', mobile.matches && open);
    document.body.classList.toggle('sidebar-collapsed', !mobile.matches && !open);
    document.body.classList.toggle('menu-open', mobile.matches && open);
    overlay.classList.toggle('visible', mobile.matches && open);
    sidebar.inert = !open;
    const modalOpen = mobile.matches && open;
    document.querySelector('main').inert = modalOpen;
    document.querySelectorAll('.mobile-nav a').forEach(link => { link.inert = modalOpen; });
    sidebar.setAttribute('aria-hidden', String(!open));
    buttons.forEach(button => {
      button.setAttribute('aria-expanded', String(open));
      button.setAttribute('aria-label', open ? 'Menyuni yopish' : 'Menyuni ochish');
      button.querySelector('i').className = open ? 'fas fa-xmark' : 'fas fa-bars';
    });
    if (restoreFocus) lastTrigger.focus();
  }

  buttons.forEach(button => button.addEventListener('click', () => {
    lastTrigger = button;
    const open = button.getAttribute('aria-expanded') !== 'true';
    if (!mobile.matches) {
      desktopCollapsed = !open;
      try { localStorage.setItem('sargetcrm_sidebar_collapsed', String(desktopCollapsed)); } catch (e) { /* optional preference */ }
    }
    setSidebar(open);
    if (mobile.matches && open) sidebar.querySelector('.nav-group:not([hidden]) .nav-group-toggle').focus();
  }));
  overlay.addEventListener('click', () => setSidebar(false, true));
  sidebar.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    if (mobile.matches) setSidebar(false, true);
  }));
  document.addEventListener('keydown', event => {
    if (!mobile.matches || !sidebar.classList.contains('open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setSidebar(false, true);
    }
    if (event.key === 'Tab') {
      const focusable = [toggle, ...sidebar.querySelectorAll('a[href], button:not([disabled])'), mobileToggle]
        .filter(element => element && !element.closest('[inert], [hidden]') && element.getClientRects().length);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });
  mobile.addEventListener('change', () => setSidebar(!mobile.matches && !desktopCollapsed));
  document.querySelectorAll('.mobile-nav-item.active').forEach(link => link.setAttribute('aria-current', 'page'));
  setSidebar(!mobile.matches && !desktopCollapsed);
}

// ── Alerts ───────────────────────────────────────────────────────
function initAlerts() {
  document.querySelectorAll('.alert .close').forEach(btn => {
    btn.addEventListener('click', () => {
      const alert = btn.closest('.alert');
      if (!alert) return;
      alert.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-4px)';
      setTimeout(() => alert.remove(), 200);
    });
  });
  // Auto-dismiss success & info alerts after 2.8s
  setTimeout(() => {
    document.querySelectorAll('.alert-success, .alert-info').forEach(a => {
      a.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
      a.style.opacity = '0';
      a.style.transform = 'translateY(-4px)';
      setTimeout(() => a.remove(), 250);
    });
  }, 2800);
}

function initNotifications() {
  const center = document.getElementById('notificationCenter');
  if (!center) return;

  const bell = document.getElementById('notificationBell');
  const panel = document.getElementById('notificationPanel');
  const list = document.getElementById('notificationList');
  const count = document.getElementById('notificationCount');
  const toasts = document.getElementById('notificationToasts');
  const status = document.getElementById('notificationStatus');
  const soundButton = document.getElementById('notificationSound');
  const cursorStorageKey = `sargetcrm_notification_cursor_${center.dataset.userId}`;
  const soundStorageKey = 'sargetcrm_notification_sound';
  let cursor = Number(center.dataset.cursor) || 0;
  let soundEnabled = true;
  let audioContext = null;
  let pendingSounds = 0;
  let polling = false;

  try {
    const savedCursor = Number(sessionStorage.getItem(cursorStorageKey));
    if (Number.isFinite(savedCursor) && savedCursor >= 0) cursor = savedCursor;
    soundEnabled = localStorage.getItem(soundStorageKey) !== 'off';
  } catch (error) {
    console.warn('Bildirishnoma sozlamalari bu brauzerda saqlanmadi.', error);
  }

  function updateCount(value) {
    count.textContent = String(value);
    count.hidden = value < 1;
  }

  function updateSoundButton() {
    soundButton.setAttribute('aria-pressed', String(soundEnabled));
    soundButton.setAttribute(
      'aria-label',
      soundEnabled ? 'Bildirishnoma ovozini o‘chirish' : 'Bildirishnoma ovozini yoqish'
    );
    soundButton.title = soundEnabled ? 'Bildirishnoma ovozi yoqilgan' : 'Bildirishnoma ovozi o‘chirilgan';
    soundButton.innerHTML = `<i class="fas ${soundEnabled ? 'fa-volume-high' : 'fa-volume-xmark'}"></i>`;
  }

  function playNotificationSound() {
    if (!soundEnabled) return;
    if (!audioContext || audioContext.state !== 'running') {
      pendingSounds = Math.min(pendingSounds + 1, 3);
      return;
    }

    const startAt = audioContext.currentTime;
    [880, 1174].forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const noteStart = startAt + index * 0.13;
      oscillator.type = 'sine';
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, noteStart);
      gain.gain.exponentialRampToValueAtTime(0.16, noteStart + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.0001, noteStart + 0.19);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(noteStart);
      oscillator.stop(noteStart + 0.2);
    });
  }

  function flushPendingSounds() {
    if (!soundEnabled || !audioContext || audioContext.state !== 'running' || !pendingSounds) return;
    const queuedSounds = pendingSounds;
    pendingSounds = 0;
    for (let index = 0; index < queuedSounds; index += 1) {
      window.setTimeout(playNotificationSound, index * 320);
    }
  }

  function unlockAudio() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      audioContext = audioContext || new AudioContextClass();
      if (audioContext.state === 'suspended') {
        audioContext.resume().then(flushPendingSounds)
          .catch(error => console.warn('Bildirishnoma ovozi yoqilmadi.', error));
      } else {
        flushPendingSounds();
      }
    } catch (error) {
      console.warn('Bildirishnoma ovozi bu brauzerda ishlamaydi.', error);
    }
  }

  function updateSoundPreference(enabled) {
    soundEnabled = enabled;
    try {
      localStorage.setItem(soundStorageKey, enabled ? 'on' : 'off');
    } catch (error) {
      console.warn('Bildirishnoma ovozi sozlamasi saqlanmadi.', error);
    }
    updateSoundButton();
  }

  function emptyMessage() {
    if (!list.querySelector('.notification-item')) {
      const empty = document.createElement('p');
      empty.className = 'notification-empty';
      empty.textContent = 'Hozircha yangi bildirishnoma yo‘q';
      list.replaceChildren(empty);
    }
  }

  function addNotification(notification, showToast) {
    const empty = list.querySelector('.notification-empty');
    if (empty) empty.remove();

    const item = document.createElement('button');
    item.className = 'notification-item';
    item.type = 'button';
    item.dataset.notificationId = String(notification.id);

    const title = document.createElement('strong');
    title.textContent = notification.title;
    const message = document.createElement('span');
    message.textContent = notification.message;
    const time = document.createElement('time');
    time.textContent = new Date(notification.created_at).toLocaleString('uz-UZ');
    item.append(title, message, time);
    list.prepend(item);

    if (showToast) {
      const toast = document.createElement('div');
      toast.className = 'notification-toast';
      const icon = document.createElement('span');
      icon.className = 'notification-toast-icon';
      icon.innerHTML = '<i class="fas fa-bell"></i>';
      const content = document.createElement('div');
      content.className = 'notification-toast-content';
      const toastTitle = document.createElement('strong');
      toastTitle.textContent = notification.title;
      const toastMessage = document.createElement('span');
      toastMessage.textContent = notification.message;
      content.append(toastTitle, toastMessage);

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'notification-toast-close';
      closeBtn.setAttribute('aria-label', 'Yopish');
      closeBtn.innerHTML = '&times;';

      toast.append(icon, content, closeBtn);

      let dismissed = false;
      function dismissToast() {
        if (dismissed) return;
        dismissed = true;
        toast.classList.add('toast-hiding');
        setTimeout(() => toast.remove(), 250);
      }

      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dismissToast();
      });

      toast.addEventListener('click', () => {
        if (notification.url) {
          const target = new URL(notification.url, window.location.origin);
          if (target.origin === window.location.origin) window.location.assign(target.href);
        } else {
          dismissToast();
        }
      });

      toasts.append(toast);
      while (toasts.children.length > 4) toasts.firstElementChild.remove();
      window.setTimeout(dismissToast, 3200);
      playNotificationSound();

      if (document.hidden && 'Notification' in window && window.Notification.permission === 'granted') {
        try {
          const desktopNotification = new window.Notification(notification.title, {
            body: notification.message,
            tag: `sargetcrm-notification-${notification.id}`,
          });
          desktopNotification.onclick = () => {
            window.focus();
            bell.click();
            desktopNotification.close();
          };
        } catch (error) {
          console.warn('Brauzer bildirishnomani ko‘rsata olmadi.', error);
        }
      }
    }
  }

  const clearButton = document.getElementById('notificationClearAll');
  if (clearButton) {
    clearButton.addEventListener('click', async (e) => {
      e.stopPropagation();
      clearButton.disabled = true;
      status.hidden = true;
      const csrfCookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
      const csrf = csrfCookie ? csrfCookie.split('=')[1] : '';
      try {
        const response = await fetch(center.dataset.clearUrl || '/api/notifications/clear-all/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Accept': 'application/json',
            ...(csrf ? { 'X-CSRFToken': decodeURIComponent(csrf) } : {})
          },
        });
        if (!response.ok) throw new Error("Bildirishnomalarni tozalab bo'lmadi");
        const data = await response.json();
        list.replaceChildren();
        emptyMessage();
        updateCount(data.unread_count);
        status.textContent = "Qo'ng'iroqcha tozalandi. Barcha bildirishnomalar tarixda saqlandi.";
        status.hidden = false;
        setTimeout(() => { status.hidden = true; }, 2500);
      } catch (err) {
        status.textContent = "Xatolik: bildirishnomalar o'qilgan deb belgilanmadi.";
        status.hidden = false;
      } finally {
        clearButton.disabled = false;
      }
    });
  }

  updateSoundButton();
  document.addEventListener('pointerdown', unlockAudio, { once: true });
  document.addEventListener('keydown', unlockAudio, { once: true });

  soundButton.addEventListener('click', () => {
    updateSoundPreference(!soundEnabled);
    if (soundEnabled) {
      unlockAudio();
      playNotificationSound();
    } else {
      pendingSounds = 0;
    }
  });

  bell.addEventListener('click', () => {
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    bell.setAttribute('aria-expanded', String(willOpen));
  });

  document.addEventListener('click', event => {
    if (!center.contains(event.target)) {
      panel.hidden = true;
      bell.setAttribute('aria-expanded', 'false');
    }
  });

  list.addEventListener('click', async event => {
    const item = event.target.closest('.notification-item');
    if (!item) return;
    const id = item.dataset.notificationId;
    if (item.disabled) return;
    item.disabled = true;
    status.hidden = true;
    const csrfCookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
    const csrf = csrfCookie ? csrfCookie.split('=')[1] : '';
    try {
      const response = await fetch(`${center.dataset.readUrlPrefix}${id}/read/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: csrf ? { 'X-CSRFToken': decodeURIComponent(csrf) } : {},
      });
      if (!response.ok) throw new Error('Bildirishnomani o‘qilgan deb belgilab bo‘lmadi');
      const data = await response.json();
      item.remove();
      updateCount(data.unread_count);
      emptyMessage();
      if (data.url) {
        const target = new URL(data.url, window.location.origin);
        if (target.origin === window.location.origin) window.location.assign(target.href);
      }
    } catch (error) {
      status.textContent = "Bildirishnoma ochilmadi. Qayta urinib ko'ring.";
      status.hidden = false;
    } finally {
      if (item.isConnected) item.disabled = false;
    }
  });

  async function poll() {
    if (polling || document.hidden) return;
    polling = true;
    try {
      const response = await fetch(`${center.dataset.pollUrl}?after=${cursor}`, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
      if (!response.ok) throw new Error('Bildirishnomalarni tekshirib bo‘lmadi');
      const data = await response.json();
      data.notifications.forEach(notification => {
        cursor = Math.max(cursor, notification.id);
        addNotification(notification, true);
      });
      try {
        sessionStorage.setItem(cursorStorageKey, String(cursor));
      } catch (error) {
        console.warn('Bildirishnoma holati bu brauzerda saqlanmadi.', error);
      }
      updateCount(data.unread_count);
    } catch (error) {
      console.error(error);
    } finally {
      polling = false;
    }
  }

  poll();
  window.setInterval(poll, 15000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) poll();
  });
}

// ── Select2 ──────────────────────────────────────────────────────
function initSelect2() {
  if (typeof $ === 'undefined' || typeof $.fn.select2 === 'undefined') return;

  $('.select2').select2({
    language: {
      noResults: () => "Natija topilmadi",
      searching: () => "Qidirilmoqda...",
      inputTooShort: (args) => `Kamida ${args.minimum - args.input.length} ta belgi kiriting`,
    },
    allowClear: true,
    width: '100%',
  });

  // Special AJAX search for student select
  const $studentSelect = $('select[name="student"].select2');
  if ($studentSelect.length) {
    $studentSelect.select2({
      language: { noResults: () => "O'quvchi topilmadi", searching: () => "Qidirilmoqda..." },
      allowClear: true,
      placeholder: "O'quvchi tanlang...",
      width: '100%',
      minimumInputLength: 0,
    });
  }
}

// ── Number formatter ─────────────────────────────────────────────
function formatNumber(n) {
  return new Intl.NumberFormat('uz-UZ').format(n);
}

// Format all .amount elements
function formatAmounts() {
  document.querySelectorAll('[data-amount]').forEach(el => {
    const val = parseFloat(el.dataset.amount);
    if (!isNaN(val)) el.textContent = formatNumber(val) + " so'm";
  });
}

function initPercentBars() {
  document.querySelectorAll('.percent-bar[data-percent]').forEach(el => {
    const value = Math.max(0, Math.min(100, parseFloat(el.dataset.percent) || 0));
    el.style.setProperty('--percent', value + '%');
  });
}

// ── Dashboard Chart (Chart.js) ────────────────────────────────────
function initDashboardChart() {
  const canvas = document.getElementById('incomeChart');
  if (!canvas || typeof Chart === 'undefined') return;

  const rawData = JSON.parse(document.getElementById(canvas.dataset.source).textContent);
  const labels = rawData.map(d => d.month);
  const incomes = rawData.map(d => d.income);
  const expenses = rawData.map(d => d.expense);

  const isLight = document.body.classList.contains('light-mode');
  const gridColor = isLight ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.05)';
  const tickColor = isLight ? '#94a3b8' : '#4b5879';

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Daromad',
          data: incomes,
          backgroundColor: 'rgba(245,166,35,0.7)',
          borderColor: 'rgba(245,166,35,1)',
          borderWidth: 1, borderRadius: 6,
        },
        {
          label: 'Xarajat',
          data: expenses,
          backgroundColor: 'rgba(239,68,68,0.45)',
          borderColor: 'rgba(239,68,68,0.8)',
          borderWidth: 1, borderRadius: 6,
        },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: tickColor, font: { family: "'DM Sans', sans-serif", size: 12 } } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${formatNumber(ctx.raw)} so'm`,
          }
        }
      },
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: tickColor } },
        y: { grid: { color: gridColor }, ticks: { color: tickColor, callback: v => formatNumber(v) } },
      }
    }
  });
}

// ── Reports Charts ────────────────────────────────────────────────
function initReportCharts() {
  // Monthly income/expense line chart
  const canvas = document.getElementById('reportChart');
  if (canvas && typeof Chart !== 'undefined') {
    const raw = JSON.parse(document.getElementById(canvas.dataset.source).textContent);
    const isLight = document.body.classList.contains('light-mode');
    const gridColor = isLight ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.05)';
    const tickColor = isLight ? '#94a3b8' : '#4b5879';

    new Chart(canvas, {
      type: 'line',
      data: {
        labels: raw.map(d => d.month),
        datasets: [
          {
            label: 'Daromad', data: raw.map(d => d.income),
            borderColor: '#f5a623', backgroundColor: 'rgba(245,166,35,0.1)',
            fill: true, tension: 0.4, pointRadius: 4,
          },
          {
            label: 'Xarajat', data: raw.map(d => d.expense),
            borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.07)',
            fill: true, tension: 0.4, pointRadius: 4,
          },
          {
            label: 'Foyda', data: raw.map(d => d.net),
            borderColor: '#22c55e', backgroundColor: 'transparent',
            fill: false, tension: 0.4, pointRadius: 4, borderDash: [4,3],
          },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: tickColor } }, tooltip: { callbacks: { label: ctx => ` ${formatNumber(ctx.raw)} so'm` } } },
        scales: { x: { grid: { color: gridColor }, ticks: { color: tickColor } }, y: { grid: { color: gridColor }, ticks: { color: tickColor, callback: v => formatNumber(v) } } }
      }
    });
  }

  // Attendance donut
  const attCanvas = document.getElementById('attendanceChart');
  if (attCanvas && typeof Chart !== 'undefined') {
    const data = JSON.parse(attCanvas.dataset.chart || '{}');
    new Chart(attCanvas, {
      type: 'doughnut',
      data: {
        labels: ['Keldi', 'Kechikdi', 'Kelmadi'],
        datasets: [{ data: [data.present||0, data.late||0, data.absent||0], backgroundColor: ['#22c55e','#f97316','#ef4444'], borderWidth: 0, hoverOffset: 8 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '65%',
        plugins: { legend: { position: 'bottom', labels: { color: document.body.classList.contains('light-mode') ? '#475569' : '#94a3b8', padding: 16 } } }
      }
    });
  }
}

// ── Confirm Delete ────────────────────────────────────────────────
function initConfirmDelete() {
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', e => {
      if (!confirm(el.dataset.confirm || "Ishonchingiz komilmi?")) {
        e.preventDefault();
      }
    });
  });
}

// ── Payment form: auto-fill amount from group fee ─────────────────
function initPaymentForm() {
  const studentSelect = document.querySelector('select[name="student"]');
  const amountInput = document.querySelector('input[name="amount"]');
  if (!studentSelect || !amountInput) return;

  studentSelect.addEventListener('change', function () {
    const option = this.options[this.selectedIndex];
    const fee = option.dataset.fee;
    if (fee && !amountInput.value) {
      amountInput.value = fee;
    }
  });
}

// ── Bulk attendance toggle ────────────────────────────────────────
function initAttendanceQuick() {
  const btnAll = document.getElementById('markAllPresent');
  if (btnAll) {
    btnAll.addEventListener('click', () => {
      document.querySelectorAll('.att-option.present input[type="radio"]').forEach(radio => {
        radio.checked = true;
        radio.dispatchEvent(new Event('change'));
      });
    });
  }
}

// ── Salary month auto-select ──────────────────────────────────────
function initSalaryMonth() {
  const monthInput = document.querySelector('input[name="month"][type="month"]');
  if (monthInput && !monthInput.value) {
    const today = new Date();
    monthInput.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  }
}

function initLeadStatusForms() {
  document.querySelectorAll('.lead-status-form').forEach(form => {
    const status = form.querySelector('[name="status"]');
    const followUpField = form.querySelector('.lead-follow-up-field');
    const followUpInput = form.querySelector('.lead-follow-up-input');
    if (!status || !followUpField || !followUpInput) return;

    const updateFollowUpField = () => {
      const callbackSelected = status.value === 'callback';
      followUpField.hidden = !callbackSelected;
      followUpInput.required = callbackSelected;
    };

    status.addEventListener('change', updateFollowUpField);
    updateFollowUpField();
  });
}

// ── Keyboard shortcuts ────────────────────────────────────────────
function initShortcuts() {
  document.addEventListener('keydown', e => {
    // Ctrl/Cmd + / → focus search
    if ((e.ctrlKey || e.metaKey) && e.key === '/') {
      const search = document.querySelector('.search-group input');
      if (search) { e.preventDefault(); search.focus(); }
    }
  });
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSidebar();
  initAlerts();
  initNotifications();
  initSelect2();
  formatAmounts();
  initPercentBars();
  initDashboardChart();
  initReportCharts();
  initConfirmDelete();
  initPaymentForm();
  initAttendanceQuick();
  initSalaryMonth();
  initLeadStatusForms();
  initShortcuts();

  // Theme toggle buttons (can be multiple, e.g., sidebar + global)
  document.querySelectorAll('.theme-toggle').forEach(btn => btn.addEventListener('click', toggleTheme));
});

// Export for inline use
window.toggleTheme = toggleTheme;
window.formatNumber = formatNumber;
