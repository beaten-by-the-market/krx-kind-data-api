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
    **params  : 화면에 보낼 추가/오버라이드 파라미터.

    파라미터 병합 규칙
    ------------------
    최종 전송값 = {**spec["defaults"], **params}.
    즉 **params로 같은 키를 주면 defaults를 덮어쓴다.** 안 주면 defaults가 쓰인다.
    - required(spec["required"])에 있는 키가 비어 있으면 KINDFetchError.
    - 값은 문자열로 보내는 게 안전하다(예: currentPageSize="2000"). 숫자도 대개 되지만
      KIND 화면은 문자열 폼값을 기대한다.
    - 어떤 키를 넘길 수 있는지는 endpoint_info(name)["params"](있으면)에 문서화돼 있다.

    MCP 등에서 프로그램적으로 쓰기
    ------------------------------
    endpoint_info(name)으로 스펙을 꺼내 툴 인자 스키마를 만들 수 있다.
    >>> info = endpoint_info("pubofr_prog_com")
    >>> props = {k: {"type": "string", "description": v["desc"]}
    ...          for k, v in info["params"].items()}
    >>> required = [k for k, v in info["params"].items() if v.get("required")]
    # → 이 props/required를 그대로 MCP 툴의 inputSchema로 노출하고,
    #   호출 시 fetch(name, **arguments) 하면 된다.

    Examples
    --------
    >>> from krx_kind_data_api import fetch
    >>> fetch("corp_list", marketType="kosdaqMkt")          # 코스닥 종목 마스터
    >>> fetch("merge_listing", toDate="2026-06-08")         # 합병·재상장
    >>> fetch("today_disclosure", marketType=1, selDate="2026-06-08")
    >>> # 공모 진행현황: 전체
    >>> fetch("pubofr_prog_com", toDate="2026-07-02")
    >>> # 공모 진행현황: 특정 회사만(종목코드 363260 = 모비데이즈)
    >>> fetch("pubofr_prog_com", searchCorpName="363260",
    ...       searchCorpNameTmp="363260", isurCd="36326", toDate="2026-07-02")
    """
    spec = endpoints.get(name)

    merged = {**spec.get("defaults", {}), **params}
    # 선택적 전처리 훅: 친절한 파라미터(예: spacType) → 화면 raw 필드(listTypeArrStr)로
    # 변환하거나 파생 값을 채운다. required 검증 전에 실행된다.
    prepare = spec.get("prepare")
    if prepare is not None:
        merged = prepare(merged)
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
