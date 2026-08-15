const cfg = window.MOSTASHAR_CONFIG || { API_BASE: "" };
const API = (cfg.API_BASE || "").replace(/\/$/, "");

async function api(path, options={}) {
  const res = await fetch(API + path, {
    credentials: "include",
    ...options,
    headers: { "Accept":"application/json", ...(options.headers||{}) }
  });
  if (res.status === 401) {
    location.href = API ? API + "/login" : "/login";
    throw new Error("auth_required");
  }
  const body = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(body?.error?.message || body?.detail || "request_failed");
  return body.data;
}
function el(tag, text, cls="") {
  const n=document.createElement(tag); if(cls)n.className=cls;
  if(text!==undefined)n.textContent=text; return n;
}
function backendUrl(path) { return API ? API + path : path; }
function courseUrl(id) { return `./course.html?id=${encodeURIComponent(id)}`; }
function lessonUrl(id) { return `./lesson.html?id=${encodeURIComponent(id)}`; }
function lessonIdFromLocation() { const raw=new URLSearchParams(location.search).get("id") || ""; return /^\d+$/.test(raw) ? Number(raw) : 0; }
function courseIdFromLocation() {
  const raw=new URLSearchParams(location.search).get("id") || "";
  return /^\d+$/.test(raw) ? Number(raw) : 0;
}
async function setupSession() {
  const session=await api("/api/v1/session");
  if(session.role!=="student") throw new Error("student_account_required");
  const name=document.querySelector("#student-name"); if(name) name.textContent=session.name;
  const logout=document.querySelector("#logout");
  if(logout) logout.onclick=async()=>{
    await api("/api/v1/logout", {method:"POST", headers:{"X-CSRF-Token":session.csrf}});
    location.href = API ? API + "/login" : "/login";
  };
  return session;
}
async function bootDashboard() {
  const status=document.querySelector("#status");
  try {
    await setupSession();
    const [summary, courses] = await Promise.all([api("/api/v1/me/summary"), api("/api/v1/courses")]);
    document.querySelector("#active-courses").textContent=summary.active_courses;
    document.querySelector("#completed-lessons").textContent=summary.completed_lessons;
    document.querySelector("#quiz-attempts").textContent=summary.quiz_attempts;
    document.querySelector("#notifications").textContent=summary.unread_notifications;
    const list=document.querySelector("#courses"); list.replaceChildren();
    if (!courses.length) list.append(el("p","لا توجد كورسات نشطة حاليًا.","empty"));
    for (const c of courses) {
      const card=el("article",undefined,"course-card");
      card.append(el("h3",c.title), el("p",c.grade || "","muted"));
      const a=el("a","عرض الدروس","button-link"); a.href=courseUrl(c.id); card.append(a); list.append(card);
    }
    status.textContent="متصل";
  } catch (e) { status.textContent="تعذر تحميل البيانات"; console.error(e); }
}
async function bootCourse() {
  const status=document.querySelector("#status");
  const courseId=courseIdFromLocation();
  if(!courseId){ status.textContent="رابط الكورس غير صالح"; return; }
  try {
    await setupSession();
    const [course, lessons]=await Promise.all([
      api(`/api/v1/courses/${courseId}`),
      api(`/api/v1/courses/${courseId}/lessons`)
    ]);
    document.title=`${course.title} | المستشار`;
    document.querySelector("#course-title").textContent=course.title;
    document.querySelector("#course-grade").textContent=course.grade || "";
    document.querySelector("#course-crumb").textContent=course.title;
    const list=document.querySelector("#lessons"); list.replaceChildren();
    if(!lessons.length) list.append(el("p","لا توجد دروس متاحة حاليًا.","empty"));
    for(const lesson of lessons){
      const row=el("article",undefined,`lesson-row ${lesson.unlocked?"":"locked"}`);
      const info=el("div");
      info.append(el("h3",`${lesson.completed?"✓ ":""}${lesson.title}`));
      if(!lesson.unlocked) info.append(el("p",lesson.lock_reason || "الدرس غير متاح حاليًا","muted"));
      row.append(info);
      if(lesson.unlocked && lesson.launch_url){
        const a=el("a","فتح الدرس","button-link"); a.href=lessonUrl(lesson.id); row.append(a);
      } else {
        const badge=el("span","مغلق","lock-badge"); row.append(badge);
      }
      list.append(row);
    }
    status.textContent="متصل";
  } catch(e){ status.textContent="تعذر تحميل الكورس"; console.error(e); }
}


