/* Compare versioned elements and file identities without serializing image data. */
export function createSceneTracker() {
  let previous=null;
  const remember=(elements,state,files,ids)=>({
    elements:elements.map(e=>[e.id,e.version,e.versionNonce,!!e.isDeleted]),
    files:ids.map(id=>{const f=files[id];return[id,f?.dataURL,f?.mimeType,f?.created];}),
    background:state.viewBackgroundColor,gridSize:state.gridSize,gridStep:state.gridStep,gridMode:state.gridModeEnabled
  });
  return {
    reset(){previous=null;},
    changed(elements=[],state={},files={}) {
      const ids=Object.keys(files).sort();
      if(previous===null){previous=remember(elements,state,files,ids);return false;}
      let changed=previous.elements.length!==elements.length||previous.files.length!==ids.length||previous.background!==state.viewBackgroundColor||previous.gridSize!==state.gridSize||previous.gridStep!==state.gridStep||previous.gridMode!==state.gridModeEnabled;
      for(let i=0;!changed&&i<elements.length;i++){
        const e=elements[i],p=previous.elements[i];
        changed=e.id!==p[0]||e.version!==p[1]||e.versionNonce!==p[2]||!!e.isDeleted!==p[3];
      }
      for(let i=0;!changed&&i<ids.length;i++){
        const id=ids[i],f=files[id],p=previous.files[i];
        changed=id!==p[0]||f?.dataURL!==p[1]||f?.mimeType!==p[2]||f?.created!==p[3];
      }
      if(changed)previous=remember(elements,state,files,ids);
      return changed;
    }
  };
}
