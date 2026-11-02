'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {displaySides}=require('../static/signal-confidence.js');
test('missing and disconnected data keeps all eight sides UNKNOWN without levels',()=>{
 for(const data of [null,{}, {observer:{running:false},server_time:100}]){
  const rows=displaySides(data,100);
  assert.equal(rows.length,8);
  assert.deepEqual(rows.map(x=>x.direction),['LONG','SHORT','LONG','SHORT','LONG','SHORT','LONG','SHORT']);
  for(const x of rows){assert.equal(x.state,'UNKNOWN');assert.equal(x.score,null);assert.equal(x.entry,undefined);}
 }
});
