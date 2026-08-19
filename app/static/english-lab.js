(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const core = window.MostasharEnglishLabCore;
  if (!core) throw new Error('english_lab_core_missing');
  const speak = (text) => {
    if (!text || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text); u.lang = 'en-US'; u.rate = 0.88;
    window.speechSynthesis.speak(u);
  };
  document.querySelectorAll('[data-target]').forEach(btn => btn.addEventListener('click', () => {
    const target = $(btn.dataset.target); if (!target) return;
    document.querySelectorAll('[data-lab-panel]').forEach(x => x.classList.remove('active'));
    target.classList.add('active');
    document.querySelectorAll('[data-target]').forEach(x => x.classList.toggle('active', x === btn));
    target.scrollIntoView({behavior:'smooth', block:'start'});
    history.replaceState(null, '', '#' + btn.dataset.target);
  }));
  const hash = location.hash.slice(1);
  const hashButton = [...document.querySelectorAll('[data-target]')].find(b => b.dataset.target === hash);
  if (hashButton) hashButton.click();

  function renderTense(){
    const s=$('lab-subject').value, v=$('lab-verb').value, t=$('lab-tense').value;
    const result=core.tenseForms(s,v,t);
    $('lab-positive').textContent=result.positive;
    $('lab-negative').textContent=result.negative;
    $('lab-question').textContent=result.question;
    $('lab-formula').innerHTML=`<span>${s}</span><b>${result.formulaVerb}</b>`;
    $('lab-tip').textContent=result.tip;
  }
  ['lab-subject','lab-verb','lab-tense'].forEach(id => $(id).addEventListener('change', renderTense));
  document.querySelectorAll('[data-speak-id]').forEach(b => b.addEventListener('click',()=>speak($(b.dataset.speakId).textContent))); renderTense();

  const flash=[['achieve','يحقق','She worked hard to achieve her goal.'],['confident','واثق','He feels confident before the exam.'],['improve','يحسّن','Practice can improve your speaking.'],['challenge','تحدٍ','Every challenge can teach you something.'],['accurate','دقيق','Try to give an accurate answer.'],['communicate','يتواصل','English helps us communicate with others.']]; let fi=0, revealed=false;
  function renderFlash(){const x=flash[fi]; $('flash-label').textContent=`Word ${fi+1} / ${flash.length}`;$('flash-word').textContent=x[0];$('flash-meaning').textContent=revealed?x[1]:'اضغط للكشف عن المعنى';$('flash-example').textContent=revealed?x[2]:'';}
  const flip=()=>{revealed=!revealed;renderFlash();}; $('flashcard').addEventListener('click',flip); $('flashcard').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();flip();}}); $('flash-flip').addEventListener('click',flip); $('flash-next').addEventListener('click',()=>{fi=(fi+1)%flash.length;revealed=false;renderFlash();}); $('flash-speak').addEventListener('click',()=>speak(flash[fi][0])); renderFlash();

  const quizzes=[
    {q:'Choose the correct sentence:',o:['He go to school every day.','He goes to school every day.','He going to school every day.'],a:1},
    {q:'The past of “write” is …',o:['writed','wrote','written'],a:1},
    {q:'Choose the correct negative:',o:["She doesn't like coffee.","She don't likes coffee.","She not like coffee."],a:0},
    {q:'“confident” means …',o:['واثق','مرهق','نادر'],a:0}
  ]; let qi=0;
  function renderQuiz(){const q=quizzes[qi];$('quiz-question').textContent=q.q;$('quiz-options').innerHTML='';$('quiz-feedback').textContent='';q.o.forEach((x,i)=>{const b=document.createElement('button');b.type='button';b.textContent=x;b.addEventListener('click',()=>{$('quiz-feedback').textContent=i===q.a?'✅ إجابة صحيحة':'❌ جرّب مرة أخرى';$('quiz-feedback').className=i===q.a?'ok':'bad';});$('quiz-options').appendChild(b);});}
  $('quiz-next').addEventListener('click',()=>{qi=(qi+1)%quizzes.length;renderQuiz();}); renderQuiz();

  const builds=[['She','studies','English','every','day.'],['They','are','watching','a','lesson','now.'],['Did','you','finish','your','homework?']]; let bi=0, chosen=[];
  function renderBuild(){chosen=[]; const words=[...builds[bi]].sort(()=>Math.random()-.5);$('builder-source').innerHTML='';$('builder-answer').textContent='اضغط الكلمات لتكوين الجملة';$('builder-feedback').textContent='';words.forEach(w=>{const b=document.createElement('button');b.type='button';b.textContent=w;b.addEventListener('click',()=>{if(b.disabled)return;b.disabled=true;chosen.push(w);$('builder-answer').textContent=chosen.join(' ');});$('builder-source').appendChild(b);});}
  $('builder-check').addEventListener('click',()=>{$('builder-feedback').textContent=chosen.join(' ')===builds[bi].join(' ')?'✅ ممتاز! الترتيب صحيح.':'❌ الترتيب محتاج تعديل.';});$('builder-reset').addEventListener('click',renderBuild);$('builder-new').addEventListener('click',()=>{bi=(bi+1)%builds.length;renderBuild();});renderBuild();

  $('speak-play').addEventListener('click',()=>speak($('speak-target').textContent));
  $('speak-check').addEventListener('click',()=>{const a=core.normalizeSentence($('speak-input').value), b=core.normalizeSentence($('speak-target').textContent);$('speak-feedback').textContent=a===b?'✅ ممتاز — الجملة مطابقة.':'حاول مرة أخرى بعد الاستماع للجملة.';});
  $('speak-record').addEventListener('click',()=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){$('speak-feedback').textContent='المتصفح لا يدعم التعرف على الصوت؛ استخدم خانة الكتابة.';return;}const r=new SR();r.lang='en-US';r.interimResults=false;r.onresult=e=>{$('speak-input').value=e.results[0][0].transcript;$('speak-check').click();};r.onerror=()=>{$('speak-feedback').textContent='تعذر الوصول للميكروفون. يمكنك الكتابة بدلًا منه.';};r.start();});

  const listens=[{s:'The student finished his homework before dinner.',o:['أنهى الطالب واجبه قبل العشاء.','بدأ الطالب واجبه بعد العشاء.','نسي الطالب كتابه.'],a:0},{s:'Mona is preparing for her English exam.',o:['منى تستعد لامتحان الإنجليزي.','منى أنهت الامتحان.','منى لا تدرس الإنجليزي.'],a:0}]; let li=0;
  function renderListen(){const x=listens[li];$('listening-options').innerHTML='';$('listening-feedback').textContent='';x.o.forEach((t,i)=>{const b=document.createElement('button');b.type='button';b.textContent=t;b.addEventListener('click',()=>{$('listening-feedback').textContent=i===x.a?'✅ صحيح':'❌ استمع مرة أخرى';});$('listening-options').appendChild(b);});}
  $('listening-play').addEventListener('click',()=>speak(listens[li].s));$('listening-next').addEventListener('click',()=>{li=(li+1)%listens.length;renderListen();});renderListen();

  const verbs=[['be','was/were','been'],['begin','began','begun'],['break','broke','broken'],['do','did','done'],['drink','drank','drunk'],['eat','ate','eaten'],['go','went','gone'],['have','had','had'],['see','saw','seen'],['take','took','taken'],['write','wrote','written']];
  function renderVerbs(){const q=$('irregular-search').value.toLowerCase().trim();const rows=verbs.filter(v=>v.some(x=>x.includes(q)));$('irregular-table').innerHTML='<div><b>Base</b><b>Past</b><b>Past Participle</b></div>'+rows.map(v=>`<div><span>${v[0]}</span><span>${v[1]}</span><span>${v[2]}</span></div>`).join('');} $('irregular-search').addEventListener('input',renderVerbs);renderVerbs();

  const matchPairs=[['achieve','يحقق'],['support','يدعم'],['careful','حريص'],['improve','يحسن']]; let selected=null,matched=new Set();
  function renderMatch(){selected=null;matched=new Set();const items=[...matchPairs.map((p,i)=>({t:p[0],i,side:'en'})),...matchPairs.map((p,i)=>({t:p[1],i,side:'ar'}))].sort(()=>Math.random()-.5);$('matching-board').innerHTML='';$('matching-feedback').textContent='';items.forEach(x=>{const b=document.createElement('button');b.type='button';b.textContent=x.t;b.dataset.idx=x.i;b.dataset.side=x.side;b.addEventListener('click',()=>{if(b.classList.contains('matched'))return;if(!selected){selected=b;b.classList.add('selected');return;}if(selected===b)return;if(selected.dataset.side!==b.dataset.side && selected.dataset.idx===b.dataset.idx){selected.classList.remove('selected');selected.classList.add('matched');b.classList.add('matched');matched.add(x.i);$('matching-feedback').textContent=matched.size===matchPairs.length?'🎉 ممتاز! خلصت كل التوصيلات.':'✅ تطابق صحيح';selected=null;}else{selected.classList.remove('selected');selected=null;$('matching-feedback').textContent='❌ حاول تطابق مختلف';}});$('matching-board').appendChild(b);});} $('matching-reset').addEventListener('click',renderMatch);renderMatch();

  document.querySelectorAll('#reading-options button').forEach(b=>b.addEventListener('click',()=>{$('reading-feedback').textContent=b.dataset.correct==='1'?'✅ إجابة صحيحة':'❌ راجع القطعة مرة أخرى';}));

  const words=['grammar','vocabulary','speaking','reading','english','practice'];let wi=0;function renderLetters(){const w=words[wi];$('letters-scramble').textContent=w.split('').sort(()=>Math.random()-.5).join(' · ');$('letters-input').value='';$('letters-feedback').textContent='';}$('letters-check').addEventListener('click',()=>{$('letters-feedback').textContent=$('letters-input').value.trim().toLowerCase()===words[wi]?'✅ ممتاز!':'❌ جرّب مرة أخرى';});$('letters-new').addEventListener('click',()=>{wi=(wi+1)%words.length;renderLetters();});renderLetters();
})();
