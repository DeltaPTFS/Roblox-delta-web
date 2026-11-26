/* All answers remain in the browser. This is a virtual-card preference guide, not a financial application. */
(function () {
  'use strict';
  const questions = [
    {text:'First things first: is this card for personal or business use?', options:[['personal','Personal'],['business','External Affairs Partnership']]},
    {text:'How often do you fly with Delta Roblox?', options:[['low','1–2x per year'],['medium','3–5x per year'],['high','6+ times per year']]},
    {text:'Which cabin do you usually choose?', options:[['main','Delta Main Basic / Delta Main'],['comfort','Delta Comfort'],['first','Delta First']]},
    {text:'How do you feel about annual Robux fees?', options:[['none','No annual fee'],['500','Up to 500 Robux'],['1000','Up to 1,000 Robux'],['2000','Up to 2,000 Robux for premium travel']]}
  ];
  function match(answers) {
    if (answers[0] === 'business') return 'business';
    if (answers[3] === 'none') return 'blue';
    if (answers[3] === '500') return 'gold';
    if (answers[3] === '1000') return 'platinum';
    const score = (answers[1]==='high'?2:answers[1]==='medium'?1:0)+(answers[2]==='first'?2:answers[2]==='comfort'?1:0);
    return score >= 2 ? 'reserve' : 'platinum';
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {match,questions};
  if (typeof document === 'undefined') return;
  const $ = id => document.getElementById(id);
  const shell=$('amex-quiz'); if(!shell)return;
  const form=$('amex-quiz-form'), next=$('amex-quiz-next'), back=$('amex-quiz-back'), options=$('amex-quiz-options');
  let step=0, answers=[], mode='personal';
  const result=$('amex-quiz-result');
  const results={
    reserve:['SkyMiles Reserve','2,000 Robux annually. Includes virtual Sky Club access when flying Delta and 3X miles on Delta purchases. Your travel preferences suggest exploring the highest card offering.','reserve'],
    platinum:['SkyMiles Platinum','1,000 Robux annually. Includes increased SkyMiles earnings and is a middle ground for price-conscious travelers.','platinum'],
    blue:['SkyMiles Blue','0 Robux annually. Earn 2X miles on Delta and eligible Delta partners.','blue'],
    gold:['SkyMiles Gold','500 Robux annually. Includes Zone 5 priority boarding, a first-flight Comfort Plus upgrade and a second-flight First Class upgrade.','gold'],
    business:['External Affairs Partnership','Business Cards are intended for External Affairs partnerships. Contact our team on Discord to discuss partnership arrangements, eligibility and benefits.','']
  };
  function setMode(value) {
    mode=value==='business'?'business':'personal';
    document.querySelectorAll('[data-card-panel]').forEach(el=>el.hidden=el.dataset.cardPanel!==mode);
    document.querySelectorAll('.amex-product-tabs [data-card-tab]').forEach(el=>{if(el.dataset.cardTab===mode)el.setAttribute('aria-current','true');else el.removeAttribute('aria-current');});
    document.querySelectorAll('[data-featured-link]').forEach(el=>{el.href=mode==='business'?'#business':'#personal';el.textContent=mode==='business'?'Explore Business Cards':'Explore Featured Cards';});
    document.querySelectorAll('[data-compare-link]').forEach(el=>{el.href=mode==='business'?'#business':'#compare';el.textContent=mode==='business'?'Partnership Inquiries':'Compare Cards';});
    $('amex-offer-copy').textContent=mode==='business'?'Business Cards are for External Affairs partnerships. Contact our team on Discord for partnership arrangements and any applicable offers.':'Explore welcome offers for Blue, Gold and Reserve. Promotional offers may vary; compare current virtual benefits below.';
  }
  document.querySelectorAll('[data-card-tab]').forEach(el=>el.addEventListener('click',()=>setMode(el.dataset.cardTab)));
  function followHash(){const hash=location.hash;if(hash==='#business')setMode('business');else if(['#personal','#compare','#registration'].includes(hash))setMode('personal');}
  window.addEventListener('hashchange',followHash);setMode(location.hash==='#business'?'business':'personal');
  function render(focus=false) {
    result.hidden=true; form.hidden=false; back.hidden=step===0;
    shell.classList.toggle('is-expanded',step>0);
    $('amex-quiz-question').textContent=questions[step].text;
    options.replaceChildren();
    questions[step].options.forEach(([value,label])=>{
      const wrapper=document.createElement('label'), input=document.createElement('input');
      input.type='radio';input.name='quiz-answer';input.value=value;input.checked=answers[step]===value;
      wrapper.append(input,document.createTextNode(label));options.append(wrapper);
    });
    next.disabled=!answers[step];next.textContent=step===3?'See Your Best Match ›':'Next ›';
    shell.querySelectorAll('.amex-quiz-progress i').forEach((el,i)=>el.classList.toggle('is-filled',i<=step));
    $('amex-quiz-count').textContent='QUESTION '+(step+1)+'/4';
    if(focus)$('amex-quiz-question').focus();
  }
  options.addEventListener('change',e=>{if(e.target.name==='quiz-answer'){answers[step]=e.target.value;next.disabled=false;}});
  form.addEventListener('submit',e=>{
    e.preventDefault();if(!answers[step])return;
    if(step<3){step++;render(true);return;}
    const key=match(answers),r=results[key],img=$('amex-quiz-card');
    form.hidden=true;back.hidden=false;shell.classList.add('is-expanded');
    $('amex-quiz-result-title').textContent=r[0];$('amex-quiz-result-copy').textContent=r[1];
    img.hidden=!r[2];img.querySelectorAll('[data-card-face]').forEach(face=>{face.hidden=face.dataset.cardFace!==r[2];});
    $('amex-quiz-result-link').textContent=key==='business'?'Contact External Affairs on Discord':key==='none'?'Ask about options on Discord':'Register on Discord';
    result.hidden=false;result.focus();
  });
  back.addEventListener('click',()=>{if(!result.hidden){render(true);return;}if(step>0){step--;render(true);}});
  $('amex-quiz-restart').addEventListener('click',()=>{step=0;answers=[];render(true);});
  const compareBack=document.querySelector('.amex-compare-back'), compareScroll=document.querySelector('.amex-comparison-scroll');
  if(compareBack && compareScroll) compareBack.addEventListener('click',()=>{compareScroll.scrollTop=0;});
  render();
})();
