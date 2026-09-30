# Paperlogy 글꼴

- 이름 / 버전: Paperlogy 1.000
- 저작권: Copyright © 2024 PT& (피티앤)
- 제작: 리디자인 이주임, 기획 김도균. 첨부 글꼴의 메타데이터에 Gmarket Sans 및 Montserrat 기반임이 기재되어 있음.
- 배포처: https://freesentation.blog/paperlogyfont
- 원본: 사용자가 제공한 `Paperlogy-1.000.zip`의 TTF 파일
- 라이선스: SIL Open Font License 1.1 (`OFL.txt` 동봉)
- 라이선스 원문: https://github.com/Freesentation/paperlogy/blob/main/OFL%20license.txt

본문 Regular(400), 버튼 Medium(500), 소제목 SemiBold(600), 제목 Bold(700), 브랜드 ExtraBold(800)를 포함한다.
원본 전체 글리프와 이름 / 저작권 / 라이선스 메타데이터를 유지하고 웹 전송용 WOFF2로 압축했다.
변환 도구는 FontTools 4.61.1(MIT, https://github.com/fonttools/fonttools), Brotli 1.2.0(MIT, https://github.com/google/brotli)다.
두 도구는 변환 시에만 사용했으며 앱 실행 시 설치할 필요가 없다.

`ui.typography.font_face_css()`가 로컬 글꼴을 data URL로 포함하므로 별도 정적 파일 서버, CDN 연결, PC 글꼴 설치가 필요 없다.
아이콘에는 Paperlogy를 강제로 적용하지 않는다.

팀 루트 README 출처표에 추가할 항목:

> UI 글꼴: Paperlogy 1.000 (PT&, SIL OFL 1.1, https://freesentation.blog/paperlogyfont). 사용자 제공 TTF를 WOFF2로 압축해 포함. 변환 도구: FontTools 4.61.1(MIT), Brotli 1.2.0(MIT).

이 변경은 화면 담당 범위인 `src/ui/`에만 기록했다.
