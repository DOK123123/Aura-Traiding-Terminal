// Local stdin/stdout calculation only; never a market/HTTP client.
const rl=require('node:readline').createInterface({input:process.stdin}),A=require('../../static/manual-live-analysis.js');
rl.on('line',line=>{try{const b=JSON.parse(line),v=A.analyze(b.snapshot,b.now);process.stdout.write(JSON.stringify({state:v.state,reasons:v.reasons,scenario:v.scenario,frames:Object.fromEntries(Object.entries(v.frames).map(([tf,f])=>[tf,f.confirmed]))})+'\n');}catch{process.stdout.write('{"state":"WAIT","reasons":["INVALID_REPLAY"],"scenario":null}\n');}});
