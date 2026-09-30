// 범용 채우기: 표준 신청 데이터(DATA)를 사이트 어댑터(ADAPTER)의 대응표대로 채운다. 칸 ID 대신 화면 글자(행 제목·선택지)로 찾는다.
// 누르지 않는 것: 저장·제출, 파일 첨부, 본인 확인·약속 체크(ADAPTER.self_check). 못 찾거나 둘 이상 맞으면 건너뛰고 '사람 확인'으로 남긴다.
// 녹화용 표시(화면에서만): 지금 채우는 칸 주황 테두리, 끝에 본인이 할 칸 점선, 실명 칸 흐림. 크롬 창이 앞에 떠 있어야 사람 속도로 채운다.
(ADAPTER, DATA) => {
  const norm = t => (t || '').trim().split('\n')[0].split('*')[0].replace(/\s+/g, ' ').trim();
  const optionLabel = e => ([...(e.labels || [])].pop()?.innerText || '').trim().replace(/\s+/g, ' ');
  const isHead = c => c.tagName === 'TH' || (c.tagName === 'TD' && !c.querySelector('input,select,textarea') && c.innerText.trim());
  const rowLabel = e => {  // 이 칸의 행 제목: 같은 줄에서 앞쪽 가장 가까운 제목 칸(th, 또는 입력칸 없는 td)
    for (let td = e.closest('td'); td; td = td.parentElement?.closest('td')) {
      for (let p = td.previousElementSibling; p; p = p.previousElementSibling) if (isHead(p)) return norm(p.innerText);
    }
    return '';
  };
  const g = id => document.getElementById(id);
  // 준비 조건은 칸이 있는지만 본다. 조사연구 칸은 인간대상연구를 고르기 전까지 원래 잠겨 있고, 위험수준 칸은 사이트가 늦게 풀 때가 있다
  if ((ADAPTER.ready || []).some(id => !g(id))) throw new Error('양식이 아직 다 뜨지 않았습니다. 크롬 창을 앞에 띄우고 다시 실행하세요.');
  window.__dlg = [];
  window.alert = m => window.__dlg.push('alert:' + m);
  window.confirm = m => { window.__dlg.push('confirm:' + m); return false; };
  const css = document.createElement('style');
  css.textContent = '.__pii{filter:blur(7px)!important}' +
    '.__now{outline:3px solid #F28C28!important;outline-offset:3px;border-radius:4px}' +
    '.__self{outline:2px dashed #F28C28!important;outline-offset:4px;border-radius:4px}';
  document.head.appendChild(css);
  (ADAPTER.pii || []).forEach(sel => document.querySelectorAll(sel).forEach(e => e.classList.add('__pii')));
  [...document.querySelectorAll('strong')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.x < 250 && r.y < 150; })
    .forEach(e => (e.parentElement || e).classList.add('__pii'));  // 왼쪽 위 로그인 이름

  const selfIds = new Set(ADAPTER.self_check || []);
  const choose = (f, want) => {
    const pool = [...document.querySelectorAll('input[type=radio],input[type=checkbox]')]
      .filter(e => !selfIds.has(e.id) && e.offsetParent && (!f.row || rowLabel(e) === f.row));  // 숨은 섹션(예: 인체유래물연구)의 같은 칸은 뺀다
    for (const test of [l => l === want, l => l.startsWith(want), l => l.includes(want)]) {
      const hit = pool.filter(e => test(optionLabel(e)));
      if (hit.length) return hit;
    }
    return [];
  };
  const textField = f => [...document.querySelectorAll('input,textarea')].filter(e => (e.type === 'text' || e.tagName === 'TEXTAREA') && e.offsetParent && rowLabel(e) === f.row)[f.nth || 0];

  const fast = document.hidden;  // 가려진 탭은 타이머가 늦어 기다리지 않는다(리허설용)
  const wait = ms => fast ? Promise.resolve() : new Promise(r => setTimeout(r, ms));
  const show = async e => { e.scrollIntoView({block: 'center', behavior: fast ? 'auto' : 'smooth'}); await wait(420); };
  const fire = e => { ['input', 'keyup', 'change'].forEach(t => e.dispatchEvent(new Event(t, {bubbles: true}))); if (window.jQuery) jQuery(e).trigger('change'); };
  const log = [];
  window.__fillResult = null;
  (async () => {
    for (const f of ADAPTER.fields) {
      const v = DATA[f.key];
      if (v == null || v === '') { log.push(`비움 ${f.key}: 계획서에 값 없음 → 사람 확인`); continue; }
      const want = (f.values && f.values[v]) || String(v);
      if (f.kind === 'text' || f.kind === 'date') {
        const e = textField(f);
        if (!e || e.disabled) { log.push(`건너뜀 ${f.key}: '${f.row}' 칸 없음 → 사람 확인`); continue; }
        await show(e);
        e.classList.add('__now');
        e.value = '';
        if (f.kind === 'date') e.value = want;  // 달력 칸은 한 글자씩 치면 사이트가 다른 칸을 잠근다 → 한 번에
        else for (const ch of want) { e.value += ch; e.dispatchEvent(new Event('input', {bubbles: true})); await wait(want.length > 40 ? 22 : 45); }
        fire(e); e.blur();
        if (window.jQuery && jQuery.datepicker && e.classList.contains('hasDatepicker')) jQuery(e).datepicker('hide');
        log.push(`${e.value === want ? '✓' : '✗'} ${f.key} → '${f.row}' = ${e.value}`);
        await wait(330);
        e.classList.remove('__now');
        continue;
      }
      const hit = choose(f, want);
      if (hit.length !== 1) { log.push(`건너뜀 ${f.key}: '${want}' 맞는 칸 ${hit.length}개 → 사람 확인`); continue; }
      const e = hit[0];
      const box = e.closest('label') || e.parentElement || e;
      await show(e);
      box.classList.add('__now');
      await wait(180);
      for (let n = 0; n < 20 && e.disabled; n++) await new Promise(r => setTimeout(r, 100));  // 사이트가 잠깐 잠그는 칸
      if (!e.checked && !e.disabled) e.click();
      log.push(`${e.checked ? '✓' : '✗'} ${f.key} → '${f.row || '(선택지)'}' ${optionLabel(e)}`);
      await wait(330);
      box.classList.remove('__now');
    }
    const self = [...selfIds].map(g).filter(Boolean);
    const last = self.find(e => e.id === 'chkObsrveMattrsConfrmYn') || self[self.length - 1];
    if (last) last.scrollIntoView({block: 'center', behavior: fast ? 'auto' : 'smooth'});
    self.forEach(e => (e.closest('label') || e.parentElement)?.classList.add('__self'));
    window.__fillResult = log.join('\n') + `\n본인 확인 칸(모두 false여야 함): ${self.map(e => `${e.id}=${e.checked}`).join(', ')}` +
      `\n대화상자: ${window.__dlg.join(' / ') || '없음'}${fast ? '\n(가려진 탭이라 바로 채움)' : ''}`;
  })().catch(err => { window.__fillResult = '실패: ' + err; });
  return 'started';
}
