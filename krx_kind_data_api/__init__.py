"""krx-kind-data-api — KRX 상장공시시스템(kind.krx.co.kr) 호출 클라이언트.

data.krx.co.kr용 [krx-data-api]의 KIND 버전. KIND는 로그인/OTP가 없고,
화면별 `.do` 엔드포인트에 폼 파라미터를 POST/GET → HTML을 파싱하는 구조다.

빠른 시작
---------
>>> from krx_kind_data_api import fetch, list_endpoints
>>> fetch("corp_list", marketType="kosdaqMkt")            # 코스닥 종목 마스터
>>> fetch("merge_listing", toDate="2026-06-08")           # 합병·재상장 기업
>>> fetch("today_disclosure", marketType=1, selDate="2026-06-08")
>>> list_endpoints()

새 화면 추가
-----------
endpoints.ENDPOINTS 에 dict 한 줄 추가 → 바로 fetch("새이름") 가능.
절차: docs/새_엔드포인트_추가하기.md
"""

from .client import fetch, list_endpoints, endpoint_info
from .parsers import register_parser, get_parser
from .transport import disclosure_viewer_url, MARKETS, BASE
from .exceptions import (
    KINDError,
    KINDFetchError,
    KINDParseError,
    UnknownEndpointError,
)

__all__ = [
    "fetch",
    "list_endpoints",
    "endpoint_info",
    "register_parser",
    "get_parser",
    "disclosure_viewer_url",
    "MARKETS",
    "BASE",
    "KINDError",
    "KINDFetchError",
    "KINDParseError",
    "UnknownEndpointError",
]

__version__ = "0.1.0"
