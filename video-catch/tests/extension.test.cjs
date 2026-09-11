const test = require('node:test');
const assert = require('node:assert/strict');
const { classify } = require('../extension/media.js');
const fs = require('node:fs');
const vm = require('node:vm');
test('manifest sniffing includes extensionless URLs and query strings', () => {
  assert.equal(classify('https://cdn.test/movie.m3u8?token=x'), 'hls');
  assert.equal(classify('https://cdn.test/get', 'application/dash+xml; charset=utf-8'), 'dash');
  assert.equal(classify('https://cdn.test/get', 'video/webm'), 'file');
});
test('segments and audio are never listed as complete videos', () => {
  for (const name of ['part.m4s', 'part.ts', 'part.cmfv', 'audio.m4a']) {
    assert.equal(classify('https://cdn.test/' + name, 'video/mp4'), null);
  }
  assert.equal(classify('https://cdn.test/get', 'video/mp2t'), null);
  assert.equal(classify('bad url'), null);
});

function browserFixture(fetchImpl = async () => ({})) {
  const context = { URL, location: new URL('https://www.bilibili.com/video/BV1WuYh6VEaS/'),
    document: {querySelector: () => ({})}, module: {exports: {}},
    XMLHttpRequest: function () {this.listeners = new Map();}, fetch: fetchImpl };
  context.XMLHttpRequest.prototype.open = function () {};
  context.XMLHttpRequest.prototype.addEventListener = function (event, callback) {this.listeners.set(event, callback);};
  context.XMLHttpRequest.prototype.removeEventListener = function (event, callback) {if(this.listeners.get(event) === callback)this.listeners.delete(event);};
  context.window = context;
  context.__INITIAL_STATE__ = {cid: 11, videoData:{bvid:'BV1WuYh6VEaS',pages:[{cid:11},{cid:22}]}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require.resolve('../extension/bili-observer.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(require.resolve('../extension/scan.js'), 'utf8'), context);
  return context;
}
test('captures embedded play info before the Bili player clears it', () => {
  const c = browserFixture();
  c.__playinfo__ = {code:0,data:{dash:{video:[{baseUrl:'https://cdn.test/v.m4s',codecs:'avc1.64001f'}],audio:[{baseUrl:'https://cdn.test/a.m4s',codecs:'mp4a.40.2'}]}}};
  c.__playinfo__ = undefined;
  assert.equal(c.__playinfo__, undefined);
  assert.equal(c.scanPage().formats.length, 2);
  assert.equal(c.scanPage().formats[1].role, 'audio');
  c.location = new URL('https://www.bilibili.com/video/BV1Different/');
  assert.equal(c.scanPage().formats.length, 0);
});
test('does not mix different parts, or export protected playback data', () => {
  const c = browserFixture();
  c.__playinfo__ = {code:0,data:{is_drm:true,dash:{video:[{baseUrl:'https://cdn.test/v.m4s'}]}}};
  assert.equal(c.scanPage().formats.length, 0);
  c.__playinfo__ = {code:0,data:{dash:{video:[{baseUrl:'https://cdn.test/v.m4s'}]}}};
  c.location = new URL('https://www.bilibili.com/video/BV1WuYh6VEaS/?p=2');
  assert.equal(c.scanPage().formats.length, 0);
});
test('fetch observer preserves the original response and excludes unrelated data', async () => {
  const data = {code:0,data:{private:'do-not-copy',dash:{video:[{baseUrl:'https://cdn.test/v.m4s'}],audio:[{baseUrl:'https://cdn.test/a.m4s'}]}}};
  const response = {headers:{get:()=>null},clone:()=>({json:async()=>data})};
  const promise = Promise.resolve(response);
  const c = browserFixture(() => promise);
  assert.equal(c.fetch('https://api.bilibili.com/x/player/wbi/playurl?cid=11'), promise);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(c.scanPage().formats.length, 2);
  assert.equal(JSON.stringify(c.__videoCatchPlayback).includes('do-not-copy'), false);
});
test('reused XHR cannot associate another response with a previous video', () => {
  const c = browserFixture();
  const xhr = new c.XMLHttpRequest();
  xhr.open('GET','https://api.bilibili.com/x/player/playurl?cid=11');
  assert.equal(xhr.listeners.size, 1);
  xhr.open('GET','https://api.bilibili.com/x/web-interface/nav');
  assert.equal(xhr.listeners.size, 0);
  xhr.open('GET','https://api.bilibili.com/x/player/playurl?cid=11');
  xhr.responseType='json';
  xhr.response={code:0,data:{dash:{video:[{baseUrl:'https://cdn.test/v.m4s'}],audio:[{baseUrl:'https://cdn.test/a.m4s'}]}}};
  xhr.listeners.get('load')();
  assert.equal(c.scanPage().formats.length, 2);
});
