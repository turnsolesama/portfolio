/* Resource-only marquee. Geometry is cached per gesture; idle schedules no work. */
(() => {
  'use strict';
  const clamp = (n,min,max) => Math.max(min,Math.min(max,n));
  const intersects = (a,b) => a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top;
  function selection(base,hits,mode) {
    const next = new Set(mode === 'replace' ? [] : base);
    for (const id of hits) { if (mode === 'toggle' && base.has(id)) next.delete(id); else next.add(id); }
    return next;
  }
  function install({viewport,getItems,getSelection,onChange,onStart = () => {},enabled = () => true,getContext = () => ''}) {
    if (!viewport) return null;
    const doc = viewport.ownerDocument, win = doc.defaultView;
    const blocked = '[data-item],[data-resource-group],[data-folder-open],button,a,input,textarea,select,label,[contenteditable],[role="button"],[role="tab"],[draggable="true"]';
    let gesture = null, frame = 0, suppressClick = false;
    const subscriptions = [];
    const on = (node,type,fn,opts) => { node.addEventListener(type,fn,opts); subscriptions.push(() => node.removeEventListener(type,fn,opts)); };
    function bounds() { const r = viewport.getBoundingClientRect(); return {left:r.left+viewport.clientLeft,top:r.top+viewport.clientTop,right:r.left+viewport.clientLeft+viewport.clientWidth,bottom:r.top+viewport.clientTop+viewport.clientHeight}; }
    function same(a,b) { return a.size === b.size && [...a].every(id => b.has(id)); }
    function apply(next) { if (!same(next,getSelection())) onChange(next); }
    function finish(restore = false) {
      const g = gesture; gesture = null;
      if (frame) win.cancelAnimationFrame(frame); frame = 0;
      if (!g) return;
      g.box?.remove(); viewport.classList.remove('yx-marquee-active');
      if (viewport.hasPointerCapture?.(g.pointerId)) viewport.releasePointerCapture(g.pointerId);
      if (restore && getContext() === g.context) apply(g.base);
      suppressClick = g.started;
    }
    function schedule() { if (gesture && !frame) frame = win.requestAnimationFrame(paint); }
    function paint() {
      frame = 0; const g = gesture;
      if (!g || !g.started) return;
      if (!enabled() || getContext() !== g.context || g.items.some(item => !viewport.contains(item.node))) { finish(); return; }
      const b = bounds(), x = clamp(g.x,b.left,b.right), y = clamp(g.y,b.top,b.bottom);
      const current = {x:x-b.left+viewport.scrollLeft,y:y-b.top+viewport.scrollTop};
      const rect = {left:Math.min(g.start.x,current.x),right:Math.max(g.start.x,current.x),top:Math.min(g.start.y,current.y),bottom:Math.max(g.start.y,current.y)};
      const hits = g.items.filter(item => !item.node.hidden && !item.node.hasAttribute('data-yx-group-hidden') && intersects(rect,item.rect)).map(item => item.id);
      apply(selection(g.base,hits,g.mode));
      const left = clamp(b.left+rect.left-viewport.scrollLeft,b.left,b.right),top = clamp(b.top+rect.top-viewport.scrollTop,b.top,b.bottom);
      Object.assign(g.box.style,{left:`${left}px`,top:`${top}px`,width:`${Math.max(0,clamp(b.left+rect.right-viewport.scrollLeft,b.left,b.right)-left)}px`,height:`${Math.max(0,clamp(b.top+rect.bottom-viewport.scrollTop,b.top,b.bottom)-top)}px`});
      // Reduced motion disables automatic scrolling; manual wheel/scroll remains available.
      if (!win.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
        const step = (value,min,max) => value < min+28 ? -12 : value > max-28 ? 12 : 0;
        const beforeX = viewport.scrollLeft,beforeY = viewport.scrollTop;
        viewport.scrollLeft += step(g.x,b.left,b.right); viewport.scrollTop += step(g.y,b.top,b.bottom);
        if (beforeX !== viewport.scrollLeft || beforeY !== viewport.scrollTop) schedule();
      }
    }
    on(viewport,'pointerdown',event => {
      suppressClick = false;
      if (gesture || !enabled() || event.button !== 0 || (event.pointerType && event.pointerType !== 'mouse') || event.target.closest(blocked)) return;
      const b = bounds(); if (event.clientX < b.left || event.clientX >= b.right || event.clientY < b.top || event.clientY >= b.bottom) return;
      const items = [...getItems()].filter(node => !node.hidden && !node.hasAttribute('data-yx-group-hidden') && node.getClientRects().length).map(node => {
        const r = node.getBoundingClientRect(); return {node,id:String(node.dataset.item),rect:{left:r.left-b.left+viewport.scrollLeft,right:r.right-b.left+viewport.scrollLeft,top:r.top-b.top+viewport.scrollTop,bottom:r.bottom-b.top+viewport.scrollTop}};
      });
      if (!items.length) return;
      gesture = {pointerId:event.pointerId,context:getContext(),items,base:new Set(getSelection()),mode:event.shiftKey ? 'add' : event.ctrlKey || event.metaKey ? 'toggle' : 'replace',start:{x:event.clientX-b.left+viewport.scrollLeft,y:event.clientY-b.top+viewport.scrollTop},downX:event.clientX,downY:event.clientY,x:event.clientX,y:event.clientY,started:false,box:null};
      event.preventDefault(); viewport.setPointerCapture(event.pointerId);
    });
    on(viewport,'pointermove',event => {
      const g = gesture; if (!g || event.pointerId !== g.pointerId) return;
      g.x = event.clientX; g.y = event.clientY;
      if (!g.started && Math.hypot(g.x-g.downX,g.y-g.downY) >= 4) {
        onStart();
        g.started = true; g.box = doc.createElement('div'); g.box.className = 'yx-marquee-box'; g.box.setAttribute('aria-hidden','true'); doc.body.append(g.box); viewport.classList.add('yx-marquee-active');
      }
      if (g.started) { event.preventDefault(); schedule(); }
    });
    on(viewport,'pointerup',event => { if (gesture?.pointerId === event.pointerId) { gesture.x = event.clientX; gesture.y = event.clientY; if (frame) win.cancelAnimationFrame(frame); frame = 0; paint(); finish(); } });
    on(viewport,'pointercancel',event => { if (gesture?.pointerId === event.pointerId) finish(true); });
    on(viewport,'lostpointercapture',event => { if (gesture?.pointerId === event.pointerId) finish(true); });
    on(viewport,'scroll',schedule,{passive:true});
    on(viewport,'click',event => { if (suppressClick) { suppressClick = false; event.preventDefault(); event.stopImmediatePropagation(); } },true);
    on(doc,'keydown',event => { if (gesture && event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); finish(true); } },true);
    on(win,'blur',() => finish(true)); on(win,'resize',() => finish(true));
    return {cancel:() => finish(true),destroy:() => { finish(true); subscriptions.forEach(off => off()); }};
  }
  window.YingXuMarquee = {install,selection,intersects};
})();
