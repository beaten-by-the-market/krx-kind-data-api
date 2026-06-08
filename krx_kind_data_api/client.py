from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import requests

from . import endpoints, parsers, transport
from .exceptions import KINDFetchError


def fetch(
    name: str,
    *,
    http: Optional[str] = None,
    send_as: Optional[str] = None,
    encoding: Optional[str] = None,
    parser: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
    **params: Any,
) -> pd.DataFrame:
    """카탈로그에 등록된 KIND 화면을 호출해 DataFrame으로 반환.

    Parameters
    ----------
    name      : 카탈로그 이름 (endpoints.ENDPOINTS의 키)
    http      : "post"/"get" override (보통 불필요)
    send_as   : "params"/"data" override
    encoding  : 응답 인코딩 override
    parser    : 파서 override (parsers._PARSERS의 키)
    session   : 재사용할 requests.Session
    **params  : 화면에 보낼 추가/오버라이드 파라미터 (defaults에 머지됨)

    Examples
    --------
    >>> from krx_kind_data_api import fetch
    >>> fetch("corp_list", marketType="kosdaqMkt")          # 코스닥 종목 마스터
    >>> fetch("merge_listing", toDate="2026-06-08")         # 합병·재상장
    >>> fetch("today_disclosure", marketType=1, selDate="2026-06-08")
    """
    spec = endpoints.get(name)

    merged = {**spec.get("defaults", {}), **params}
    missing = [k for k in spec.get("required", []) if not merged.get(k)]
    if missing:
        raise KINDFetchError(
            f"Endpoint {name!r} missing required params: {missing}"
        )

    html = transport.request(
        spec["path"],
        merged,
        http=(http or spec.get("http", "post")),
        send_as=(send_as or spec.get("send_as", "params")),
        encoding=(encoding or spec.get("encoding", "utf-8")),
        session=session,
        timeout=timeout,
    )

    parser_fn = parsers.get_parser(parser or spec.get("parser", "read_html"))
    return parser_fn(html, **spec.get("parser_kwargs", {}))


def list_endpoints() -> list[str]:
    return sorted(endpoints.ENDPOINTS)


def endpoint_info(name: str) -> dict:
    return dict(endpoints.get(name))
