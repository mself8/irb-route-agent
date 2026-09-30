"""S5: 위원회 질문과 연구자 입력을 분리하고 rejudge() 결과를 표시한다."""
from html import escape
import streamlit as st
from agent import api
from ui.common import accept_result, badge, basis_details, go, heading, notice, reset
from ui.s2_facts import _parse


def _context(item, result) -> None:
    judgments = [j for j in result.judgments if j.rule_id == item.rule_id or j.rule_id in item.cites]
    fact_keys = set(item.cites)
    for judgment in judgments:
        fact_keys.update(judgment.fact_refs)
    spans = list(dict.fromkeys(f.span for f in result.facts if f.key in fact_keys and f.span))
    with st.expander('관련 근거와 계획서 원문'):
        for judgment in judgments:
            basis_details(judgment)
        if not judgments:
            st.caption('이 항목의 세부 조문은 응답에 없습니다.')
        for span in spans:
            st.write('계획서 원문: ' + span)
        if not spans:
            st.caption('연결된 계획서 원문 구간이 없습니다.')
        for ref in item.references:
            st.write(f"참고: {ref.get('문서명', '')} {ref.get('조항', '')}")
            url = ref.get('url') or ''
            if url.startswith(('https://', 'http://')):
                st.link_button('참고 문서 열기', url)


def _mail(result, items) -> str:
    lines = ['제목: 연구 심의 절차 확인 요청', '', '안녕하세요. 아래 연구의 심의 절차에 관해 확인을 요청드립니다.']
    if result.institution.name:
        lines.append('소속기관: ' + result.institution.name)
    lines.extend(['안내된 경로: ' + ' → '.join(result.route.committees), ''])
    for n, item in enumerate(items, 1):
        lines.extend([f'{n}. [{item.rule_id}]', item.question, ''])
    lines.extend(['검토 후 안내 부탁드립니다. 감사합니다.', '', result.notice])
    return '\n'.join(lines)


def render() -> None:
    result = st.session_state.result
    notice(result)
    heading(f'판단하지 않은 항목 {len(result.abstain)}건', '위원회가 판단할 질문과 연구자가 보완할 정보를 구분해 안내합니다.')
    if not result.abstain:
        st.success('현재 응답에 판단불가 항목이 없습니다.')
    left, right = st.columns([3, 1], gap='medium')
    questions = [a for a in result.abstain if a.kind == '가' and a.question]
    extra = {}
    with right:
        st.markdown('<div class="question-side"><div class="symbol">▤</div><b>위원회 사무국</b><p>위원회 판단이 필요한 항목은<br>질문을 복사해 직접 확인하세요.</p>' + badge(f'사무국 질문 {len(questions)}건', 'human') + '</div>', unsafe_allow_html=True)
        if questions:
            st.button('메일 초안 만들기', key='mail_open', on_click=lambda: st.session_state.update(mail_visible=True), use_container_width=True)
            st.caption('초안을 화면에 만들며 메일을 발송하지 않습니다.')
    with left:
        for index, item in enumerate(result.abstain):
            with st.container(border=True):
                label = '(가) 위원회 판단' if item.kind == '가' else '(나) 연구자 입력 필요'
                st.markdown(badge('판단불가', 'human') + badge(label, 'human') + badge(item.rule_id, 'public'), unsafe_allow_html=True)
                st.write(item.reason)
                _context(item, result)
                if item.kind == '가':
                    st.markdown(badge('AI', 'ai') + ' 사무국에 보낼 질문', unsafe_allow_html=True)
                    if item.question:
                        st.code(item.question, language=None, wrap_lines=True)
                        st.caption('질문 오른쪽 위 복사 아이콘으로 복사하세요.')
                    else:
                        st.info('API 응답에 질문이 없습니다. 질문 생성 결과를 확인해 주세요.')
                elif not item.input_key:
                    st.warning('입력할 사실 키가 응답에 없어 이 항목은 재판정할 수 없습니다.')
                else:
                    key = f'answer_{index}_{item.rule_id}_{item.input_key}'
                    saved = st.session_state.get(key + '_draft')
                    if item.options:
                        initial = item.options.index(saved) if saved in item.options else None
                        value = st.radio(item.ask_input or item.reason, item.options, index=initial, key=key, horizontal=True)
                    else:
                        value = st.text_input(item.ask_input or item.reason, value=saved or '', key=key)
                    st.session_state[key + '_draft'] = value
                    if value and str(value).strip():
                        original = next((f.value for f in result.facts if f.key == item.input_key), None)
                        extra[item.input_key] = _parse(value, original, item.input_key)
        if any(a.kind == '나' for a in result.abstain):
            if api.FAKE:
                st.caption('예시 모드(FAKE=1): 답한 질문을 목록에서 제거하는 시연입니다. 경로, 서류, 일정은 다시 계산되지 않습니다.')
            if st.button('입력한 값으로 다시 판정', type='primary', disabled=not extra, use_container_width=True):
                try:
                    with st.spinner('보완한 정보로 다시 확인하고 있어요…'):
                        updated = api.rejudge(result.run_id, extra)
                except Exception:
                    st.error('재판정을 완료하지 못했습니다. 입력값은 유지됩니다. 잠시 후 다시 시도해 주세요.')
                    return
                accept_result(updated)
                go(2)
    if st.session_state.get('mail_visible') and questions:
        with st.container(border=True):
            st.subheader('사무국 메일 초안')
            draft = _mail(result, questions)
            st.code(draft, language=None, wrap_lines=True)
            st.download_button('메일 초안 내려받기', draft, file_name='irb_questions.txt', mime='text/plain')
    back, new = st.columns(2)
    if back.button('결과 대시보드로 돌아가기'):
        go(2)
    new.button('처음으로', on_click=reset)
