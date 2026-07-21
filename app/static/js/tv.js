/**
 * tv.js — Smart TV display helpers.
 * Auto-refresh, font scaling for 15-ft readability, and optional class rotation.
 */

(function () {
  'use strict';

  const REFRESH_SECONDS = parseInt(
    document.documentElement.dataset.tvRefresh || '300', 10
  );

  /** ── Auto Refresh ── */
  function initAutoRefresh() {
    if (!REFRESH_SECONDS) return;

    // Countdown timer display
    const counter = document.getElementById('tv-refresh-counter');
    let remaining = REFRESH_SECONDS;

    const tick = setInterval(() => {
      remaining -= 1;
      if (counter) counter.textContent = remaining + 's';
      if (remaining <= 0) {
        clearInterval(tick);
        window.location.reload();
      }
    }, 1000);

    console.log(`[TV] Auto-refresh in ${REFRESH_SECONDS}s`);
  }

  /** ── Viewport Font Scaling ── */
  function scaleForTV() {
    // Target: 1920×1080 or higher — use vw-based scaling
    const vw = window.innerWidth;
    const scale = Math.max(1, vw / 1280);
    document.documentElement.style.setProperty('--tv-scale', scale.toFixed(2));
    console.log(`[TV] Scale factor: ${scale.toFixed(2)} (viewport: ${vw}px)`);
  }

  /** ── Fullscreen toggle ── */
  function initFullscreen() {
    const btn = document.getElementById('tv-fullscreen-btn');
    if (!btn) return;

    btn.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(err => {
          console.warn('[TV] Fullscreen error:', err);
        });
        btn.textContent = '⛶ Exit Fullscreen';
      } else {
        document.exitFullscreen();
        btn.textContent = '⛶ Fullscreen';
      }
    });
  }

  /** ── Chart.js Radar Chart ── */
  function initPillarRadar() {
    const canvas = document.getElementById('pillar-radar-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = JSON.parse(canvas.dataset.labels || '[]');
    const initialValues = JSON.parse(canvas.dataset.values || '[]');
    const classLabel = canvas.dataset.classLabel || '';
    const subjectRadarData = JSON.parse(canvas.dataset.subjectRadar || '{}');

    // Database keys mapping
    const pillarKeys = [
      'english_speaking', 'mathematics', 'reasoning', 'reading', 'writing'
    ];

    const chart = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: labels,
        datasets: [{
          label: classLabel,
          data: initialValues,
          backgroundColor: 'rgba(99,102,241,0.2)',
          borderColor: 'rgba(99,102,241,1)',
          borderWidth: 3,
          pointBackgroundColor: '#a5b4fc',
          pointRadius: 6,
          pointHoverRadius: 9,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            labels: {
              color: '#e2e8f0',
              font: { size: 18, family: 'Inter', weight: '600' },
            }
          },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${ctx.raw}%`
            }
          }
        },
        scales: {
          r: {
            beginAtZero: true,
            max: 100,
            ticks: {
              color: '#94a3b8',
              font: { size: 14 },
              stepSize: 20,
              backdropColor: 'transparent',
            },
            grid: { color: 'rgba(148,163,184,0.2)' },
            angleLines: { color: 'rgba(148,163,184,0.2)' },
            pointLabels: {
              color: '#e2e8f0',
              font: { size: 20, family: 'Poppins', weight: '700' },
            }
          }
        }
      }
    });

    const select = document.getElementById('tv-subject-select');
    if (select) {
      select.addEventListener('change', function () {
        const val = this.value;
        let newValues = [];
        if (val === 'All') {
          newValues = initialValues;
        } else {
          const sData = subjectRadarData[val] || {};
          newValues = pillarKeys.map(k => sData[k] || 0);
        }
        chart.data.datasets[0].data = newValues;
        chart.data.datasets[0].label = val === 'All' ? classLabel : `${classLabel} — ${val}`;
        chart.update();
      });
    }
  }

  /** ── Bar Chart for Attendance ── */
  function initAttendanceBar() {
    const canvas = document.getElementById('attendance-bar-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels  = JSON.parse(canvas.dataset.labels || '[]');
    const present = JSON.parse(canvas.dataset.present || '[]');
    const absent  = JSON.parse(canvas.dataset.absent  || '[]');

    new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Present',
            data: present,
            backgroundColor: 'rgba(16,185,129,0.8)',
            borderRadius: 8,
          },
          {
            label: 'Absent',
            data: absent,
            backgroundColor: 'rgba(244,63,94,0.8)',
            borderRadius: 8,
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: { color: '#e2e8f0', font: { size: 16, family: 'Inter' } }
          }
        },
        scales: {
          x: { ticks: { color: '#94a3b8', font: { size: 14 } }, grid: { display: false } },
          y: { ticks: { color: '#94a3b8', font: { size: 14 } }, grid: { color: 'rgba(148,163,184,0.1)' }, beginAtZero: true },
        }
      }
    });
  }

  /** ── Init ── */
  function init() {
    scaleForTV();
    initAutoRefresh();
    initFullscreen();
    initPillarRadar();
    initAttendanceBar();
    window.addEventListener('resize', scaleForTV);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