function installLessonProtection(root, watermark) {
  const grid=document.querySelector("#watermark-grid"), moving=document.querySelector("#moving-watermark"), videoWm=document.querySelector("#video-watermark");
  if(grid){ grid.replaceChildren(); for(let i=0;i<15;i++) grid.append(el("span",watermark)); }
  if(moving) moving.textContent=watermark;
  if(videoWm) videoWm.textContent=watermark;
  function move(node, zone){ if(!node||!zone)return; const x=Math.max(8,Math.floor(Math.random()*Math.max(9,zone.clientWidth-node.offsetWidth-16))); const y=Math.max(8,Math.floor(Math.random()*Math.max(9,zone.clientHeight-node.offsetHeight-16))); node.style.transform=`translate(${x}px,${y}px) rotate(-8deg)`; }
  const playerZone=document.querySelector("#player-zone");
  const moveAll=()=>{ move(moving,root); move(videoWm,playerZone); };
  moveAll(); setInterval(moveAll,7000);
  root.addEventListener("contextmenu",e=>e.preventDefault()); root.addEventListener("copy",e=>e.preventDefault()); root.addEventListener("dragstart",e=>e.preventDefault());
  document.addEventListener("keydown",e=>{ const k=String(e.key||"").toLowerCase(); const blocked=e.key==="PrintScreen"||((e.ctrlKey||e.metaKey)&&["s","p","u"].includes(k))||(e.ctrlKey&&e.shiftKey&&["i","j","c"].includes(k)); if(blocked){e.preventDefault(); document.body.classList.add("capture-warning"); setTimeout(()=>document.body.classList.remove("capture-warning"),1200);} },true);
}
async function postProgress(lessonId, csrf, completed=false, watchedSeconds=0){
  return api(`/api/lesson/${lessonId}/progress`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({csrf,completed,watched_seconds:watchedSeconds})});
}
async function bootLesson(){
  const status=document.querySelector("#status"), lessonId=lessonIdFromLocation();
  if(!lessonId){ status.textContent="رابط الدرس غير صالح"; return; }
  try{
    const session=await setupSession();
    const data=await api(`/api/v1/lessons/${lessonId}/experience`);
    document.title=`${data.title} | المستشار`; document.querySelector("#lesson-title").textContent=data.title; document.querySelector("#lesson-crumb").textContent=data.title;
    const courseLink=document.querySelector("#course-link"); courseLink.href=courseUrl(data.course_id); courseLink.textContent="العودة للكورس";
    const root=document.querySelector("#protected-root"); root.hidden=false; root.dataset.watermark=data.watermark; installLessonProtection(root,data.watermark);
    document.querySelector("#lesson-body").textContent=data.body || "لا يوجد شرح نصي مضاف لهذا الدرس.";
    const playerCard=document.querySelector("#player-card"), zone=document.querySelector("#player-zone"), ps=document.querySelector("#player-status");
    if(data.playback.kind!=="none"){
      playerCard.hidden=false;
      if(data.playback.kind==="cloudflare"){
        const frame=document.createElement("iframe"); frame.src=backendUrl(data.playback.url); frame.allow="encrypted-media; autoplay; picture-in-picture"; frame.referrerPolicy="strict-origin"; frame.title="مشغل Cloudflare Stream المحمي"; zone.append(frame); ps.textContent="Cloudflare Secure";
      }else if(data.playback.kind==="direct_proxy"){
        const v=document.createElement("video"); v.src=backendUrl(data.playback.url); v.controls=true; v.playsInline=true; v.preload="metadata"; v.setAttribute("controlslist","nodownload noplaybackrate nofullscreen"); v.disablePictureInPicture=true; zone.append(v); ps.textContent="Protected Proxy";
        let last=0; v.addEventListener("timeupdate",()=>{ const now=Math.floor(v.currentTime||0); if(now-last>=20){last=now; postProgress(lessonId,session.csrf,false,now).catch(()=>{});} });
      }else if(data.playback.kind==="backend_only"){
        const box=el("div","هذا النوع من الفيديو ما زال يعمل عبر صفحة الـBackend المحمية لحين نقله إلى Stream/DRM.","error-box"); const a=el("a","فتح المشغل المحمي","button-link"); a.href=backendUrl(data.playback.url); box.append(document.createElement("br"),a); zone.append(box); ps.textContent="Backend protected";
      }else{ zone.append(el("div","إعداد مشغل Cloudflare غير مكتمل. راجع إعداد CF_EDGE_SIGNING_SECRET.","error-box")); ps.textContent="غير جاهز"; }
    }
    const cps=data.checkpoints||[], cpSec=document.querySelector("#checkpoints-section"), cpList=document.querySelector("#checkpoints");
    if(cps.length){cpSec.hidden=false; for(const cp of cps){
      const box=el("article",undefined,"checkpoint-item"); box.append(el("strong",`${Math.floor(cp.timestamp_seconds/60)}:${String(cp.timestamp_seconds%60).padStart(2,"0")} — ${cp.question}`));
      const opts=el("div",undefined,"checkpoint-options");
      for(const [key,val] of Object.entries(cp.options)){ const lab=document.createElement("label"), input=document.createElement("input"); input.type="radio"; input.name=`cp-${cp.id}`; input.value=key; if(cp.selected===key)input.checked=true; lab.append(input,el("span",val)); opts.append(lab);} box.append(opts);
      const result=el("div",undefined,"checkpoint-result");
      if(cp.answered){ result.className=cp.is_correct?"success-box":"error-box"; result.textContent=cp.is_correct?"تمت الإجابة بشكل صحيح":`الإجابة السابقة غير صحيحة${cp.explanation?" — "+cp.explanation:""}`; }
      const submit=el("button",cp.answered?"تحديث الإجابة":"تحقق من الإجابة","button-link small-button"); submit.type="button";
      submit.onclick=async()=>{ const selected=box.querySelector(`input[name="cp-${cp.id}"]:checked`); if(!selected){result.className="error-box"; result.textContent="اختر إجابة أولًا"; return;} submit.disabled=true; try{const out=await api(`/api/v1/lessons/${lessonId}/checkpoints/${cp.id}/answer`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify({answer:selected.value})}); result.className=out.is_correct?"success-box":"error-box"; result.textContent=out.is_correct?`إجابة صحيحة${out.explanation?" — "+out.explanation:""}`:`إجابة غير صحيحة${out.explanation?" — "+out.explanation:""}`; submit.textContent="تحديث الإجابة";}catch(e){result.className="error-box"; result.textContent=e.message||"تعذر تسجيل الإجابة";}finally{submit.disabled=false;}};
      box.append(submit,result); cpList.append(box);
    } }
    const fcs=data.flashcards||[], fcSec=document.querySelector("#flashcards-section"), fcList=document.querySelector("#flashcards"); if(fcs.length){fcSec.hidden=false; for(const c of fcs){const d=document.createElement("details"); d.className="mini-card"; const sum=document.createElement("summary"); sum.textContent=c.front; d.append(sum,el("p",c.back)); fcList.append(d);}}
    const hws=data.homeworks||[], hwSec=document.querySelector("#homework-section"), hwList=document.querySelector("#homeworks"); if(hws.length){hwSec.hidden=false; for(const h of hws){const box=el("article",undefined,"homework-item"); box.append(el("h3",h.title),el("p",h.instructions,"muted")); const a=el("a","فتح الواجب","button-link"); a.href=backendUrl(h.launch_url); box.append(a); hwList.append(box);}}
    const assets=data.assets||[], asSec=document.querySelector("#assets-section"), asList=document.querySelector("#assets"); if(assets.length){asSec.hidden=false; for(const a0 of assets){const box=el("article",undefined,"mini-card"); box.append(el("h3",a0.name),el("p",a0.mime_type||"ملف محمي","muted")); const a=el("a","فتح المحتوى","button-link"); a.href=backendUrl(a0.launch_url); a.target="_blank"; a.rel="noopener"; box.append(a); asList.append(box);}}
    const assistantForm=document.querySelector("#assistant-form"), assistantAnswer=document.querySelector("#assistant-answer");
    assistantForm.onsubmit=async(e)=>{e.preventDefault(); const q=document.querySelector("#assistant-question").value.trim(); if(q.length<2)return; const btn=assistantForm.querySelector("button"); btn.disabled=true; assistantAnswer.hidden=false; assistantAnswer.textContent="جاري تجهيز الإجابة..."; try{const out=await api(`/api/v1/lessons/${lessonId}/assistant`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify({question:q,mode:document.querySelector("#assistant-mode").value})}); assistantAnswer.textContent=out.answer;}catch(err){assistantAnswer.textContent=err.message||"تعذر الحصول على الإجابة";}finally{btn.disabled=false;}};
    const discussionList=document.querySelector("#discussion"), discussionForm=document.querySelector("#discussion-form");
    async function loadDiscussion(){const posts=await api(`/api/v1/lessons/${lessonId}/discussion`); discussionList.replaceChildren(); if(!posts.length){discussionList.append(el("p","لا توجد مشاركات بعد.","muted"));return;} for(const p of posts){const card=el("article",undefined,"discussion-post"); card.append(el("strong",p.author),el("p",p.body)); if(p.created_at)card.append(el("small",new Date(p.created_at).toLocaleString("ar-EG"),"muted")); discussionList.append(card);}}
    discussionForm.onsubmit=async(e)=>{e.preventDefault(); const body=document.querySelector("#discussion-body").value.trim(); if(body.length<2)return; const btn=discussionForm.querySelector("button"); btn.disabled=true; try{await api(`/api/v1/lessons/${lessonId}/discussion`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify({body})}); document.querySelector("#discussion-body").value=""; await loadDiscussion();}catch(err){alert(err.message||"تعذر نشر المشاركة");}finally{btn.disabled=false;}};
    await loadDiscussion();
    const fallback=document.querySelector("#backend-fallback"); fallback.href=backendUrl(data.backend_fallback_url);
    const complete=document.querySelector("#complete-lesson"); complete.textContent=data.completed?"✓ الدرس مكتمل":"تم إكمال الدرس"; complete.disabled=!!data.completed; complete.onclick=async()=>{ complete.disabled=true; try{await postProgress(lessonId,session.csrf,true,data.watched_seconds||0); complete.textContent="✓ تم تسجيل إكمال الدرس";}catch(e){complete.disabled=false; complete.textContent="تعذر التسجيل — حاول مرة أخرى";}};
    status.textContent="متصل — محتوى محمي";
  }catch(e){status.textContent="تعذر تحميل الدرس"; console.error(e); const root=document.querySelector("#protected-root"); root.hidden=false; root.replaceChildren(el("div",e.message||"تعذر تحميل الدرس","error-box"));}
}

