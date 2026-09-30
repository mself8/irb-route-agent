"""설명용 근거 검색 (RAG의 검색 단계). data/laws/*.md를 조문·소제목 단위로 나눠 BM25 키워드 검색을 한다.

- 판정에는 쓰지 않는다. ⑨ 사무국 질문과 근거 보기에 붙일 참고 문단만 찾는다.
- 임베딩을 쓰지 않는다. 글자 2-gram BM25라 같은 질의에는 늘 같은 결과가 나온다(점수가 같으면 파일·절 순서).
- 조각은 원문 인용(">"로 시작하는 줄)이 있는 절만 쓴다. 조사 메모와 옛 조문(개정 연혁)·확인 못 한 문구는 검색하지 않는다.
- 조각: {문서명, 조항, 원문, url, 확인일}. 문서명은 절의 국가법령정보센터 주소에서 법령명을 읽고, 없으면 파일 제목을 쓴다.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

LAWS_DIR = Path(__file__).resolve().parents[2] / "data" / "laws"
K1, B = 1.5, 0.75  # BM25 기본값
SKIP = re.compile(r"개정 연혁|확인불가|판본")  # 현행 원문이 아닌 절
LAW_NAMES = {
    "생명윤리및안전에관한법률": "생명윤리 및 안전에 관한 법률",
    "생명윤리및안전에관한법률시행령": "생명윤리 및 안전에 관한 법률 시행령",
    "생명윤리및안전에관한법률시행규칙": "생명윤리 및 안전에 관한 법률 시행규칙",
    "개인정보보호법": "개인정보 보호법",
    "개인정보보호법시행령": "개인정보 보호법 시행령",
    "의약품등의안전에관한규칙": "의약품 등의 안전에 관한 규칙",
    "의료기기법시행규칙": "의료기기법 시행규칙",
}


def _grams(text: str) -> list[str]:
    s = re.sub(r"\s+", "", text)
    return [s[i:i + 2] for i in range(len(s) - 1)]


def _doc_name(url: str | None, file_title: str) -> str:
    m = re.search(r"law\.go\.kr/법령/([^/]+)/", url or "")
    return LAW_NAMES.get(m.group(1), m.group(1)) if m else file_title


def _chunks(path: Path) -> list[dict]:
    md = path.read_text(encoding="utf-8")
    head, *sections = md.split("\n## ")
    title = re.sub(r"^#\s*(원문\s*[—-]\s*)?", "", head.splitlines()[0])
    title = re.sub(r"\s*[—-]\s*발췌$|\s*\((?!개인정보보호위원회)[^)]*\)$|[「」]", "", title).strip()
    checked = re.search(r"확인일:\s*(\d{4}-\d{2}-\d{2})", head)
    head_url = re.search(r"https?://\S+", head)
    out = []
    for sec in sections:
        name, _, body = sec.partition("\n")
        quote = "\n".join(line[2:].strip() for line in body.splitlines() if line.startswith("> "))
        if not quote or SKIP.search(name):
            continue
        url = re.search(r"출처:\s*(\S+)", body)
        url = url.group(1) if url else (head_url.group(0) if head_url else None)
        out.append({"문서명": _doc_name(url, title), "조항": name.strip(), "원문": quote, "url": url,
                    "확인일": checked.group(1) if checked else None})
    return out


@lru_cache(maxsize=1)
def _index():
    chunks = [c for path in sorted(LAWS_DIR.glob("*.md")) for c in _chunks(path)]
    tfs = []
    for c in chunks:
        tf: dict[str, int] = {}
        for g in _grams(c["조항"] + " " + c["원문"]):
            tf[g] = tf.get(g, 0) + 1
        tfs.append(tf)
    lengths = [sum(tf.values()) for tf in tfs]
    df: dict[str, int] = {}
    for tf in tfs:
        for g in tf:
            df[g] = df.get(g, 0) + 1
    return chunks, tfs, lengths, df, sum(lengths) / max(len(lengths), 1)


def search(query: str, k: int = 3) -> list[dict]:
    """질의와 가장 가까운 조각 k개. 결과는 {문서명, 조항, 원문, url, 확인일, 점수}."""
    chunks, tfs, lengths, df, avg = _index()
    n, grams = len(chunks), set(_grams(query))
    scored = []
    for i, tf in enumerate(tfs):
        s = 0.0
        for g in grams & tf.keys():
            idf = math.log(1 + (n - df[g] + 0.5) / (df[g] + 0.5))
            s += idf * tf[g] * (K1 + 1) / (tf[g] + K1 * (1 - B + B * lengths[i] / avg))
        if s > 0:
            scored.append((-round(s, 6), i))
    return [dict(chunks[i], 점수=-s) for s, i in sorted(scored)[:k]]
