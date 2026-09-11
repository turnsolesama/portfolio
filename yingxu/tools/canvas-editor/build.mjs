import {build} from 'esbuild';
import {mkdir,cp,writeFile,readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const output=path.resolve('../../frontend/canvas');
await mkdir(output,{recursive:true});
await build({entryPoints:['entry.jsx'],bundle:true,splitting:true,format:'esm',outdir:output,minify:true,conditions:['production'],define:{'process.env.NODE_ENV':'"production"'},loader:{'.woff2':'file','.woff':'file','.ttf':'file'},metafile:true,legalComments:'external'});
await cp('node_modules/@excalidraw/excalidraw/dist/prod/fonts',path.join(output,'fonts'),{recursive:true});
await writeFile(path.join(output,'index.html'),'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>映序画板</title><link rel="stylesheet" href="/canvas/entry.css"><link rel="stylesheet" href="/canvas/host.css"><div id="root"></div><script type="module" src="/canvas/entry.js"></script></html>');
await writeFile(path.join(output,'host.css'),'html,body,#root{margin:0;width:100%;height:100%;overflow:hidden}.excalidraw{--color-primary:#466d57;--color-primary-darker:#365443}.excalidraw .library-button{display:none}');
const manifest=[];
async function walk(folder){for(const item of await readdir(folder,{withFileTypes:true})){const file=path.join(folder,item.name);if(item.isDirectory())await walk(file);else {const data=await readFile(file);manifest.push({path:path.relative(output,file).replaceAll('\\','/'),bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')});}}}
await cp('pnpm-lock.yaml',path.join(output,'DEPENDENCIES.lock.yaml'));
let licenses='Excalidraw 0.18.1 / React 18.3.1 and bundled dependencies\n\n';
for(const name of ['@excalidraw/excalidraw','react','react-dom']){for(const file of ['LICENSE','LICENSE.txt']){try{licenses+='\n'+name+'\n'+await readFile('node_modules/'+name+'/'+file,'utf8');break;}catch{}}}
await writeFile(path.join(output,'LICENSE.txt'),licenses);
await cp('Excalidraw-LICENSE.txt',path.join(output,'Excalidraw-LICENSE.txt'));
try{await cp('FONT-LICENSES.txt',path.join(output,'FONT-LICENSES.txt'));}catch{}
const licenseDir=path.join(output,'licenses');await mkdir(licenseDir,{recursive:true});
for(const entry of await readdir('node_modules/.pnpm',{withFileTypes:true})){
  if(!entry.isDirectory())continue;
  const modules=path.join('node_modules/.pnpm',entry.name,'node_modules');
  let packages=[];try{packages=await readdir(modules,{withFileTypes:true});}catch{continue;}
  for(const pack of packages){
    if(pack.isSymbolicLink())continue;
    let dirs=[path.join(modules,pack.name)];
    if(pack.name.startsWith('@'))dirs=(await readdir(dirs[0])).map(n=>path.join(dirs[0],n));
    for(const dir of dirs){
      let names=[];try{names=await readdir(dir);}catch{continue;}
      for(const file of names.filter(n=>/^(license|copying|ofl)/i.test(n))){
        try{await cp(path.join(dir,file),path.join(licenseDir,entry.name.replaceAll('+','-')+'-'+file+'.txt'));}catch{}
      }
    }
  }
}
// Do not include the previous manifest in its own new digest set.
async function inventory(folder){for(const item of await readdir(folder,{withFileTypes:true})){const file=path.join(folder,item.name);if(item.isDirectory())await inventory(file);else if(file!==path.join(output,'manifest.json')){const data=await readFile(file);manifest.push({path:path.relative(output,file).replaceAll('\\','/'),bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')});}}}
await inventory(output);
await writeFile(path.join(output,'manifest.json'),JSON.stringify({excalidraw:'0.18.1',react:'18.3.1',files:manifest},null,2));
console.log('Built local Excalidraw assets:',manifest.length);
