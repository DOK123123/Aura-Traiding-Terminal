/* Opt-in audible LIVE notifications. No network, replay or execution authority. */
(function(root){'use strict';
const KEY='aura.signal.alerts.v1',defaults={enabled:false,LONG:true,SHORT:true,volume:.3};
class Alerts{
 constructor({storage,player,onStatus=()=>{}}){this.storage=storage;this.player=player;this.onStatus=onStatus;this.settings={...defaults};this.watermarks={};this.ready=false;this.durable=false;
  try{const x=JSON.parse(storage?.getItem(KEY)||'null');if(x?.version===1){for(const k of ['enabled','LONG','SHORT'])if(typeof x.settings?.[k]==='boolean')this.settings[k]=x.settings[k];if(Number.isFinite(x.settings?.volume))this.settings.volume=Math.min(1,Math.max(0,x.settings.volume));if(x.watermarks&&typeof x.watermarks==='object')for(const [k,v]of Object.entries(x.watermarks).slice(0,100))if(Number.isFinite(v.at)&&typeof v.id==='string')this.watermarks[k]={at:v.at,id:v.id};}this.persist();}catch{this.onStatus('Хранилище недоступно: автоматический звук заблокирован');}
 }
 persist(){if(!this.storage)throw Error('NO_STORAGE');this.storage.setItem(KEY,JSON.stringify({version:1,settings:this.settings,watermarks:this.watermarks}));this.durable=true;}
 configure(values){for(const k of ['enabled','LONG','SHORT'])if(typeof values[k]==='boolean')this.settings[k]=values[k];if(Number.isFinite(values.volume))this.settings.volume=Math.min(1,Math.max(0,values.volume));try{this.persist();}catch{this.durable=false;this.ready=false;this.onStatus('Настройки не сохранены: автоматический звук заблокирован');}}
 async arm(){try{this.ready=await this.player.activate();this.onStatus(this.ready?'Звук активирован для этой вкладки':'Браузер не разрешил звук. Нажмите ещё раз');return this.ready;}catch{this.ready=false;this.onStatus('Звук недоступен в браузере');return false;}}
 suspend(){this.ready=false;this.player.suspend?.();this.onStatus('Звук приостановлен. Нажмите «Активировать звук» после возврата');}
 async test(){if(await this.arm())this.player.play('LONG',this.settings.volume);}
 receive(rows,{now,live,hidden=false}){
  let played=0;
  for(const x of rows){
   if(!live||hidden||!Number.isFinite(now)||x.version!=='MANUAL_STRATEGIES_1'||!['entry','stop','target'].every(k=>Number.isFinite(x[k])&&x[k]>0)||!(x.state==='LONG'?x.stop<x.entry&&x.entry<x.target:x.target<x.entry&&x.entry<x.stop)||!Array.isArray(x.reasons)||!Array.isArray(x.rejection)||x.mode==='HISTORICAL_REPLAY'||!x.fresh||!['LONG','SHORT'].includes(x.state)||x.setup!==x.state||!['TREND_PULLBACK','BREAKOUT_RETEST','SR_REVERSAL'].includes(x.strategy)||!['15m','1h','4h'].includes(x.tf)||!x.id||typeof x.id!=='string'||!Number.isFinite(x.formed_at)||x.formed_at>now||!Number.isFinite(x.valid_until)||x.valid_until<=now||!Number.isFinite(x.net_rr)||x.net_rr<1.5||x.rejection?.length||!['VALIDATED','UNVALIDATED'].includes(x.edge))continue;
   const step={'15m':900,'1h':3600,'4h':14400}[x.tf];if(now-x.formed_at>=step||x.id!==[x.version,x.strategy,step,x.formed_at].join(':'))continue;
   const key=[x.version,x.strategy,x.state,x.tf].join(':'),old=this.watermarks[key];
   if(old&&(x.formed_at<old.at||x.formed_at===old.at))continue;
   // Persist BEFORE playing, including when muted/unarmed, to prevent reload/backlog repeats.
   this.watermarks[key]={at:x.formed_at,id:x.id};
   try{this.persist();}catch{this.ready=false;this.durable=false;this.onStatus('Не удалось сохранить дедупликацию. Звук заблокирован');continue;}
   if(this.settings.enabled&&this.settings[x.state]&&this.ready&&this.durable){
    const result=this.player.play(x.state,this.settings.volume);if(result!==false){played++;this.onStatus(x.state+' · '+x.strategy+' · '+x.tf+(x.edge==='UNVALIDATED'?' · UNVALIDATED: статистическая эффективность не подтверждена':''));}
    else{this.ready=false;this.onStatus('Звук приостановлен браузером. Активируйте ещё раз');}
   }
  }
  return played;
 }
}
class WebAudioPlayer{
 constructor(){this.context=null;this.plays=0;}
 async activate(){const C=root.AudioContext||root.webkitAudioContext;if(!C)return false;this.context??=new C();await this.context.resume();return this.context.state==='running';}
 suspend(){const context=this.context;this.context=null;context?.close().catch(()=>{});}
 play(side,volume){const c=this.context;if(c?.state!=='running')return false;try{const start=c.currentTime;for(const [i,f]of (side==='LONG'?[660,880]:[440,330]).entries()){const oscillator=c.createOscillator(),gain=c.createGain();oscillator.type='sine';oscillator.frequency.value=f;gain.gain.setValueAtTime(0,start+i*.14);gain.gain.linearRampToValueAtTime(volume*.25,start+i*.14+.015);gain.gain.exponentialRampToValueAtTime(.0001,start+i*.14+.12);oscillator.connect(gain);gain.connect(c.destination);oscillator.start(start+i*.14);oscillator.stop(start+i*.14+.13);oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};}this.plays++;return true;}catch{return false;}}
}
const api={Alerts,WebAudioPlayer,KEY};root.AuraSignalAlerts=api;if(typeof module!=='undefined')module.exports=api;
if(!root.document||document.body.dataset.manualPreview!=='true')return;
const host=document.getElementById('aura-notifications');if(!host)return;
host.innerHTML=`<h2>Уведомления · LIVE</h2><p>Короткий звук только для нового допустимого LONG/SHORT. UNVALIDATED означает: статистическая эффективность не подтверждена. Звук не открывает сделки. При закрытой вкладке, сне или блокировке телефона доставка не гарантируется. Replay не озвучивается.</p>
<div class="replay-controls"><label><input id="sa-enabled" type="checkbox"> Включить звук</label><label><input id="sa-long" type="checkbox"> LONG</label><label><input id="sa-short" type="checkbox"> SHORT</label><label>Громкость<input id="sa-volume" type="range" min="0" max="1" step="0.05"></label><button id="sa-arm" type="button">Активировать звук</button><button id="sa-test" type="button">Проверить звук</button></div><p id="sa-status" role="status">Нажмите «Активировать звук»: браузеру нужно действие пользователя. После перезагрузки активация нужна снова.</p>`;
const el=k=>document.getElementById('sa-'+k),player=new WebAudioPlayer();let storage=null;try{storage=localStorage;}catch{}
const alerts=new Alerts({storage,player,onStatus:text=>{el('status').textContent=text;}});root.AuraLiveAlerts={alerts,player};
for(const k of ['enabled','LONG','SHORT'])el(k.toLowerCase()).checked=alerts.settings[k];el('volume').value=alerts.settings.volume;
el('enabled').addEventListener('change',async()=>{alerts.configure({enabled:el('enabled').checked});if(alerts.settings.enabled)await alerts.arm();else{alerts.suspend();el('status').textContent='Автоматический звук выключен';}});
for(const k of ['LONG','SHORT'])el(k.toLowerCase()).addEventListener('change',()=>alerts.configure({[k]:el(k.toLowerCase()).checked}));
el('volume').addEventListener('input',()=>alerts.configure({volume:Number(el('volume').value)}));
el('arm').addEventListener('click',()=>alerts.arm());el('test').addEventListener('click',()=>alerts.test());
root.addEventListener('aura-manual-signals',event=>{const {rows,now,snapshot}=event.detail;alerts.receive(rows,{now,live:snapshot.status==='LIVE',hidden:document.hidden});});
document.addEventListener('visibilitychange',()=>{if(document.hidden)alerts.suspend();});root.addEventListener('pagehide',()=>alerts.suspend());
})(typeof window==='undefined'?globalThis:window);
