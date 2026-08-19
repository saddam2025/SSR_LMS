(function(root, factory){
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MostasharEnglishLabCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
  'use strict';
  const irregularPast = {go:'went',write:'wrote',have:'had',do:'did',be:'was/were',begin:'began',break:'broke',drink:'drank',eat:'ate',see:'saw',take:'took'};
  const regularPast = v => v.endsWith('e') ? v+'d' : (v.endsWith('y') && !/[aeiou]y$/.test(v) ? v.slice(0,-1)+'ied' : v+'ed');
  const thirdPerson = v => v === 'have' ? 'has' : (v === 'do' ? 'does' : (/(s|sh|ch|x|o)$/.test(v) ? v+'es' : (v.endsWith('y') && !/[aeiou]y$/.test(v) ? v.slice(0,-1)+'ies' : v+'s')));
  const ing = v => v.endsWith('ie') ? v.slice(0,-2)+'ying' : (v.endsWith('e') && !v.endsWith('ee') ? v.slice(0,-1)+'ing' : v+'ing');
  const lowerSubject = s => String(s || '').toLowerCase();
  const normalizeSentence = s => String(s || '').toLowerCase().replace(/[^a-z ]/g,'').replace(/\s+/g,' ').trim();
  function tenseForms(subject, verb, tense){
    const s=String(subject||'').trim(), v=String(verb||'').trim();
    if(!s || !v) throw new Error('subject_and_verb_required');
    const he=/^(He|She|It)$/.test(s); let positive='',negative='',question='',formulaVerb='',tip='';
    if(tense==='present-simple'){
      const fv=he?thirdPerson(v):v, aux=he?'does':'do';
      positive=`${s} ${fv}.`; negative=`${s} ${aux}n't ${v}.`; question=`${aux[0].toUpperCase()+aux.slice(1)} ${lowerSubject(s)} ${v}?`; formulaVerb=fv;
      tip=he?'💡 مع he/she/it في المضارع البسيط نضيف s/es للفعل، والنفي والسؤال يستخدمان does + المصدر.':'💡 مع I/we/they في المضارع البسيط نستخدم المصدر، والنفي والسؤال يستخدمان do + المصدر.';
    } else if(tense==='present-continuous'){
      const be=s==='I'?'am':(he?'is':'are'), iv=ing(v);
      positive=`${s} ${be} ${iv}.`; negative=`${s} ${be} not ${iv}.`; question=`${be[0].toUpperCase()+be.slice(1)} ${lowerSubject(s)} ${iv}?`; formulaVerb=`${be} ${iv}`; tip='💡 المضارع المستمر = am/is/are + verb-ing.';
    } else if(tense==='past-simple'){
      const pv=irregularPast[v]||regularPast(v);
      positive=`${s} ${pv}.`; negative=`${s} didn't ${v}.`; question=`Did ${lowerSubject(s)} ${v}?`; formulaVerb=pv; tip="💡 في الماضي البسيط نستخدم التصريف الثاني، لكن بعد did/didn't يعود الفعل للمصدر.";
    } else if(tense==='future-simple'){
      positive=`${s} will ${v}.`; negative=`${s} will not ${v}.`; question=`Will ${lowerSubject(s)} ${v}?`; formulaVerb=`will ${v}`; tip='💡 المستقبل البسيط = will + المصدر في الإثبات والنفي والسؤال.';
    } else throw new Error('unsupported_tense');
    return {positive, negative, question, formulaVerb, tip};
  }
  return {irregularPast, regularPast, thirdPerson, ing, normalizeSentence, tenseForms};
});
