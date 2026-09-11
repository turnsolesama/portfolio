'use strict';
// Program ingress and website rules are local routing policy, never login data.
const path=require('node:path'),net=require('node:net');
const {domainToASCII}=require('node:url');
const ID=/^[a-f0-9]{32}$/;
const ingressName=id=>'FS-Program-'+id;
const ingressGroup=id=>ingressName(id)+'-Route';
const samePath=(a,b)=>path.win32.normalize(a).toLowerCase()===path.win32.normalize(b).toLowerCase();
function domain(value){
 if(typeof value!=='string'||value!==value.trim()||/[\s\x00-\x1f\/,\\:@?#*()]/.test(value))throw Error('网站规则只接受域名，不能包含网址路径、端口或登录参数');
 const result=domainToASCII(value.replace(/\.$/,'')).toLowerCase();
 if(!result||result.length>253||net.isIP(result)||result.split('.').some(label=>!label||label.length>63||!/^([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])$/.test(label)))throw Error('网站域名格式无效');
 return result;
}
function normalize(s,o){
 const router=require('./AppRouter.cjs'),ingresses=s.programIngresses===undefined?[]:s.programIngresses,sites=s.siteRules===undefined?[]:s.siteRules;
 if(!Array.isArray(ingresses)||ingresses.length>128||!Array.isArray(sites)||sites.length>1024)throw Error('程序入口或网站规则列表无效');
 const ids=new Set(),paths=new Set(),ports=new Set(o.Profiles.filter(p=>['127.0.0.1','localhost','::1'].includes(p.Host)).map(p=>p.Port));
 const guards=o.Profiles.flatMap(p=>[p.CorePath,p.AppPath]).filter(Boolean);
 const route=(id,follow=false)=>{if(id==='Direct'||(follow&&id==='Follow')||o.Profiles.some(p=>p.Id===id&&p.Id!==o.Routing.ProfileId))return id;throw Error('规则目标不是可用上游');};
 const programIngresses=ingresses.map(raw=>{
  if(!raw||!ID.test(raw.id)||ids.has(raw.id)||!Number.isInteger(raw.port)||raw.port<1024||raw.port>65535||ports.has(raw.port))throw Error('程序固定入口标识或端口无效、重复或与已有代理冲突');
  const e=router.normalizeEntry(raw.path,route(raw.route,true),o),key=e.path.toLowerCase();
  if(paths.has(key)||guards.some(p=>samePath(p,e.path))||(s.entries||[]).some(x=>samePath(x.path,e.path)))throw Error('程序固定入口与已有规则或代理内核冲突');
  ids.add(raw.id);paths.add(key);ports.add(raw.port);
  const result={id:raw.id,path:e.path,port:raw.port,route:e.route},identity=router.normalizeIdentity(raw.identity);if(identity)result.identity=identity;return result;
 });
 const siteIds=new Set(),matches=new Set();
 const siteRules=sites.map(raw=>{
  if(!raw||!ID.test(raw.id)||siteIds.has(raw.id)||!['domain','suffix'].includes(raw.type)||(raw.scope!=='global'&&!ids.has(raw.scope)))throw Error('网站规则标识、范围或匹配方式无效');
  const value=domain(raw.domain),key=[raw.scope,raw.type,value].join('|');if(matches.has(key))throw Error('同一范围包含重复的网站规则');
  matches.add(key);siteIds.add(raw.id);return {id:raw.id,scope:raw.scope,type:raw.type,domain:value,route:route(raw.route)};
 });
 return {programIngresses,siteRules};
}
function routeIds(s){return [...new Set([...(s.entries||[]).map(x=>x.route),s.defaultRoute,...(s.programIngresses||[]).map(x=>x.route),...(s.siteRules||[]).map(x=>x.route)].filter(x=>x&&x!=='Follow'))];}
function sharedRouteIds(s){return [...new Set([...(s.entries||[]).map(x=>x.route),s.defaultRoute,...(s.siteRules||[]).map(x=>x.route)].filter(Boolean))];}
function selectors(s,group){return [...sharedRouteIds(s).filter(x=>x!=='Direct').map(id=>({key:id,name:group(id),preferred:id})),...(s.programIngresses||[]).filter(e=>!['Direct','Follow'].includes(e.route)).map(e=>({key:'ingress-'+e.id,name:ingressGroup(e.id),preferred:e.route}))];}
function ingressTarget(e,s,group){return e.route==='Follow'?(s.defaultRoute?group(s.defaultRoute):'REJECT'):e.route==='Direct'?group('Direct'):ingressGroup(e.id);}
function requestedRoute(ingress,s){return ingress.route==='Follow'?s.defaultRoute:ingress.route;}
function connectionRows(snapshot){
 if(Array.isArray(snapshot?.connections))return snapshot.connections;
 // Pinned mihomo Snapshot uses a nil Go slice for zero active connections.
 // Accept only that complete controller shape, not a missing/failed response.
 if(snapshot?.connections===null&&['downloadTotal','uploadTotal','memory'].every(key=>Number.isFinite(snapshot[key])&&snapshot[key]>=0))return [];
 return null;
}
function orderedSiteRules(s){
 // The editor has no manual rule ordering. More-specific domains win inside
 // each scope; an exact rule wins over a suffix rule for the same hostname.
 return (s.siteRules||[]).map((rule,index)=>({rule,index})).sort((a,b)=>
  b.rule.domain.split('.').length-a.rule.domain.split('.').length||
  (a.rule.type==='domain'?0:1)-(b.rule.type==='domain'?0:1)||a.index-b.index).map(x=>x.rule);
}
function rules(s,group){
 const result=[],push=(line,type,payload,proxy)=>result.push({line,type,payload,proxy});
 for(const scope of ['program','global'])for(const rule of orderedSiteRules(s)){
  if((rule.scope==='global')!==(scope==='global'))continue;
  const rawType=rule.type==='domain'?'DOMAIN':'DOMAIN-SUFFIX',type=rule.type==='domain'?'Domain':'DomainSuffix',target=group(rule.route);
  if(scope==='global')push(rawType+','+rule.domain+','+target,type,rule.domain,target);
  else {const name=ingressName(rule.scope);push('AND,((IN-NAME,'+name+'),('+rawType+','+rule.domain+')),'+target,'AND','((InName,'+name+') && ('+type+','+rule.domain+'))',target);}
 }
 for(const e of s.programIngresses||[]){const target=ingressTarget(e,s,group),name=ingressName(e.id);push('IN-NAME,'+name+','+target,'InName',name,target);}
 for(const e of s.entries||[]){const target=group(e.route),exe=path.win32.normalize(e.path);push('PROCESS-PATH,'+exe+','+target,'ProcessPath',exe,target);}
 const target=s.defaultRoute?group(s.defaultRoute):'REJECT';push('MATCH,'+target,'Match','',target);return result;
}
function listeners(s){return (s.programIngresses||[]).map(e=>({name:ingressName(e.id),type:'mixed',listen:'127.0.0.1',port:e.port,udp:false}));}
function connectionPolicy(s,metadata,group){
 const ingress=(s.programIngresses||[]).find(e=>ingressName(e.id)===metadata?.inboundName);
 let host=String(metadata?.host||'').toLowerCase().replace(/\.$/,'');
 const matches=r=>r.type==='domain'?host===r.domain:host===r.domain||host.endsWith('.'+r.domain);
 const ordered=orderedSiteRules(s),rule=ordered.find(r=>ingress&&r.scope===ingress.id&&matches(r))||ordered.find(r=>r.scope==='global'&&matches(r));
 if(rule)return group?group(rule.route):rule.route;
 if(ingress)return group?ingressTarget(ingress,s,group):requestedRoute(ingress,s);
 const entry=(s.entries||[]).find(e=>metadata?.processPath&&samePath(e.path,metadata.processPath));const selected=entry?entry.route:s.defaultRoute;return group?(selected?group(selected):'REJECT'):selected;
}
module.exports={normalize,domain,ingressName,ingressGroup,routeIds,sharedRouteIds,selectors,ingressTarget,requestedRoute,connectionRows,orderedSiteRules,rules,listeners,connectionPolicy};
