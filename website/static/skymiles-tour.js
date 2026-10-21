/* Delta SkyMiles extended tour: smooth, accessible, cross-page steps.
   Only navigates to first-party pages and stores progress for this tab. */
(() => {
 'use strict';
 const modal=document.getElementById('tutorial-modal');
 if(!modal) return;
 const intro=modal.querySelector('.tutorial-intro');
 const guide=modal.querySelector('.tutorial-guide');
 const name=JSON.parse(document.getElementById('delta-tour-name')?.textContent||'""') || 'member';
 const staff=document.body.dataset.tutorialStaff==='1';
 const steps=[
  {speaker:'Grey R.',path:'/skymiles',target:'.delta-dash-hero',title:'Welcome to SkyMiles',copy:'Welcome aboard, '+name+'! This is your personal dashboard, with your account overview and latest updates.'},
  {speaker:'Grey R.',path:'/skymiles',target:'#site-header',title:'Your Delta navigation',copy:'This top bar works across Delta Home, Flights, Forms, Partnerships and SkyMiles.'},
  {speaker:'Cookie',path:'/skymiles',target:'#sky-nav-dropdown > summary',open:'menu',title:'The Navigation Hub',copy:'Open MENU to reach every SkyMiles page, trips, rewards, profile tools and community links.'},
  {speaker:'Grey R.',path:'/skymiles',target:'.delta-account-menu > summary',open:'account',title:'Your Discord account',copy:'This is your verified Discord account dropdown. Find your profile, status, staff links (if eligible) and sign-out controls here.'},
  {speaker:'Cookie',path:'/skymiles',target:'.delta-balance-card',title:'Available SkyMiles',copy:'Your miles balance updates after eligible flight activity, rewards and authorized staff adjustments.'},
  {speaker:'Grey R.',path:'/skymiles',target:'.delta-qualification-card',title:'Medallion progress',copy:'MQP and flight segments track progress toward your next Medallion status tier.'},
  {speaker:'Grey R.',path:'/skymiles',target:'.delta-identity-card',title:'Your verified identity',copy:'You have one linked Roblox identity and a separate verified Discord identity.'},
  {speaker:'Cookie',path:'/flights',target:'.flight-terminal-content',title:'Current flights',copy:'Find upcoming hosted community flights here. If there are none, you will see the standby message.'},
  {speaker:'Grey R.',path:'/miles',target:'main',title:'Miles and Medallion status',copy:'Review your current balance, qualifying points and benefits for your membership tier.'},
  {speaker:'Cookie',path:'/trips',target:'main',title:'My Trips',copy:'Your booked trips and flight confirmations appear on this page.'},
  {speaker:'Cookie',path:'/activity',target:'main',title:'Activity history',copy:'See recorded transactions and keep track of how your virtual SkyMiles balance changes.'},
  {speaker:'Grey R.',path:'/rewards',target:'main',title:'Redeem rewards',copy:'Browse available community rewards and the SkyMiles required for each.'},
  {speaker:'Grey R.',path:'/profile',target:'main',title:'Your full profile',copy:'View the Discord and Roblox profiles associated with this SkyMiles membership.'},
  {speaker:'Cookie',path:'/settings',target:'main',title:'Account settings',copy:'Manage preferences and find the option to replay this tutorial.'},
  ...(staff?[{speaker:'Grey R.',path:'/skymiles',target:'#sky-nav-dropdown > summary',open:'menu',title:'Staff workspace',copy:'If your Discord roles authorize it, the Navigation Hub also contains your Owner, Admin or Staff panel.'}]:[]),
  {speaker:'Cookie',path:'/skymiles',target:'.delta-dash-hero-actions',title:'Ready to take off?',copy:'That is the full member tour! Explore the site and check back for new flights and benefits.'}
 ];
 const key='delta_skymiles_tour_progress';
 const progress=modal.querySelector('#tutorial-progress');
 const bar=modal.querySelector('#tutorial-progress-bar');
 const speakerLabel=modal.querySelector('#tutorial-speaker');
 const greyImg=modal.querySelector('#tutorial-avatar-grey');
 const cookieImg=modal.querySelector('#tutorial-avatar-cookie');
 const next=modal.querySelector('#tutorial-next');
 const back=modal.querySelector('#tutorial-back');
 const finish=modal.querySelector('#tutorial-finish');
 let i=0,highlighted=null;
 const stopHighlight=()=>{if(highlighted)highlighted.classList.remove('tutorial-target');highlighted=null;};
 const closeMenus=()=>{for(const id of ['sky-nav-dropdown','delta-account-menu']){const el=document.getElementById(id);if(el)el.open=false;}};
 function navigateTo(stepIndex){
   const step=steps[stepIndex];
   try{sessionStorage.setItem(key,String(stepIndex));}catch(_){}
   if(window.location.pathname!==step.path){
     window.location.assign(step.path+'?tutorial=1');return true;
   }
   return false;
 }
 function show(){
   if(i<0)i=0;if(i>=steps.length)i=steps.length-1;
   if(navigateTo(i))return;
   stopHighlight();closeMenus();
   const step=steps[i];
   if(step.open==='menu'){const menu=document.getElementById('sky-nav-dropdown');if(menu)menu.open=true;}
   if(step.open==='account'){const account=document.getElementById('delta-account-menu');if(account)account.open=true;}
   const cookie=step.speaker==='Cookie';
   greyImg.hidden=cookie;cookieImg.hidden=!cookie;
   speakerLabel.textContent=step.speaker;
   progress.textContent=(i+1)+' of '+steps.length;
   bar.style.width=((i+1)/steps.length*100).toFixed(1)+'%';
   modal.querySelector('#tutorial-heading').textContent=step.title;
   modal.querySelector('#tutorial-copy').textContent=step.copy;
   back.disabled=i===0;
   next.hidden=i===steps.length-1;
   finish.hidden=i!==steps.length-1;
   let el=document.querySelector(step.target);
   if(!el||el.getClientRects().length===0){el=document.querySelector('#sky-nav-dropdown > summary')||document.querySelector('main');}
   highlighted=el;
   if(el){el.classList.add('tutorial-target');
     if(step.target!=='#site-header')el.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
   }
 }
 function resume(index){
   i=Math.max(0,Math.min(index,steps.length-1));
   intro.hidden=true;guide.hidden=false;
   modal.classList.add('tutorial-active');
   show();
 }
 // The server only renders this script on a logged-in SkyMiles page.
 modal.show();
 modal.querySelector('#tutorial-start').addEventListener('click',()=>resume(0));
 next.addEventListener('click',()=>resume(i+1));
 back.addEventListener('click',()=>resume(i-1));
 finish.addEventListener('submit',()=>{try{sessionStorage.removeItem(key);}catch(_){}});
 modal.querySelector('.tutorial-intro form')?.addEventListener('submit',()=>{try{sessionStorage.removeItem(key);}catch(_){}});
 modal.addEventListener('close',stopHighlight);
 const existing=Number.parseInt(sessionStorage.getItem(key)||'',10);
 if(Number.isInteger(existing)&&existing>=0&&window.location.search.includes('tutorial=1'))resume(existing);
})();