document.addEventListener("DOMContentLoaded",()=>{
  const page=document.body.dataset.page || "dashboard";
  if(page==="lesson") bootLesson(); else if(page==="course") bootCourse(); else if(page==="learning") bootLearning(); else if(page==="quiz") bootQuiz(); else if(page==="homework") bootHomework(); else bootDashboard();
});
function queryId(){const raw=new URLSearchParams(location.search).get("id")||"";return /^\d+$/.test(raw)?Number(raw):0;}
function quizUrl(id){return `./quiz.html?id=${encodeURIComponent(id)}`;}
function homeworkUrl(id){return `./homework.html?id=${encodeURIComponent(id)}`;}
function fmtDate(v){if(!v)return "";try{return new Date(v).toLocaleString("ar-EG");}catch{return v;}}
async function bootLearning(){
 const status=document.querySelector("#status"); try{const session=await setupSession(); const [hub,plan,notes]=await Promise.all([api("/api/v1/learning-center"),api("/api/v1/study-plan"),api("/api/v1/notifications")]);
 document.querySelector("#learning-unread").textContent=hub.unread_notifications; document.querySelector("#study-points").textContent=plan.points;
 const tasks=document.querySelector("#study-tasks"); tasks.replaceChildren(); for(const t of plan.tasks){const c=el("article",undefined,"mini-card"); c.append(el("strong",t.title),el("p",t.type==="lesson"?"درس":"واجب","muted"));const a=el("a","فتح","button-link");a.href=t.type==="lesson"?`./lesson.html?id=${t.id}`:homeworkUrl(t.id);c.append(a);tasks.append(c);} if(!plan.tasks.length)tasks.append(el("p","لا توجد مهام حالية.","muted"));
 const ql=document.querySelector("#quiz-list"); ql.replaceChildren(); for(const q of hub.quizzes){const c=el("article",undefined,"mini-card");c.append(el("strong",q.title),el("p",`المحاولات ${q.attempts_used}/${q.max_attempts}${q.best_score!==null?` — أفضل نتيجة ${Math.round(q.best_score)}%`:""}`,"muted"));const a=el("a","بدء / متابعة","button-link");a.href=quizUrl(q.id);c.append(a);ql.append(c);} if(!hub.quizzes.length)ql.append(el("p","لا توجد اختبارات متاحة.","muted"));
 const hl=document.querySelector("#homework-list");hl.replaceChildren();for(const h of hub.homeworks){const c=el("article",undefined,"mini-card");c.append(el("strong",h.title),el("p",`${h.status}${h.due_at?` — حتى ${fmtDate(h.due_at)}`:""}`,"muted"));const a=el("a","فتح الواجب","button-link");a.href=homeworkUrl(h.id);c.append(a);hl.append(c);} if(!hub.homeworks.length)hl.append(el("p","لا توجد واجبات متاحة.","muted"));
 const nl=document.querySelector("#notification-list"); function renderNotes(items){nl.replaceChildren();for(const n of items){const c=el("article",undefined,`mini-card ${n.read?"":"unread"}`);c.append(el("strong",n.title),el("p",n.body));nl.append(c);}if(!items.length)nl.append(el("p","لا توجد إشعارات.","muted"));} renderNotes(notes);
 document.querySelector("#read-all").onclick=async()=>{await api("/api/v1/notifications/read-all",{method:"POST",headers:{"X-CSRF-Token":session.csrf}});renderNotes(notes.map(n=>({...n,read:true})));document.querySelector("#learning-unread").textContent="0";};
 document.querySelector("#search-form").onsubmit=async e=>{e.preventDefault();const q=document.querySelector("#search-q").value.trim();const out=await api(`/api/v1/search?q=${encodeURIComponent(q)}`);const r=document.querySelector("#search-results");r.replaceChildren();for(const x of out.courses){const a=el("a",`كورس: ${x.title}`,"mini-card");a.href=courseUrl(x.id);r.append(a);}for(const x of out.lessons){const a=el("a",`درس: ${x.title}`,"mini-card");a.href=lessonUrl(x.id);r.append(a);}for(const x of out.quizzes){const a=el("a",`اختبار: ${x.title}`,"mini-card");a.href=quizUrl(x.id);r.append(a);}if(!r.children.length)r.append(el("p","لا توجد نتائج.","muted"));}; status.textContent="متصل";
 }catch(e){status.textContent=e.message||"تعذر تحميل مركز التعلم";console.error(e);}}
