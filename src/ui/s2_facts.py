"""S2: 마스킹 원문과 사실을 대조한 뒤 confirm()을 호출한다."""
from html import escape
import streamlit as st
from agent import api
from ui.common import accept_result, badge, go, heading, marked_text

STATUS = {'found': '검토 전', 'not_found': '계획서에서 찾지 못함', 'conflict': '내용 확인 필요'}


def _show(value) -> str:
    if value is None:
        return ''
    return ', '.join(map(str, value)) if isinstance(value, list) else str(value)


def _parse(text: str, original, key: str = ''):
    text = (text or '').strip()
    if isinstance(original, list) or key in ('F12', 'F16'):
        return [x.strip() for x in text.split(',') if x.strip()] if text else ([] if isinstance(original, list) else None)
    if not text:
        return None
    if isinstance(original, int) and text.isdigit():
        return int(text)
    return text


def render() -> None:
    pending = st.session_state.pending
    heading('연구 내용을 확인해 주세요', '계획서에서 읽은 답이 실제 연구와 맞는지 확인해 주세요. 다른 답은 수정할 수 있습니다.')
    left, right = st.columns([1, 1], gap='medium')
    with left.container(border=True, height=620):
        st.subheader('개인정보를 가린 연구계획서')
        count = sum(log.count for log in pending.mask_log)
        st.markdown(badge(f'마스킹 {count}건', 'public'), unsafe_allow_html=True)
        st.caption(' / '.join(f'{log.type} {log.count}건' for log in pending.mask_log) or '마스킹 내역 없음')
        st.markdown(marked_text(pending.masked_text, pending.facts), unsafe_allow_html=True)
        st.download_button('마스킹된 원문 내려받기', pending.masked_text, file_name='masked_plan.txt', mime='text/plain')
    with right.container(border=True, height=620):
        st.subheader('확인할 연구 정보')
        for number, fact in enumerate(pending.facts, 1):
            prefix = f'fact_{fact.key}'
            reviewed = st.session_state.get(prefix + '_reviewed', False)
            with st.container(border=True, key=f'fact_card_{fact.key}'):
                status = '내가 확인함' if reviewed else '추출 결과가 달라 확인 필요' if fact.cross_check == 'disagree' else STATUS[fact.status]
                st.markdown(
                    f'<div class="fact-review-state" data-reviewed="{str(reviewed).lower()}">'
                    f'<h4 class="fact-question">Q{number}. {escape(fact.label)}</h4>'
                    + badge(status, 'rule' if reviewed else 'danger') + '</div>',
                    unsafe_allow_html=True,
                )
                editing = st.session_state.get(prefix + '_editing', False)
                # Widget values are disposable in Streamlit: keep the draft separately
                # so a collapsed edit field cannot silently discard a saved correction.
                draft_key, widget_key = prefix + '_draft', prefix + '_value'
                if editing:
                    st.session_state.setdefault(widget_key, st.session_state.get(draft_key, _show(fact.value)))
                    value = st.text_input(f'{fact.key} {fact.label} 수정', key=widget_key, help='목록은 쉼표로 구분하고, 모르는 값은 비워 두세요.')
                    st.session_state[draft_key] = value
                else:
                    value = st.session_state.get(draft_key, _show(fact.value))
                    st.markdown('<div class="fact-value">' + escape(value or ('없음' if fact.value == [] else '정보 없음')) + '</div>', unsafe_allow_html=True)
                evidence = ' '.join((fact.span or '근거 문장을 찾지 못했습니다. 계획서에서 직접 확인해 주세요.').split())
                st.markdown(
                    f'<p class="fact-evidence">원문 : {escape(evidence)} '
                    f'<span>(항목 번호 {escape(fact.key)})</span></p>',
                    unsafe_allow_html=True,
                )
                a, b = st.columns(2)
                if a.button('내용이 맞아요' if not editing else '수정 완료', key=prefix + '_ok', use_container_width=True):
                    st.session_state[prefix + '_reviewed'] = True
                    st.session_state[prefix + '_editing'] = False
                    st.rerun()
                if b.button('수정', key=prefix + '_edit', use_container_width=True):
                    st.session_state[prefix + '_reviewed'] = False
                    st.session_state[prefix + '_editing'] = True
                    st.rerun()
    back, action = st.columns([1, 2])
    if back.button('입력으로 돌아가기'):
        go(0)
    if action.button('사실 확정하고 판정', type='primary', use_container_width=True):
        facts, changed = [], []
        for fact in pending.facts:
            key = f'fact_{fact.key}_draft'
            value = _parse(st.session_state[key], fact.value, fact.key) if key in st.session_state else fact.value
            if value != fact.value:
                changed.append(fact.key)
                fact = fact.model_copy(update={'value': value, 'status': 'not_found' if value is None else 'found'})
            facts.append(fact.model_dump())
        try:
            with st.spinner('확정한 사실로 심의 경로와 서류를 확인하고 있어요…'):
                previous = st.session_state.get('result')
                if previous is not None and previous.run_id == pending.run_id:
                    result = api.rejudge(pending.run_id, {f['key']: f['value'] for f in facts if f['key'] in changed}) if changed else previous
                else:
                    result = api.confirm(pending.run_id, facts, changed)
        except Exception:
            st.error('판정을 완료하지 못했습니다. 입력한 사실은 유지되니 잠시 후 다시 시도해 주세요.')
            return
        accept_result(result)
        go(2)
