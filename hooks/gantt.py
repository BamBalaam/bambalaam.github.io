"""MkDocs hook: replace <!-- gantt --> with a generated Gantt chart."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import yaml

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PLACEHOLDER = "<!-- gantt -->"
DATA_FILE = "experience.yml"


def _parse_ym(s: str) -> date:
    year, month = s.split("-")
    return date(int(year), int(month), 1)


def _pct(d: date, start: date, span: int) -> str:
    return f"{(d - start).days / span * 100:.1f}"


def _fmt_month_year(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.year}"


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[list[date]] = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _build_gantt_html(data: dict[str, Any]) -> str:
    today = date.today()

    t_start = _parse_ym(data["timeline_start"])
    t_end_raw = data.get("timeline_end")
    t_end = today if t_end_raw is None else _parse_ym(t_end_raw)
    span = (t_end - t_start).days

    tracks = data["tracks"]
    for track in tracks:
        for bar in track["bars"]:
            bar["_start"] = _parse_ym(bar["start"])
            bar["_end"] = today if bar["end"] is None else _parse_ym(bar["end"])
            bar["_current"] = bar["end"] is None

    # Year axis ticks: Jan 1 of each year that falls within the timeline
    first_year = t_start.year if t_start.month == 1 else t_start.year + 1
    year_ticks: list[tuple[int, str]] = []
    for year in range(first_year, t_end.year + 1):
        jan1 = date(year, 1, 1)
        if jan1 <= t_end:
            year_ticks.append((year, _pct(jan1, t_start, span)))

    # Overlap detection: compare every bar in track i against every bar in track j (i < j)
    raw_overlaps: list[tuple[date, date]] = []
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            for bar_i in tracks[i]["bars"]:
                for bar_j in tracks[j]["bars"]:
                    ov_start = max(bar_i["_start"], bar_j["_start"])
                    ov_end = min(bar_i["_end"], bar_j["_end"])
                    if ov_start < ov_end:
                        raw_overlaps.append((ov_start, ov_end))

    merged_overlaps = _merge_intervals(raw_overlaps)

    overlap_bands = "\n".join(
        f'      <div class="gantt-overlap-band"'
        f' style="left:{_pct(ov_s, t_start, span)}%;'
        f'width:{(ov_e - ov_s).days / span * 100:.1f}%;"></div>'
        for ov_s, ov_e in merged_overlaps
    )

    year_spans = "".join(
        f'\n        <span class="gantt-year" style="left:{left}%">{year}</span>'
        for year, left in year_ticks
    )

    track_rows = []
    for track in tracks:
        bar_divs = []
        for bar in track["bars"]:
            left = _pct(bar["_start"], t_start, span)
            width = f"{(bar['_end'] - bar['_start']).days / span * 100:.1f}"
            end_label = "Present" if bar["_current"] else _fmt_month_year(bar["_end"])
            title = f"{bar['company']} · {_fmt_month_year(bar['_start'])}–{end_label}"
            css_class = "gantt-bar gantt-bar--current" if bar["_current"] else "gantt-bar"
            bar_divs.append(
                f'        <div class="{css_class}" style="left:{left}%;width:{width}%"'
                f' title="{title}"><span class="gantt-bar-label">{bar["short_label"]}</span></div>'
            )
        track_rows.append(
            '      <div class="gantt-track">\n' + "\n".join(bar_divs) + '\n      </div>'
        )

    label_divs = "\n".join(
        f'      <div class="gantt-label">{track["role"]}</div>'
        for track in tracks
    )

    # Overlap footer labels: positioned at band midpoint (CSS centers via translateX(-50%))
    footer_labels = "\n".join(
        f'      <span class="gantt-overlap-label"'
        f' style="left:{_pct(ov_s + timedelta(days=(ov_e - ov_s).days // 2), t_start, span)}%">'
        f'{_fmt_month_year(ov_s)} – {_fmt_month_year(ov_e)}</span>'
        for ov_s, ov_e in merged_overlaps
    )

    return f"""\
<div class="gantt-wrapper">
  <div class="gantt">
    <div class="gantt-labels">
      <div class="gantt-label-spacer"></div>
{label_divs}
    </div>
    <div class="gantt-tracks">
{overlap_bands}
      <div class="gantt-axis">{year_spans}
      </div>
{chr(10).join(track_rows)}
    </div>
  </div>
  <div class="gantt-footer">
    <div class="gantt-footer-spacer"></div>
    <div class="gantt-footer-track">
{footer_labels}
    </div>
  </div>
</div>"""


def on_page_markdown(markdown: str, *, page, config, files, **kwargs) -> str:
    if PLACEHOLDER not in markdown:
        return markdown

    data_path = os.path.join(config["docs_dir"], DATA_FILE)
    with open(data_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    return markdown.replace(PLACEHOLDER, _build_gantt_html(data), 1)
