"""S5: 위원회 질문과 연구자 입력을 분리하고 rejudge() 결과를 표시한다."""
from html import escape
import streamlit as st
from agent import api
from ui.common import accept_result, basis_details, go, heading, notice, reset
from ui.s2_facts import _parse


def _context(item, result) -> None:
    judgments = [j for j in result.judgments if j.rule_id == item.rule_id or j.rule_id in item.cites]
    fact_keys = set(item.cites)
    for judgment in judgments:
        fact_keys.update(judgment.fact_refs)
    spans = list(dict.fromkeys(f.span for f in result.facts if f.key in fact_keys and f.span))
    with st.expander('확인이 필요한 이유와 근거'):
        st.markdown(f'<p class="question-reason">{escape(item.reason)}</p>', unsafe_allow_html=True)
        st.caption(f'규칙 {item.rule_id}')
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


def _title(item, result) -> str:
    if item.kind == '나':
        fact = next((f for f in result.facts if f.key == item.input_key), None)
        if fact and fact.label:
            return fact.label
    judgment = next((j for j in result.judgments if j.rule_id == item.rule_id), None)
    return judgment.requirement if judgment else item.ask_input or item.reason


def _answer(item, index, result, extra) -> None:
    if not item.input_key:
        st.warning('입력할 사실 키가 응답에 없어 이 항목은 재판정할 수 없습니다.')
        return
    key = f'answer_{index}_{item.rule_id}_{item.input_key}'
    saved = st.session_state.get(key + '_draft')
    if item.options:
        initial = item.options.index(saved) if saved in item.options else None
        value = st.radio(item.ask_input or item.reason, item.options, index=initial, key=key)
    else:
        value = st.text_input(item.ask_input or item.reason, value=saved or '', key=key)
    st.session_state[key + '_draft'] = value
    if value and str(value).strip():
        original = next((f.value for f in result.facts if f.key == item.input_key), None)
        extra[item.input_key] = _parse(value, original, item.input_key)


def _question(item, index, number, result, extra) -> None:
    with st.container(border=True, key=f's5_question_{index}_{item.rule_id}'):
        st.markdown(
            f'<div class="question-header" data-kind="{escape(item.kind)}">'
            f'<h4 class="question-title">Q{number}. {escape(_title(item, result))}</h4></div>',
            unsafe_allow_html=True,
        )
        label = '답변 입력' if item.kind == '나' else '문의할 질문 보기'
        with st.expander(label):
            if item.kind == '나':
                _answer(item, index, result, extra)
            elif item.question:
                st.code(item.question, language=None, wrap_lines=True)
                st.caption('오른쪽 위 복사 아이콘으로 질문을 복사해 기관에 문의하세요.')
            else:
                st.info('API 응답에 질문이 없습니다. 질문 생성 결과를 확인해 주세요.')
            _context(item, result)


def _navigation() -> None:
    back, new = st.columns(2)
    if back.button('결과 대시보드로 돌아가기'):
        go(2)
    new.button('처음으로', on_click=reset)


def render() -> None:
    result = st.session_state.result
    notice(result)
    heading(f'확인이 필요한 항목 {len(result.abstain)}건', '항목을 펼쳐 답변을 입력하거나 기관에 문의할 질문을 확인하세요.')
    if not result.abstain:
        st.success('현재 응답에 판단불가 항목이 없습니다.')
        _navigation()
        return

    groups = {
        '나': [(i, a) for i, a in enumerate(result.abstain) if a.kind == '나'],
        '가': [(i, a) for i, a in enumerate(result.abstain) if a.kind == '가'],
    }
    order = ['나', '가'] if groups['나'] else ['가', '나']
    names = {'나': '연구자 입력', '가': '기관 확인'}
    tabs = st.tabs([f'{names[kind]} {len(groups[kind])}건' for kind in order])
    extra = {}
    for kind, tab in zip(order, tabs):
        with tab:
            if not groups[kind]:
                st.info('직접 입력할 항목이 없습니다.' if kind == '나' else '기관에 확인할 항목이 없습니다.')
                continue
            for number, (index, item) in enumerate(groups[kind], 1):
                _question(item, index, number, result, extra)
            if kind == '나':
                st.caption(f'입력한 정보 {len(extra)}건')
                if st.button('입력한 값으로 다시 판정', type='primary', disabled=not extra, use_container_width=True):
                    try:
                        with st.spinner('보완한 정보로 다시 확인하고 있어요…'):
                            updated = api.rejudge(result.run_id, extra)
                    except Exception:
                        st.error('재판정을 완료하지 못했습니다. 입력값은 유지됩니다. 잠시 후 다시 시도해 주세요.')
                    else:
                        accept_result(updated)
                        go(2)
                if api.FAKE:
                    with st.expander('재판정 안내'):
                        st.caption('예시 모드(FAKE=1): 답한 질문을 목록에서 제거하는 시연입니다. 경로, 서류, 일정은 다시 계산되지 않습니다.')
            else:
                questions = [item for _, item in groups[kind] if item.question]
                if questions:
                    with st.expander(f'사무국 메일 초안 / 질문 {len(questions)}건'):
                        st.subheader('위원회 사무국')
                        st.caption('초안을 복사하거나 파일로 내려받아 내용을 확인한 뒤 직접 전달하세요.')
                        draft = _mail(result, questions)
                        st.code(draft, language=None, wrap_lines=True)
                        st.download_button('메일 초안 내려받기', draft, file_name='irb_questions.txt', mime='text/plain')
    _navigation()
