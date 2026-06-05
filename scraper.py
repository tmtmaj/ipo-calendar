"""38커뮤니케이션 공모주 청약 일정 스크래핑 (독립 실행용).

38커뮤니케이션은 구형 SSL(DH key too small)을 쓰므로 SECLEVEL=1 어댑터가 필요하다.
이 파일은 트레이딩 repo와 독립적이며, 공개 IPO 일정 데이터만 다룬다.
"""
from __future__ import annotations

import re

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from bs4 import BeautifulSoup

BASE = "https://www.38.co.kr"
LIST_URL = f"{BASE}/html/fund/index.htm?o=k"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class _LegacySSLAdapter(HTTPAdapter):
    """38커뮤니케이션의 구형 SSL 협상을 허용하는 어댑터."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context(ciphers="DEFAULT:@SECLEVEL=1")
        # 커스텀 컨텍스트는 기본 CA를 안 불러오므로 certifi 번들을 명시적으로 로드
        ctx.load_verify_locations(certifi.where())
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def _session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacySSLAdapter())
    return s


def fetch_ipo_list() -> list[dict]:
    """공모주 청약 일정 목록을 반환한다."""
    s = _session()
    res = s.get(LIST_URL, headers={"User-Agent": UA}, timeout=10)
    res.encoding = "euc-kr"
    soup = BeautifulSoup(res.text, "lxml")

    target = None
    for tag in soup.find_all(["td", "th"]):
        if tag.get_text(strip=True) == "종목명":
            target = tag.find_parent("table")
            break
    if not target:
        return []

    tr_list = target.find_all("tr")
    headers = [c.get_text(strip=True) for c in tr_list[0].find_all(["th", "td"])]

    rows: list[dict] = []
    for tr in tr_list[1:]:
        tds = tr.find_all("td")
        if not tds or not tds[0].get_text(strip=True):
            continue
        row: dict = {
            headers[i] if i < len(headers) else f"col{i}": td.get_text(strip=True)
            for i, td in enumerate(tds)
        }
        link = tr.find("a")
        row["_href"] = link["href"] if link else ""

        rate_raw = row.get("청약경쟁률", "")
        try:
            row["청약경쟁률_수치"] = (
                float(rate_raw.split(":")[0].replace(",", ""))
                if rate_raw and rate_raw != "-" else None
            )
        except Exception:
            row["청약경쟁률_수치"] = None

        row["상태"] = "완료" if row.get("확정공모가", "-") not in ["-", ""] else "예정"
        rows.append(row)

    rows.sort(key=lambda r: (0 if r["상태"] == "예정" else 1))
    return rows


def fetch_ipo_detail(href: str) -> dict:
    """상세 페이지에서 기관경쟁률·의무확약·신규상장일·종목코드·시장을 파싱."""
    result: dict = {}
    if not href:
        return result
    try:
        url = BASE + href if href.startswith("/") else href
        s = _session()
        res = s.get(url, headers={"User-Agent": UA}, timeout=8)
        res.encoding = "euc-kr"
        text = BeautifulSoup(res.text, "lxml").get_text(separator="")

        def _re(pattern, cast=str, default=None):
            m = re.search(pattern, text)
            try:
                return cast(m.group(1).replace(",", "")) if m else default
            except Exception:
                return default

        result["기관경쟁률"] = _re(r"기관경쟁률[\s\xa0]*([\d,]+\.?\d*):1", float)
        result["의무확약%"] = _re(r"의무보유확약[\s\xa0]*(\d+\.?\d*)%", float)
        result["신규상장일"] = _re(r"신규상장일[\s\xa0]*(\d{4}\.\d{2}\.\d{2})")
        result["종목코드"] = _re(r"종목코드[\s\xa0]+([A-Z0-9]{6})")
        m = re.search(r"시장구분[\s\xa0]*(코스닥|유가증권|코스피)", text)
        result["시장"] = m.group(1) if m else "코스닥"
    except Exception:
        pass
    return result
