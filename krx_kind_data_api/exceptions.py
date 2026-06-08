class KINDError(Exception):
    pass


class KINDFetchError(KINDError):
    """KIND 화면 호출 자체가 실패 (HTTP 오류, 빈 응답 등)."""

    pass


class KINDParseError(KINDError):
    """응답은 받았으나 HTML→DataFrame 파싱에 실패 (테이블 없음 등)."""

    pass


class UnknownEndpointError(KINDError):
    pass
