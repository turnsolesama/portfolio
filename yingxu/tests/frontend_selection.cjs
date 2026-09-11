'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function setup(order=['a','b','c','d','e']) {
  const nodes=order.map(id=>({dataset:{item:id}}));
  const context=vm.createContext({document:{querySelectorAll:()=>nodes},localStorage:{getItem:()=>null}});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/, '');
  vm.runInContext(source+'\nupdateSelection=()=>{};globalThis.app={state,selectResource};',context);
  return {...context.app,selected:()=>[...context.app.state.selectedIds],nodes};
}

test('click first then Shift click last selects the inclusive range',()=>{
  const s=setup();s.selectResource('b');s.selectResource('e',{shiftKey:true});
  assert.deepEqual(s.selected(),['b','c','d','e']);assert.equal(s.state.selectionAnchor,'b');
  s.selectResource('c',{shiftKey:true});assert.deepEqual(s.selected(),['b','c']);
});
test('reverse range follows the visible board/list order',()=>{
  const s=setup(['e','c','a','d','b']);s.selectResource('d');s.selectResource('e',{shiftKey:true});
  assert.deepEqual(s.selected(),['e','c','a','d']);
});
test('Ctrl toggles individual resources and Ctrl Shift adds a range',()=>{
  const s=setup();s.selectResource('a');s.selectResource('c',{ctrlKey:true});s.selectResource('e',{shiftKey:true,ctrlKey:true});
  assert.deepEqual(s.selected(),['a','c','d','e']);
  s.selectResource('a',{ctrlKey:true});assert.deepEqual(s.selected(),['c','d','e']);
});
test('checkboxes establish the same range anchor and toggle without replacing other checks',()=>{
  const s=setup();s.selectResource('a',{},true);s.selectResource('d',{shiftKey:true},true);
  assert.deepEqual(s.selected(),['a','b','c','d']);
  s.selectResource('b',{},true);assert.deepEqual(s.selected(),['a','c','d']);
});
test('missing anchor after navigation does not select an unrelated range',()=>{
  const s=setup();s.state.selectionAnchor='previous-page';s.selectResource('d',{shiftKey:true});
  assert.deepEqual(s.selected(),['d']);assert.equal(s.state.selectionAnchor,'d');
});
