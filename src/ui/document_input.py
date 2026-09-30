"""업로드한 문서의 텍스트만 읽는다. 사실 추출과 판정은 agent.api에 맡긴다."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_PDF_PAGES = 200
WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class DocumentInputError(ValueError):
    """기존 입력을 지우지 않고 화면에 보여 줄 문서 읽기 오류."""


@dataclass(frozen=True)
class DocumentText:
    text: str
    warnings: tuple[str, ...] = ()


def _pdf(data: bytes) -> DocumentText:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentInputError('현재 실행 환경에 PDF 읽기 기능이 설치되지 않았습니다. 문서 내용을 복사해 입력해 주세요.') from exc
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise DocumentInputError('암호가 걸린 PDF입니다. 암호를 해제한 사본을 올려 주세요.')
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentInputError('PDF는 200쪽까지 읽을 수 있습니다. 연구계획서에 해당하는 쪽만 올려 주세요.')
        pages, empty_pages, total = [], [], 0
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').strip()
            total += len(text)
            if total > MAX_TEXT_CHARS:
                raise DocumentInputError('문서 내용은 20만 자까지 읽을 수 있습니다. 연구계획서 본문만 올려 주세요.')
            if text:
                pages.append(text)
            else:
                empty_pages.append(number)
    except DocumentInputError:
        raise
    except Exception as exc:
        raise DocumentInputError('PDF를 읽지 못했습니다. 파일을 다시 저장하거나 내용을 복사해 입력해 주세요.') from exc
    if not pages:
        raise DocumentInputError('PDF에서 글자를 찾지 못했습니다. 스캔 문서는 문자 인식(OCR) 후 올려 주세요.')
    warnings = ()
    if empty_pages:
        numbers = ', '.join(map(str, empty_pages[:10]))
        more = ' 외' if len(empty_pages) > 10 else ''
        warnings = (f'{numbers}{more}쪽에서 글자를 읽지 못했습니다. 빈 쪽이나 이미지인지 원본과 대조해 주세요.',)
    return DocumentText('\n\n'.join(pages), warnings)


def _docx(data: bytes) -> DocumentText:
    try:
        with ZipFile(BytesIO(data)) as document:
            info = document.getinfo('word/document.xml')
            if info.file_size > MAX_FILE_BYTES:
                raise DocumentInputError('문서 본문이 너무 큽니다. 연구계획서 본문만 별도 파일로 올려 주세요.')
            xml = document.read(info)
        if b'<!DOCTYPE' in xml.upper():
            raise DocumentInputError('이 문서 형식을 읽을 수 없습니다. Word에서 DOCX로 다시 저장해 주세요.')
        root = ElementTree.fromstring(xml)
        body = root.find(WORD_NS + 'body')
        if body is None:
            raise DocumentInputError('Word 문서에서 본문을 찾지 못했습니다.')
        # 문단과 표 안의 문단을 문서 순서대로 읽는다. 삭제된 변경 추적 문구는 제외한다.
        parts = []
        def walk(node):
            if node.tag == WORD_NS + 'del':
                return
            if node.tag == WORD_NS + 't':
                parts.append(node.text or '')
            elif node.tag == WORD_NS + 'tab':
                parts.append('\t')
            elif node.tag in (WORD_NS + 'br', WORD_NS + 'cr'):
                parts.append('\n')
            for child in node:
                walk(child)
            if node.tag == WORD_NS + 'p':
                parts.append('\n')
        walk(body)
    except DocumentInputError:
        raise
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, OSError, RecursionError) as exc:
        raise DocumentInputError('Word 문서를 읽지 못했습니다. DOCX로 다시 저장하거나 내용을 복사해 입력해 주세요.') from exc
    warnings = ()
    if any(node.tag.endswith('}drawing') or node.tag.endswith('}pict') for node in body.iter()):
        warnings = ('문서에 포함된 이미지의 글자는 읽지 않습니다. 필요한 내용이 입력칸에 있는지 확인해 주세요.',)
    return DocumentText(''.join(parts), warnings)


def extract_document(name: str, data: bytes) -> DocumentText:
    """전체 텍스트를 반환하며 빈 파일이나 용량 초과를 조용히 잘라 내지 않는다."""
    if not data:
        raise DocumentInputError('파일이 비어 있습니다. 내용이 있는 파일을 올려 주세요.')
    if len(data) > MAX_FILE_BYTES:
        raise DocumentInputError('20MB 이하의 파일을 올려 주세요.')
    suffix = Path(name).suffix.lower()
    if suffix == '.pdf':
        result = _pdf(data)
    elif suffix == '.docx':
        result = _docx(data)
    elif suffix == '.txt':
        encodings = ('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp949')
        for encoding in encodings:
            try:
                result = DocumentText(data.decode(encoding))
                break
            except UnicodeError:
                continue
        else:
            raise DocumentInputError('텍스트 파일의 인코딩을 읽지 못했습니다. UTF-8로 저장해 주세요.')
    else:
        raise DocumentInputError('PDF, Word(DOCX), TXT 파일을 올려 주세요. HWP와 DOC는 PDF 또는 DOCX로 변환해 주세요.')
    text = result.text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        raise DocumentInputError('문서에서 글자를 찾지 못했습니다. 내용을 복사해 입력해 주세요.')
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentInputError('문서 내용은 20만 자까지 읽을 수 있습니다. 연구계획서 본문만 올려 주세요.')
    return DocumentText(text, result.warnings)
