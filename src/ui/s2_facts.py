"""S2: 마스킹 원문과 사실을 대조한 뒤 confirm()을 호출한다."""
from html import escape
import streamlit as st
from agent import api
from ui.common import accept_result, badge, go, heading, marked_text

STATUS = {'found': '추출됨', 'not_found': '계획서에 없음', 'conflict': '확인 필요'}


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
    heading('AI가 뽑은 사실을 확인해 주세요', '왼쪽 원문과 대조하고 수정한 뒤, 아래 버튼으로 판정에 사용할 사실을 확정하세요.')
    if api.FAKE:
        st.caption('예시 모드(FAKE=1): 수정 화면은 체험할 수 있지만 판정 결과는 샘플에 고정됩니다.')
    left, right = st.columns([1, 1], gap='medium')
    with left.container(border=True, height=620):
        st.subheader('연구계획서 원문')
        count = sum(log.count for log in pending.mask_log)
        st.markdown(badge(f'마스킹 {count}건', 'public'), unsafe_allow_html=True)
        st.caption(' / '.join(f'{log.type} {log.count}건' for log in pending.mask_log) or '마스킹 내역 없음')
        st.markdown(marked_text(pending.masked_text, pending.facts), unsafe_allow_html=True)
        st.download_button('마스킹된 원문 내려받기', pending.masked_text, file_name='masked_plan.txt', mime='text/plain')
    with right.container(border=True, height=620):
        st.subheader('사실 추출 결과')
        st.markdown(badge('AI 추출') + badge('사람 확인', 'human'), unsafe_allow_html=True)
        for fact in pending.facts:
            with st.container(border=True):
                prefix = f'fact_{fact.key}'
                reviewed = st.session_state.get(prefix + '_reviewed', False)
                tone = 'human' if fact.status != 'found' or fact.cross_check == 'disagree' else 'rule'
                status = '확인함' if reviewed else '교차 확인 불일치' if fact.cross_check == 'disagree' else STATUS[fact.status]
                st.markdown('<div class="fact-title">' + badge(fact.key) + escape(fact.label) + '</div>' + badge(status, 'rule' if reviewed else tone), unsafe_allow_html=True)
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
                st.markdown('<div class="fact-span">' + escape(fact.span or '대응하는 원문 구간이 없습니다.') + '</div>', unsafe_allow_html=True)
                a, b = st.columns(2)
                if a.button('맞음' if not editing else '수정 완료', key=prefix + '_ok', use_container_width=True):
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
