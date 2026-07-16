"""Selenium 폴백: 임의 공시의 본문 URL을 JS 실행 후 docLocPath에서 직접 읽는다.

requests-only 경로(transport.disclosure_content_url)는 docno(서식코드)를 알아야 한다
(잠정실적 별도 99620 / 연결 99626 등). docno를 모르는 임의 폼이거나 shell 구조가
바뀌어 requests가 실패할 때, 브라우저로 shell을 열면 JS가 완성 URL(docno 포함)을
docLocPath에 채워준다. 그 값을 그대로 읽는다.

selenium 4는 Selenium Manager가 chromedriver를 자동 관리(별도 설치 불필요), Chrome만
있으면 된다. selenium은 선택 의존성이다: pip install "krx-kind-data-api[selenium]".

대량 수집 시 매 호출 webdriver.Chrome()은 느리므로 브라우저 재사용을 권장한다.
"""
from __future__ import annotations

import time

from .exceptions import KINDFetchError
from .transport import disclosure_viewer_url


def disclosure_content_url_selenium(
    acptno: str, *, headless: bool = True, wait: float = 12.0
) -> str:
    """접수번호 → 공시 본문 실제 URL(docno 포함). JS 실행 후 docLocPath에서 읽음."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opt = Options()
    if headless:
        opt.add_argument("--headless=new")
    for a in ("--no-sandbox", "--disable-gpu", "--window-size=1200,900"):
        opt.add_argument(a)
    d = webdriver.Chrome(options=opt)
    try:
        d.get(disclosure_viewer_url(acptno))
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.5)
            loc = d.execute_script(
                "var e=document.getElementById('docLocPath');return e?e.value:'';"
            )
            if loc:
                return loc     # 완성 URL(docno 포함) 그대로 반환
        raise KINDFetchError(f"docLocPath 미확보(acptno={acptno})")
    finally:
        d.quit()
