"""공모주 청약 일정 → iCalendar(.ics) 생성 (독립 실행용).

애플/구글 캘린더 URL 구독(webcal)으로 사용한다.

실행:
    python3 generate_ipo_ics.py          # 상세 정보까지 포함 (느림)
    python3 generate_ipo_ics.py --fast   # 청약 일정만 (빠름)

이벤트:
    📋/🔥 [청약] 종목명 : 청약 기간 (🔥 = 기관경쟁률 1000배↑ 따상후보)
    🔔    [상장] 종목명 : 신규상장일 (시초가 매도 검토일)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scraper import fetch_ipo_list, fetch_ipo_detail

OUTPUT = Path(__file__).resolve().parent / "ipo.ics"


def _parse_subscription_period(text: str) -> tuple[datetime, datetime] | None:
    """'2026.07.01~07.02' → (시작일, 종료일). 연도 롤오버 처리."""
    if not text or "~" not in text:
        return None
    try:
        left, right = [p.strip() for p in text.split("~")]
        start = datetime.strptime(left, "%Y.%m.%d")
        mm, dd = [int(x) for x in right.split(".")]
        year = start.year
        if mm < start.month:
            year += 1
        end = datetime(year, mm, dd)
        return start, end
    except Exception:
        return None


def _parse_date(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%Y.%m.%d")
    except Exception:
        return None


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _event(uid: str, dtstart: datetime, dtend: datetime, summary: str, desc: str) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}@ipo-calendar",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{dtstart.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{dtend.strftime('%Y%m%d')}",
        f"SUMMARY:{_esc(summary)}",
        f"DESCRIPTION:{_esc(desc)}",
        "BEGIN:VALARM",
        "TRIGGER:PT9H",          # 종일 일정(자정) 기준 +9h = 당일 오전 9시 알림
        "ACTION:DISPLAY",
        "DESCRIPTION:공모주 일정 알림",
        "END:VALARM",
        "END:VEVENT",
    ]


def build_ics(enrich: bool = True) -> str:
    rows = fetch_ipo_list()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ipo-calendar//IPO Calendar//KR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:공모주 청약 일정",
        "X-WR-TIMEZONE:Asia/Seoul",
        "X-WR-CALDESC:38커뮤니케이션 기반 공모주 청약/상장 일정 (매일 자동 갱신)",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    n_sub, n_list = 0, 0
    for row in rows:
        name = row.get("종목명", "").strip()
        if not name:
            continue
        safe_name = name.replace(" ", "_")

        detail = fetch_ipo_detail(row.get("_href", "")) if enrich else {}
        inst_rate = detail.get("기관경쟁률")
        lockup = detail.get("의무확약%")
        listing = _parse_date(detail.get("신규상장일", ""))

        desc_parts = []
        if row.get("희망공모가") and row["희망공모가"] != "-":
            desc_parts.append(f"희망공모가 {row['희망공모가']}")
        if row.get("확정공모가") and row["확정공모가"] != "-":
            desc_parts.append(f"확정공모가 {row['확정공모가']}원")
        if inst_rate is not None:
            desc_parts.append(f"기관경쟁률 {inst_rate:,.0f}:1")
        if lockup is not None:
            desc_parts.append(f"의무확약 {lockup}%")
        if row.get("주간사"):
            desc_parts.append(f"주간사 {row['주간사']}")
        desc = "\n".join(desc_parts)

        period = _parse_subscription_period(row.get("공모주일정", ""))
        if period:
            start, end = period
            badge = "🔥" if (inst_rate is not None and inst_rate >= 1000) else "📋"
            uid = f"ipo-sub-{safe_name}-{start.strftime('%Y%m%d')}"
            lines += _event(
                uid, start, end + timedelta(days=1),
                f"{badge} [청약] {name}", desc,
            )
            n_sub += 1

        if listing:
            uid = f"ipo-list-{safe_name}-{listing.strftime('%Y%m%d')}"
            lines += _event(
                uid, listing, listing + timedelta(days=1),
                f"🔔 [상장] {name}", desc + "\n→ 상장일 시초가 매도 검토",
            )
            n_list += 1

    lines.append("END:VCALENDAR")
    print(f"✅ 청약 {n_sub}건 · 상장 {n_list}건 → 총 {n_sub + n_list}개 이벤트", file=sys.stderr)
    return "\r\n".join(lines) + "\r\n"


def main() -> None:
    enrich = "--fast" not in sys.argv
    ics = build_ics(enrich=enrich)
    OUTPUT.write_text(ics, encoding="utf-8")
    print(f"📅 생성 완료: {OUTPUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
