import React from 'react';
import {createRoot} from 'react-dom/client';
import {Excalidraw,MainMenu,serializeAsJSON,loadFromBlob} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';

window.EXCALIDRAW_ASSET_PATH='/canvas/';
window.EXCALIDRAW_EXPORT_SOURCE='YingXu';
let api=null,current='',baseline=null,composing=false,generation=0,root=createRoot(document.getElementById('root'));
const post=(type,extra={})=>parent.postMessage({type,...extra},location.origin);
const serialized=()=>api ? serializeAsJSON(api.getSceneElements(),api.getAppState(),api.getFiles(),'local') : current;
// Selection, scrolling and zoom are not document edits.
const fingerprint=value=>{const s=JSON.parse(value);return JSON.stringify([s.elements,s.files,s.appState.viewBackgroundColor,s.appState.gridSize]);};
window.yingxuCanvas={getValue:()=>{if(api){const next=serialized();if(fingerprint(next)!==baseline){current=next;baseline=fingerprint(next);post('yingxu-canvas-change',{value:current});}}return current;},isComposing:()=>composing};
document.addEventListener('compositionstart',()=>{composing=true;},true);
document.addEventListener('compositionend',()=>{composing=false;},true);
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();if(!composing){window.yingxuCanvas.getValue();parent.postMessage({type:'yingxu-canvas-save'},location.origin);}}},true);
window.addEventListener('message',async event=>{
  if(event.origin!==location.origin||event.source!==parent||event.data?.type!=='yingxu-canvas-load')return;
  const seq=++generation;
  try {
    current=event.data.value;
    const scene=await loadFromBlob(new Blob([current],{type:'application/json'}),null,null);
    if(seq!==generation)return;
    api=null;baseline=null;
    root.render(<Excalidraw key={seq} initialData={{...scene,scrollToContent:true}} langCode="zh-CN"
      excalidrawAPI={value=>{api=value;}}
      onChange={(elements,state,files)=>{
        const value=serializeAsJSON(elements,state,files,'local');const mark=fingerprint(value);
        if(baseline===null){baseline=mark;return;}
        if(mark!==baseline){baseline=mark;current=value;post('yingxu-canvas-change',{value});}
      }}
      validateEmbeddable={false} onLinkOpen={(element,event)=>event.preventDefault()}
      UIOptions={{canvasActions:{loadScene:false,saveToActiveFile:false,export:false,saveAsImage:false,toggleTheme:false}}}
    ><MainMenu><MainMenu.DefaultItems.ClearCanvas/><MainMenu.DefaultItems.ChangeCanvasBackground/></MainMenu></Excalidraw>);
  } catch(error){post('yingxu-canvas-error',{message:'画板载入失败：'+error.message});}
});
post('yingxu-canvas-ready');
