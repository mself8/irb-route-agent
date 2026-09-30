"""앱에 포함된 Paperlogy 웹 글꼴. 외부 글꼴 서버나 PC 설치가 필요 없다."""
from base64 import b64encode
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def font_face_css() -> str:
    """정적 글꼴을 한 번만 읽고 모든 화면에서 재사용한다."""
    font_dir = Path(__file__).with_name("fonts")
    faces = []
    for weight, name in (
        (400, "Paperlogy-4Regular"),
        (500, "Paperlogy-5Medium"),
        (600, "Paperlogy-6SemiBold"),
        (700, "Paperlogy-7Bold"),
        (800, "Paperlogy-8ExtraBold"),
    ):
        encoded = b64encode((font_dir / f"{name}.woff2").read_bytes()).decode("ascii")
        faces.append(
            "@font-face { font-family:'Paperlogy'; font-style:normal; "
            f"font-weight:{weight}; font-display:swap; "
            f"src:url('data:font/woff2;base64,{encoded}') format('woff2'); }}"
        )
    return "\n".join(faces)
