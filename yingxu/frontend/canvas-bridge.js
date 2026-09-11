/* Local iframe ownership: mount once, hide between tabs, destroy on close. */
window.YingXuCanvas = {create({value,onChange,onError,onSave}) {
  const frame=document.createElement('iframe');frame.src='/canvas/index.html';frame.title='Excalidraw 画板';
  let current=value,ready=false,destroyed=false,active=true,host=null;
  const send=()=>{if(!destroyed&&ready)frame.contentWindow?.postMessage({type:'yingxu-canvas-load',value:current},location.origin);};
  const receive=event=>{
    if(destroyed||event.origin!==location.origin||event.source!==frame.contentWindow)return;
    if(event.data?.type==='yingxu-canvas-ready'){ready=true;frame.contentWindow?.yingxuCanvas?.setActive(active);send();}
    if(event.data?.type==='yingxu-canvas-change'&&typeof event.data.value==='string'){current=event.data.value;onChange(current);}
    if(event.data?.type==='yingxu-canvas-error')onError(new Error(String(event.data.message)));
    if(event.data?.type==='yingxu-canvas-save')onSave();
  };
  const getValue=()=>{if(!destroyed){const latest=frame.contentWindow?.yingxuCanvas?.getValue();if(typeof latest==='string')current=latest;}return current;};
  window.addEventListener('message',receive);
  return {
    mount(parent){
      if(destroyed)throw new Error('画板已经关闭。');
      if(host&&host!==parent)throw new Error('画板需要保留原显示容器，不能通过搬动窗口切换标签。');
      if(!host){host=parent;host.hidden=!active;parent.appendChild(frame);}
    },
    setActive(value){active=!!value;if(!active)getValue();frame.contentWindow?.yingxuCanvas?.setActive(active);frame.hidden=!active;if(host)host.hidden=!active;frame.setAttribute('aria-hidden',String(!active));},
    setValue(value){if(value!==current){current=value;send();}},
    getValue,
    isComposing(){return !destroyed&&!!frame.contentWindow?.yingxuCanvas?.isComposing();},
    destroy(){if(destroyed)return;destroyed=true;ready=false;window.removeEventListener('message',receive);frame.remove();host=null;}
  };
}};
