import './local-assets.js';
import React from 'react';
import {createRoot} from 'react-dom/client';
import {Excalidraw,MainMenu,serializeAsJSON,loadFromBlob} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
import {createSceneTracker} from './scene-tracker.js';

let api=null,current='',composing=false,generation=0,pending=false,timer=null;
const tracker=createSceneTracker(),root=createRoot(document.getElementById('root'));
const post=(type,extra={})=>parent.postMessage({type,...extra},location.origin);
const elements=()=>api?.getSceneElementsIncludingDeleted?.() || api?.getSceneElements() || [];
const cancel=()=>{if(timer!==null){clearTimeout(timer);timer=null;}};
function flush() {
  if(!api||composing)return current;
  if(tracker.changed(elements(),api.getAppState(),api.getFiles()))pending=true;
  cancel();
  if(pending){current=serializeAsJSON(elements(),api.getAppState(),api.getFiles(),'local');pending=false;post('yingxu-canvas-change',{value:current});}
  return current;
}
function schedule() {if(!composing&&timer===null)timer=setTimeout(()=>{timer=null;flush();},120);}
window.yingxuCanvas={getValue:flush,isComposing:()=>composing,setActive:value=>window.yingxuCanvasFrames.setActive(value)};
document.addEventListener('compositionstart',()=>{composing=true;cancel();},true);
document.addEventListener('compositionend',()=>{composing=false;if(pending)schedule();},true);
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();if(!composing){flush();post('yingxu-canvas-save');}}},true);
window.addEventListener('pagehide',()=>{if(!composing)flush();cancel();});
window.addEventListener('message',async event=>{
  if(event.origin!==location.origin||event.source!==parent||event.data?.type!=='yingxu-canvas-load')return;
  const seq=++generation;
  try {
    const value=event.data.value;
    const scene=await loadFromBlob(new Blob([value],{type:'application/json'}),null,null);
    if(seq!==generation)return;
    cancel();current=value;api=null;pending=false;tracker.reset();
    root.render(<Excalidraw key={seq} initialData={{...scene,scrollToContent:true}} langCode="zh-CN"
      excalidrawAPI={value=>{api=value;}}
      onChange={(elements,state,files)=>{if(tracker.changed(elements,state,files)){pending=true;schedule();}}}
      validateEmbeddable={false} onLinkOpen={(element,event)=>event.preventDefault()}
      UIOptions={{canvasActions:{loadScene:false,saveToActiveFile:false,export:false,saveAsImage:false,toggleTheme:false}}}
    ><MainMenu><MainMenu.DefaultItems.ClearCanvas/><MainMenu.DefaultItems.ChangeCanvasBackground/></MainMenu></Excalidraw>);
  } catch(error){post('yingxu-canvas-error',{message:'画板载入失败：'+error.message});}
});
post('yingxu-canvas-ready');
