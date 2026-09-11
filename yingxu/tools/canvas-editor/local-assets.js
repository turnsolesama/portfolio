import {createAnimationGate} from './animation-gate.js';
// A blocking local bootstrap executes before the Excalidraw module graph.
window.EXCALIDRAW_ASSET_PATH=location.origin+'/canvas/';
window.EXCALIDRAW_EXPORT_SOURCE='YingXu';
if(!window.yingxuCanvasFrames){
  const gate=createAnimationGate(window.requestAnimationFrame.bind(window),window.cancelAnimationFrame.bind(window));
  window.requestAnimationFrame=gate.request;window.cancelAnimationFrame=gate.cancel;
  window.yingxuCanvasFrames=gate;
}
