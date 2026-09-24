(function () {
  'use strict';

  // Log out after 30 minutes without user interaction.
  var IDLE_LIMIT = 30 * 60 * 1000;
  // Log out after the app remains in the background for 15 minutes.
  var BACKGROUND_LIMIT = 15 * 60 * 1000;
  var HIDDEN_KEY = 'cc_hidden_since';
  var idleTimer = null;
  var backgroundTimer = null;

  function logout() {
    location.replace('/auto-logout');
  }

  function clearHiddenMark() {
    try { sessionStorage.removeItem(HIDDEN_KEY); } catch (e) {}
  }

  function startIdleTimer() {
    clearTimeout(idleTimer);
    if (!document.hidden) {
      idleTimer = setTimeout(logout, IDLE_LIMIT);
    }
  }

  function markBackground() {
    try { sessionStorage.setItem(HIDDEN_KEY, String(Date.now())); } catch (e) {}
    clearTimeout(backgroundTimer);
    backgroundTimer = setTimeout(logout, BACKGROUND_LIMIT);
  }

  function checkBackgroundExpiry() {
    var hiddenAt = 0;
    try { hiddenAt = Number(sessionStorage.getItem(HIDDEN_KEY) || 0); } catch (e) {}
    if (hiddenAt && Date.now() - hiddenAt >= BACKGROUND_LIMIT) {
      logout();
      return true;
    }
    return false;
  }

  // Actual user interaction resets the 30-minute inactivity countdown.
  ['pointerdown', 'keydown', 'touchstart', 'click', 'input', 'scroll'].forEach(function (eventName) {
    document.addEventListener(eventName, startIdleTimer, { passive: true });
  });

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      markBackground();
    } else {
      if (checkBackgroundExpiry()) return;
      clearTimeout(backgroundTimer);
      backgroundTimer = null;
      clearHiddenMark();
      startIdleTimer();
    }
  });

  window.addEventListener('pagehide', markBackground);
  window.addEventListener('pageshow', function () {
    if (checkBackgroundExpiry()) return;
    if (!document.hidden) {
      clearTimeout(backgroundTimer);
      backgroundTimer = null;
      clearHiddenMark();
      startIdleTimer();
    }
  });

  startIdleTimer();
})();
