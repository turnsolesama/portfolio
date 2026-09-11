/* Local Markdown file links stay inert until the backend authorizes their IDs. */
(function(scope){
  'use strict';
  const validId=id=>typeof id==='string'&&/^[a-f0-9]{32}$/.test(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function relativeLink(value){
    if(typeof value!=='string'||!value||value.length>4096||/[\x00-\x20\x7f]/.test(value))return false;
    const parts=value.split('#');if(parts.length>2||parts[1]&&!/^yx-item=[a-f0-9]{32}$/.test(parts[1]))return false;
    let path;try{path=decodeURIComponent(parts[0]);}catch{return false;}
    return !!path&&!/^[\/\\]/.test(path)&&!/[\\:\x00-\x1f\x7f]/.test(path)&&!parts[0].includes('?');
  }
  function linkRequest(note,item){if(!validId(note)||!validId(item))throw Error('只有项目中已登记的文稿和文件才能建立链接。');return '/api/markdown-assets/file-link?'+new URLSearchParams({note,item});}
  function resolveRequest(note,path){if(!validId(note)||!relativeLink(path))throw Error('此链接不是受支持的项目文件链接。');return '/api/markdown-assets/resolve-file?'+new URLSearchParams({note,path});}
  function renderLink(label,path,note){
    if(!validId(note)||!relativeLink(path))return escape(label);
    return `<a href="#yx-file" data-yx-document-link="${escape(path)}" data-yx-note="${note}" title="在映序中打开项目文件">${escape(label)}</a>`;
  }
  function bind({root,api,onOpen,onError=()=>{}}){
    let disposed=false,busy=false;
    const click=async event=>{
      const anchor=event.target.closest?.('[data-yx-document-link]');if(!anchor||!root.contains(anchor))return;
      event.preventDefault();event.stopPropagation();if(disposed||busy)return;
      busy=true;
      try{const item=await api(resolveRequest(anchor.dataset.yxNote,anchor.dataset.yxDocumentLink));if(!disposed&&root.contains(anchor)&&anchor.isConnected!==false&&validId(item?.id))await onOpen(item.id,item,anchor);}
      catch(error){if(!disposed)onError(error);}
      finally{busy=false;}
    };
    root.addEventListener('click',click);
    return {destroy(){disposed=true;root.removeEventListener('click',click);}};
  }
  scope.YingXuDocumentLinks={relativeLink,linkRequest,resolveRequest,renderLink,bind};
  if(typeof module!=='undefined')module.exports=scope.YingXuDocumentLinks;
})(typeof window!=='undefined'?window:globalThis);
