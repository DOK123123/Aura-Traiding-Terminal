/* Owner opt-in only. No tab polling or browser timer delivers notifications. */
(function(){'use strict';
const host=document.getElementById('aura-signal-lock');if(!host)return;
const panel=document.createElement('details');panel.className='aura-push-settings';
panel.innerHTML='<summary>Android Push · настройки и диагностика</summary><p data-push-status role="status">Проверка поддержки…</p>'+
 '<label><input type="checkbox" data-candidate> Предварительные CANDIDATE</label>'+
 '<label><input type="checkbox" data-watch checked> Технические WATCH</label>'+
 '<button type="button" data-enable>Включить уведомления</button><button type="button" data-save>Сохранить выбор типов</button>'+
 '<button type="button" data-disable>Отключить уведомления</button><button type="button" data-test>Тестовое уведомление</button>'+
 '<button type="button" data-diagnose>Проверить подписку</button>'+
 '<p>Это технические сценарии, не вероятность прибыли и не команда на вход. Android и браузер определяют звук: беззвучный режим и энергосбережение могут мешать доставке.</p>'+
 '<p>Render Free может засыпать: тогда новые сценарии не обнаруживаются. Доставка вне открытой вкладки возможна только при работающем сервере, доступном push-сервисе и разрешении устройства.</p>';
host.append(panel);
const get=s=>panel.querySelector(s),status=get('[data-push-status]'),idKey='aura.push.subscription-id.v1';
let id='',config=null,busy=false,bootRefresh=false;
try{id=localStorage.getItem(idKey)||'';}catch{}
const supported=()=>isSecureContext&&'serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;
function show(message){status.textContent=message;}
function prefs(){return {candidate:get('[data-candidate]').checked,watch:get('[data-watch]').checked};}
function saveId(value){id=value;try{if(value)localStorage.setItem(idKey,value);else localStorage.removeItem(idKey);}catch{}}
async function request(path,data){
 const headers={};if(data){headers['Content-Type']='application/json';headers['X-Aura-Preview-Push']=document.querySelector('meta[name="aura-preview-ws-token"]')?.content||'';}
 const response=await fetch('/api/preview/push/'+path,{method:data?'POST':'GET',headers,credentials:'same-origin',cache:'no-store',
  body:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(12000)});
 if(!response.ok)throw Error('PUSH_REQUEST_UNAVAILABLE');return response.json();
}
async function diagnose(){
 if(!supported()){show('Web Push не поддерживается этим браузером или нужен HTTPS.');return;}
 if(Notification.permission==='denied'){show('Уведомления запрещены. Разрешите их в настройках Chrome/Android, затем повторите.');return;}
 try{
  config=await request('status'+(id?'?subscription_id='+encodeURIComponent(id):''));
  if(!config.configured){show('Сервер Web Push пока недоступен. Повторите проверку.');return;}
  const sub=config.diagnostics?.subscription;
  if(sub){get('[data-candidate]').checked=sub.candidate;get('[data-watch]').checked=sub.watch;}
  const messages={ACCEPTED_NOT_DEVICE_CONFIRMED:'Последний push принят push-сервисом. Доставка на телефон не подтверждена.',RETRY:'Ошибка доставки: сервер повторит попытку с ограничением частоты.',STALE:'Сценарий устарел: уведомление не отправлено.'};
  show(sub?(messages[sub.last_status]||'Подписка сохранена. Используйте тест для проверки телефона.'):'Подписка на этом устройстве ещё не включена.');
 }catch{show('Сервер или хранилище уведомлений временно недоступны. Повторите проверку.');}
}
async function action(button,operation){if(busy)return;busy=true;button.disabled=true;try{await operation();}catch{show('Операция не завершена. Проверьте разрешение браузера и соединение, затем повторите.');}finally{busy=false;button.disabled=false;}}
get('[data-enable]').onclick=()=>{
 if(!supported()){show('Для Web Push нужен поддерживаемый браузер и HTTPS.');return;}
 if(Notification.permission==='denied'){show('Разрешение запрещено. Измените его в настройках браузера.');return;}
 if(!config?.configured){show('Сначала нажмите «Проверить подписку», чтобы получить готовность сервера.');return;}
 const permission=Notification.requestPermission(); // Called directly in the user gesture.
 void action(get('[data-enable]'),async()=>{
  if(await permission!=='granted'){show('Разрешение не получено. Уведомления остаются выключенными.');return;}
  const reg=await navigator.serviceWorker.register('/signal-lock-sw.js',{scope:'/'});await navigator.serviceWorker.ready;
  let existing=await reg.pushManager.getSubscription();
  if(existing&&id&&!config.diagnostics?.subscription){await existing.unsubscribe();existing=null;await request('unsubscribe',{id});}
  const bytes=Uint8Array.from(atob(config.public_key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-config.public_key.length%4)%4)),c=>c.charCodeAt(0));
  const sub=existing||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});
  try{const result=await request('subscribe',{subscription:sub.toJSON(),...prefs()});saveId(result.id);show('Подписка сохранена. Отправьте тест и проверьте уведомление на устройстве.');}
  catch(error){await sub.unsubscribe();throw error;}
 });
};
get('[data-save]').onclick=()=>void action(get('[data-save]'),async()=>{if(!id){show('Сначала включите уведомления.');return;}await request('preferences',{id,...prefs()});show('Типы уведомлений сохранены.');});
get('[data-disable]').onclick=()=>void action(get('[data-disable]'),async()=>{
 const reg=await navigator.serviceWorker.getRegistration('/');const sub=await reg?.pushManager.getSubscription();if(sub)await sub.unsubscribe();
 if(id)await request('unsubscribe',{id});saveId('');show('Уведомления отключены.');
});
get('[data-test]').onclick=()=>void action(get('[data-test]'),async()=>{
 if(!id){show('Сначала включите уведомления на этом устройстве.');return;}
 const result=await request('test',{id});show(result.enqueued?'Тест поставлен в очередь. Проверьте телефон: этот ответ ещё не подтверждает доставку.':'Тест уже запрошен недавно. Подождите две минуты.');
});
get('[data-diagnose]').onclick=()=>void diagnose();
window.addEventListener('aura-preview-snapshot',e=>{if(!bootRefresh&&e.detail?.signal_lock?.ready){bootRefresh=true;void diagnose();}});
if(new URL(location.href).searchParams.has('push_test')){panel.open=true;show('Открыто тестовое уведомление. Это не торговый сигнал.');}
void diagnose();
})();
