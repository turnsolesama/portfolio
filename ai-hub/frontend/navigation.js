/* In-window navigation history. Snapshots stay in memory, never in persistent storage. */
((root, factory) => {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AIHubNavigation = factory();
})(globalThis, () => {
  'use strict';

  function create({ history, location, capture, render, update }) {
    const session = `${Date.now()}-${Math.random()}`;
    let entries = [], index = -1, serial = 0, pending = false;
    const currentHash = () => location.hash || '#/overview';
    const status = () => ({
      canBack: index > 0 && !pending,
      canForward: index < entries.length - 1 && !pending,
      previous: entries[index - 1] || null,
    });
    const notify = () => update(status());
    const save = () => { if (index >= 0) entries[index].snapshot = capture(); };
    const marker = entry => ({ aiHubNavigation: { session, id: entry.id } });
    const show = () => { notify(); return render(entries[index].hash, entries[index].snapshot); };

    function start() {
      entries = [{ id: ++serial, hash: currentHash(), snapshot: null }];
      index = 0; pending = false;
      history.replaceState(marker(entries[0]), '', entries[0].hash);
      return show();
    }
    function navigate(hash, { force = false } = {}) {
      if (pending || !/^#\//.test(hash)) return;
      if (hash === entries[index]?.hash && !force) return refresh();
      save();
      const entry = { id: ++serial, hash, snapshot: null };
      history.pushState(marker(entry), '', hash);
      entries.splice(index + 1);
      entries.push(entry); index++;
      return show();
    }
    function refresh() {
      if (pending) return;
      save();
      return show();
    }
    function travel(delta) {
      if (pending || index + delta < 0 || index + delta >= entries.length) return false;
      pending = true; notify();
      history.go(delta);
      return true;
    }
    function sync() {
      const state = history.state?.aiHubNavigation;
      const target = state?.session === session
        ? entries.findIndex(entry => entry.id === state.id && entry.hash === currentHash()) : -1;
      // A fresh/deep link or a history entry from before this window session starts a new trail.
      // Never enable our Back button using history.length, which can include external pages.
      if (target < 0) return start();
      if (target === index) return; // popstate and hashchange can describe the same traversal.
      save(); index = target; pending = false;
      return show();
    }
    return { start, navigate, refresh, sync, back: () => travel(-1), forward: () => travel(1), status };
  }
  return { create };
});
