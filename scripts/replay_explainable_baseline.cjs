/* Export old independent strategy decisions. No future prices enter evaluate(). */
'use strict';
const fs=require('node:fs'),zlib=require('node:zlib'),E=require('../static/manual-strategies.js');
const b=JSON.parse(zlib.gunzipSync(fs.readFileSync('research/strategy_engine/bitget-2026-07-10-15m.json.gz'))),result={};
for(const [tf,step] of Object.entries({'15m':900,'1h':3600,'4h':14400})){
 const groups=new Map();for(const x of b){const at=Math.floor(x.time/step)*step;if(!groups.has(at))groups.set(at,[]);groups.get(at).push(x);}
 const bars=[...groups].filter(([,v])=>v.length===step/900).map(([time,v])=>({time,open:v[0].open,high:Math.max(...v.map(x=>x.high)),low:Math.min(...v.map(x=>x.low)),close:v.at(-1).close,volume:v.reduce((s,x)=>s+x.volume,0)}));
 const rows=[];for(let i=259;i<bars.length;i++){
  const now=bars[i].time+step;
  for(const x of E.evaluate(bars.slice(i-259,i+1),step,now))if(['LONG','SHORT'].includes(x.state))rows.push({index:i,strategy:x.strategy,direction:x.setup,entry:x.entry,sl:x.stop,tp:x.target,hold_bars:24});
 }
 result[tf]=rows;
}
fs.writeFileSync(process.argv[2],JSON.stringify(result));
console.log(JSON.stringify(Object.fromEntries(Object.entries(result).map(([tf,x])=>[tf,x.length]))));
