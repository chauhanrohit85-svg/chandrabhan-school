/**
 * sync.js — Offline → Online data synchronization.
 * Polls /api/health every 30s (uses navigator.onLine as fast path).
 * When connectivity is restored, flushes any queued localStorage payloads
 * to the server via /api/sync/* endpoints.
 */

(function () {
  'use strict';

  const POLL_INTERVAL_MS = 30000;
  const SYNC_QUEUE_KEY = 'sync_queue';
  const SYNC_ENDPOINTS = {
    log:        '/api/sync/log',
    attendance: '/api/sync/attendance',
    pillars:    '/api/sync/pillars',
  };

  let isOnline = navigator.onLine;
  let syncInProgress = false;

  /** Update online status indicator in the UI */
  function updateStatusUI(online) {
    const indicator = document.getElementById('online-status');
    if (!indicator) return;
    indicator.className = `online-badge ${online ? 'online' : 'offline'}`;
    indicator.textContent = online ? '● Online' : '○ Offline';
  }

  /** Add an item to the sync queue in localStorage */
  function enqueue(type, payload) {
    if (!SYNC_ENDPOINTS[type]) {
      console.warn('[Sync] Unknown sync type:', type);
      return;
    }
    let queue = getQueue();
    queue.push({ type, payload, queued_at: new Date().toISOString() });
    localStorage.setItem(SYNC_QUEUE_KEY, JSON.stringify(queue));
    console.log(`[Sync] Queued ${type} payload. Queue size: ${queue.length}`);
  }

  /** Get current sync queue */
  function getQueue() {
    try {
      return JSON.parse(localStorage.getItem(SYNC_QUEUE_KEY) || '[]');
    } catch (e) {
      return [];
    }
  }

  /** Check connectivity via /api/health */
  async function checkHealth() {
    try {
      const resp = await fetch('/api/health', {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  /** Flush all queued items to server */
  async function flushQueue() {
    if (syncInProgress) return;
    const queue = getQueue();
    if (!queue.length) return;

    syncInProgress = true;
    console.log(`[Sync] Flushing ${queue.length} queued item(s)…`);

    const remaining = [];
    for (const item of queue) {
      const endpoint = SYNC_ENDPOINTS[item.type];
      try {
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item.payload),
          signal: AbortSignal.timeout(10000),
        });

        if (resp.ok) {
          console.log(`[Sync] ✓ Synced ${item.type}`);
        } else {
          console.warn(`[Sync] Server rejected ${item.type}:`, resp.status);
          remaining.push(item);
        }
      } catch (err) {
        console.warn(`[Sync] Network error for ${item.type}:`, err.message);
        remaining.push(item);
      }
    }

    // Put back only failed items
    localStorage.setItem(SYNC_QUEUE_KEY, JSON.stringify(remaining));
    syncInProgress = false;

    if (remaining.length === 0) {
      console.log('[Sync] All queued items synced successfully.');
      showSyncSuccess();
    }
  }

  /** Show a brief sync success toast */
  function showSyncSuccess() {
    const toast = document.getElementById('sync-toast');
    if (!toast) return;
    toast.style.display = 'flex';
    toast.textContent = '✓ Offline data synced';
    setTimeout(() => { toast.style.display = 'none'; }, 4000);
  }

  /** Main polling loop */
  async function poll() {
    const online = navigator.onLine && await checkHealth();

    if (online !== isOnline) {
      isOnline = online;
      updateStatusUI(online);
      if (online) {
        console.log('[Sync] Connectivity restored. Flushing queue…');
        await flushQueue();
      } else {
        console.log('[Sync] Connectivity lost. Switching to offline mode.');
      }
    } else if (online && getQueue().length > 0) {
      await flushQueue();
    }
  }

  /** Expose enqueue globally so forms can call sync.enqueue('log', {...}) */
  window.SchoolSync = { enqueue, getQueue, flushQueue };

  /** Init */
  function init() {
    updateStatusUI(isOnline);

    // Browser events
    window.addEventListener('online',  () => { poll(); });
    window.addEventListener('offline', () => { isOnline = false; updateStatusUI(false); });

    // Poll every 30 seconds
    setInterval(poll, POLL_INTERVAL_MS);

    // Initial check
    setTimeout(poll, 2000);

    console.log('[Sync] Initialized. Polling every 30s.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
