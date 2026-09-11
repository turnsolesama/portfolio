/* The editor is lazy-loaded in a local iframe and retained while its tab is open. */
window.YingXuCanvas = {create({value,onChange,onError,onSave}) {
  const frame=document.createElement('iframe');frame.src='/canvas/index.html';frame.title='Excalidraw 画板';
  let current=value,ready=false;
  const send=()=>frame.contentWindow?.postMessage({type:'yingxu-canvas-load',value:current},location.origin);
  const receive=event=>{
    if(event.origin!==location.origin || event.source!==frame.contentWindow)return;
    if(event.data?.type==='yingxu-canvas-ready'){ready=true;send();}
    if(event.data?.type==='yingxu-canvas-change' && typeof event.data.value==='string'){current=event.data.value;onChange(current);}
    if(event.data?.type==='yingxu-canvas-error')onError(new Error(String(event.data.message)));
    if(event.data?.type==='yingxu-canvas-save')onSave();
  };
  window.addEventListener('message',receive);
  return {
    mount(parent){if(frame.parentNode!==parent)parent.appendChild(frame);},
    setValue(value){if(value!==current){current=value;if(ready)send();}},
    getValue(){return frame.contentWindow?.yingxuCanvas?.getValue() || current;},
    isComposing(){return !!frame.contentWindow?.yingxuCanvas?.isComposing();},
    destroy(){window.removeEventListener('message',receive);frame.remove();}
  };
}};
