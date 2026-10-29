/* Reproducible local research; reads only the preserved real Bitget OHLCV archive. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto'),{execFileSync}=require('node:child_process');
const R=require('../static/historical-replay.js'),O=require('../static/trade-outcomes.js');
const out=process.argv[2]||'work/trade-outcomes',py=process.env.PYTHON||'python';fs.mkdirSync(out,{recursive:true});
const periods=[{label:'october',start:1790812800,end:1793232000},{label:'august05to31',start:1785888000,end:1788220800},{label:'september',start:1788220800,end:1790812800}];
const summaries=[];
for(const period of periods)for(const tf of ['15m','1h','4h']){
 const payload=JSON.parse(execFileSync(py,['-c',`import json,time;from app.manual_preview.history import archive_history;print(json.dumps(archive_history(${JSON.stringify(tf)},${period.start},${period.end},time.time())))`],{maxBuffer:8e6,encoding:'utf8'}));
 const replay=new R.Replay(payload),stress=new O.Analyzer(R.STEPS[tf],{full_spread_bps:4,slippage_bps_per_side:10,fee_bps_per_side:20});
 while(!replay.done){const index=replay.cursor,bar=replay.bars[index],rows=replay.next();stress.advance(bar);for(const s of rows)if(['LONG','SHORT'].includes(s.state))stress.register(s);}stress.finalize();
 const result=replay.outcomeReport(),stressed={...stress.report(),source:payload.source,input_sha256:payload.sha256,timeframe:tf,start:period.start,end:period.end};
 for(const [suffix,data] of [['base',result],['stress2',stressed]]){const file=path.join(out,`${period.label}-${tf}-${suffix}.json.gz`);const json=JSON.stringify(data);fs.writeFileSync(file,zlib.gzipSync(json,{mtime:0}));}
 summaries.push({period:period.label,timeframe:tf,start:period.start,end:period.end,input_sha256:payload.sha256,result_sha256:crypto.createHash('sha256').update(JSON.stringify(result)).digest('hex'),counts:replay.counts,groups:Object.fromEntries(Object.entries(result.statistics.groups).map(([key,{curve,...m}])=>[key,m])),stress2:Object.fromEntries(Object.entries(stressed.statistics.groups).map(([key,{curve,...m}])=>[key,m]))});
}
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({source:'PRESERVED_REAL_BITGET_USDT_FUTURES_BTCUSDT',edge:'UNVALIDATED',validation:'NO_VALIDATED_EDGE',selection:'DESCRIPTIVE_MONTHS_NOT_INDEPENDENT_VALIDATION;NO_TUNING',results:summaries},null,2));console.log(JSON.stringify(summaries.map(r=>({period:r.period,tf:r.timeframe,signals:r.counts.LONG+r.counts.SHORT,groups:r.groups})),null,2));
