/* Recovery stays outside the service worker's cached paths so port sign-in can complete. */
'use strict';
const recoveryStatus=document.getElementById('recovery-status');
const retryRecovery=document.getElementById('retry-recovery');
async function recoverWorkspace(){
  retryRecovery.hidden=true;
  try{
    if('serviceWorker' in navigator){
      const registrations=await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.filter(registration=>[registration.active,registration.waiting,registration.installing].some(worker=>{
        if(!worker)return false;const url=new URL(worker.scriptURL);return url.origin===location.origin && url.pathname==='/service-worker.js';
      })).map(registration=>registration.unregister()));
    }
    if('caches' in window){
      const names=await caches.keys();
      await Promise.all(names.filter(name=>name.startsWith('avtrack-offline-')).map(name=>caches.delete(name)));
    }
    recoveryStatus.textContent='Browser files refreshed. Opening AVTrack…';
    location.replace('/?recovered='+Date.now());
  }catch(error){
    recoveryStatus.textContent='Could not refresh browser files: '+error.message+'. Try opening the app in a new private browser window and sign in to GitHub if prompted.';
    retryRecovery.hidden=false;
  }
}
retryRecovery.onclick=recoverWorkspace;
recoverWorkspace();