async function bootQuiz(){const status=document.querySelector("#status"),id=queryId();if(!id){status.textContent="رابط غير صالح";return;}try{const session=await setupSession(),data=await api(`/api/v1/quizzes/${id}/attempt`);document.querySelector("#quiz-title").textContent=data.quiz.title;const list=document.querySelector("#quiz-questions");for(const [i,q] of data.questions.entries()){const c=el("article",undefined,"mini-card");c.append(el("strong",`${i+1}. ${q.text}`));for(const [k,v] of Object.entries(q.options)){const lab=document.createElement("label"),inp=document.createElement("input");inp.type="radio";inp.name=`q-${q.id}`;inp.value=k;lab.append(inp,el("span",`${k}) ${v}`));c.append(lab);}list.append(c);}let left=data.remaining_seconds;const timer=document.querySelector("#quiz-timer");const tick=()=>{timer.textContent=`${Math.floor(left/60)}:${String(left%60).padStart(2,"0")}`;if(left<=0){clearInterval(int);document.querySelector("#quiz-submit").disabled=true;}left--;};tick();const int=setInterval(tick,1000);document.querySelector("#quiz-form").onsubmit=async e=>{e.preventDefault();const answers={};for(const q of data.questions){const x=document.querySelector(`input[name="q-${q.id}"]:checked`);if(x)answers[String(q.id)]=x.value;}const out=await api(`/api/v1/quizzes/${id}/submit`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify({answers})});clearInterval(int);document.querySelector("#quiz-form").hidden=true;const r=document.querySelector("#quiz-result");r.hidden=false;r.className=out.percentage>=80?"success-box":"mini-card";r.textContent=`النتيجة: ${out.score}/${out.total} — ${out.percentage}%`;};status.textContent="متصل";}catch(e){status.textContent=e.message||"تعذر فتح الاختبار";}}
async function bootHomework(){const status=document.querySelector("#status"),id=queryId();if(!id){status.textContent="رابط غير صالح";return;}try{const session=await setupSession(),h=await api(`/api/v1/homeworks/${id}`);document.querySelector("#homework-title").textContent=h.title;document.querySelector("#homework-instructions").textContent=h.instructions||"لا توجد تعليمات إضافية";document.querySelector("#homework-due").textContent=h.due_at?`موعد التسليم: ${fmtDate(h.due_at)}`:"";if(h.submission){document.querySelector("#homework-answer").value=h.submission.answer_text||"";const fb=document.querySelector("#homework-feedback");fb.className="mini-card";fb.textContent=`الحالة: ${h.submission.status}${h.submission.score!==null?` — الدرجة ${h.submission.score}/100`:""}${h.submission.feedback?` — ${h.submission.feedback}`:""}`;}document.querySelector("#homework-form").onsubmit=async e=>{e.preventDefault();const answer=document.querySelector("#homework-answer").value;await api(`/api/v1/homeworks/${id}/submit`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":session.csrf},body:JSON.stringify({answer_text:answer})});const fb=document.querySelector("#homework-feedback");fb.className="success-box";fb.textContent="تم حفظ وتسليم الواجب.";};status.textContent="متصل";}catch(e){status.textContent=e.message||"تعذر فتح الواجب";}}
