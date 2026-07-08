#!/usr/bin/env python3
"""Plot RPY time series from single or dual daisi IMU drift logs."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


Vec3 = tuple[float, float, float]
Sample = tuple[datetime, float, float, float, Vec3 | None, Vec3 | None]


LINE_RE = re.compile(
    r"^[IWEF](?P<month>\d{2})(?P<day>\d{2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<usec>\d{6})"
    r".* (?P<imu>imu_[ab]) rpy: "
    r"(?P<roll>[-+0-9.eE]+) (?P<pitch>[-+0-9.eE]+) (?P<yaw>[-+0-9.eE]+)"
)
SINGLE_LINE_RE = re.compile(
    r"^[IWEF](?P<month>\d{2})(?P<day>\d{2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<usec>\d{6})"
    r".* rpy: "
    r"(?P<roll>[-+0-9.eE]+) (?P<pitch>[-+0-9.eE]+) (?P<yaw>[-+0-9.eE]+)"
)
DUAL_VEC_RE = re.compile(
    r"^[IWEF](?P<month>\d{2})(?P<day>\d{2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<usec>\d{6})"
    r".* (?P<imu>imu_[ab])_(?P<kind>omega|acc): "
    r"(?P<x>[-+0-9.eE]+) (?P<y>[-+0-9.eE]+) (?P<z>[-+0-9.eE]+)"
)
SINGLE_VEC_RE = re.compile(
    r"^[IWEF](?P<month>\d{2})(?P<day>\d{2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<usec>\d{6})"
    r".* (?P<kind>omega|acc): "
    r"(?P<x>[-+0-9.eE]+) (?P<y>[-+0-9.eE]+) (?P<z>[-+0-9.eE]+)"
)
YEAR_RE = re.compile(r"_(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})_")


def infer_year(path: Path) -> int:
    match = YEAR_RE.search(path.name)
    if match:
        return int(match.group("year"))
    return datetime.now().year


def parse_log(path: Path) -> dict[str, list[Sample]]:
    year = infer_year(path)
    rpy_data: dict[str, list[tuple[datetime, float, float, float]]] = {"imu_a": [], "imu_b": []}
    vec_data: dict[str, dict[str, list[Vec3]]] = {
        "imu_a": {"omega": [], "acc": []},
        "imu_b": {"omega": [], "acc": []},
        "ttyUSB0": {"omega": [], "acc": []},
    }
    single_rows: list[tuple[datetime, float, float, float]] = []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = LINE_RE.match(line)
            if match:
                timestamp = datetime(
                    year,
                    int(match.group("month")),
                    int(match.group("day")),
                    int(match.group("hour")),
                    int(match.group("minute")),
                    int(match.group("second")),
                    int(match.group("usec")),
                )
                rpy_data[match.group("imu")].append(
                    (
                        timestamp,
                        float(match.group("roll")),
                        float(match.group("pitch")),
                        float(match.group("yaw")),
                    )
                )
                continue

            match = DUAL_VEC_RE.match(line)
            if match:
                vec_data[match.group("imu")][match.group("kind")].append(
                    (float(match.group("x")), float(match.group("y")), float(match.group("z")))
                )
                continue

            match = SINGLE_LINE_RE.match(line)
            if match:
                timestamp = datetime(
                    year,
                    int(match.group("month")),
                    int(match.group("day")),
                    int(match.group("hour")),
                    int(match.group("minute")),
                    int(match.group("second")),
                    int(match.group("usec")),
                )
                single_rows.append(
                    (
                        timestamp,
                        float(match.group("roll")),
                        float(match.group("pitch")),
                        float(match.group("yaw")),
                    )
                )
                continue

            match = SINGLE_VEC_RE.match(line)
            if match:
                vec_data["ttyUSB0"][match.group("kind")].append(
                    (float(match.group("x")), float(match.group("y")), float(match.group("z")))
                )

    def with_vectors(imu: str, rows: list[tuple[datetime, float, float, float]]) -> list[Sample]:
        omega_rows = vec_data[imu]["omega"]
        acc_rows = vec_data[imu]["acc"]
        return [
            (
                timestamp,
                roll,
                pitch,
                yaw,
                omega_rows[index] if index < len(omega_rows) else None,
                acc_rows[index] if index < len(acc_rows) else None,
            )
            for index, (timestamp, roll, pitch, yaw) in enumerate(rows)
        ]

    if rpy_data["imu_a"] or rpy_data["imu_b"]:
        for imu, rows in rpy_data.items():
            if not rows:
                raise ValueError(f"No '{imu} rpy:' rows found in {path}")
        return {imu: with_vectors(imu, rows) for imu, rows in rpy_data.items()}

    if single_rows:
        return {"ttyUSB0": with_vectors("ttyUSB0", single_rows)}

    raise ValueError(f"No RPY rows found in {path}")


def elapsed_minutes(rows: list[Sample], start: datetime) -> list[float]:
    elapsed: list[float] = []
    day_offset = timedelta()
    previous = rows[0][0]
    for timestamp, *_ in rows:
        if timestamp + day_offset < previous:
            day_offset += timedelta(days=1)
        adjusted = timestamp + day_offset
        elapsed.append((adjusted - start).total_seconds() / 60.0)
        previous = adjusted
    return elapsed


def plot_rpy(
    data: dict[str, list[Sample]],
    output: Path,
    title: str,
    degrees: bool,
) -> None:
    first_timestamp = min(rows[0][0] for rows in data.values())
    labels = ("roll", "pitch", "yaw")
    unit = "deg" if degrees else "rad"
    scale = 180.0 / 3.141592653589793 if degrees else 1.0

    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True, constrained_layout=True)
    colors = {"imu_a": "#1f77b4", "imu_b": "#d62728", "ttyUSB0": "#1f77b4"}

    for index, axis in enumerate(axes):
        for imu, rows in data.items():
            rows = data[imu]
            x = elapsed_minutes(rows, first_timestamp)
            y = [row[index + 1] * scale for row in rows]
            axis.plot(
                x,
                y,
                label=imu.upper().replace("_", " "),
                linewidth=1.3,
                color=colors.get(imu, "#1f77b4"),
            )

        axis.set_ylabel(f"{labels[index]} ({unit})")
        axis.grid(True, alpha=0.28)
        axis.legend(loc="best")

    axes[-1].set_xlabel("elapsed time (min)")
    fig.suptitle(title)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_interactive_html(
    data: dict[str, list[Sample]],
    output: Path,
    title: str,
    degrees: bool,
) -> None:
    first_timestamp = min(rows[0][0] for rows in data.values())
    scale = 180.0 / 3.141592653589793 if degrees else 1.0

    def vector_component(rows: list[Sample], vec_index: int, component_index: int) -> list[float | None]:
        values: list[float | None] = []
        for row in rows:
            vector = row[vec_index]
            values.append(vector[component_index] if vector is not None else None)
        return values

    payload = {
        "title": title,
        "unit": "deg" if degrees else "rad",
        "units": {
            "roll": "deg" if degrees else "rad",
            "pitch": "deg" if degrees else "rad",
            "yaw": "deg" if degrees else "rad",
            "omega_x": "rad/s",
            "omega_y": "rad/s",
            "omega_z": "rad/s",
            "acc_x": "m/s^2",
            "acc_y": "m/s^2",
            "acc_z": "m/s^2",
        },
        "series": [
            {
                "name": imu.upper().replace("_", " "),
                "color": {"imu_a": "#1f77b4", "imu_b": "#d62728", "ttyUSB0": "#1f77b4"}.get(imu, "#1f77b4"),
                "x": elapsed_minutes(rows, first_timestamp),
                "roll": [row[1] * scale for row in rows],
                "pitch": [row[2] * scale for row in rows],
                "yaw": [row[3] * scale for row in rows],
                "omega": [row[4] for row in rows],
                "acc": [row[5] for row in rows],
                "omega_x": vector_component(rows, 4, 0),
                "omega_y": vector_component(rows, 4, 1),
                "omega_z": vector_component(rows, 4, 2),
                "acc_x": vector_component(rows, 5, 0),
                "acc_y": vector_component(rows, 5, 1),
                "acc_z": vector_component(rows, 5, 2),
            }
            for imu, rows in data.items()
        ],
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    safe_title = html.escape(title)
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17212b; background: #f7f8fa; }}
header {{ position: sticky; top: 0; z-index: 2; background: rgba(255,255,255,.94); border-bottom: 1px solid #d8dde3; padding: 12px 18px; }}
h1 {{ margin: 0 0 6px; font-size: 18px; font-weight: 650; }}
.hint {{ color: #53606c; font-size: 13px; }}
.wrap {{ padding: 14px 18px 26px; }}
.panel {{ margin: 0 0 14px; background: #fff; border: 1px solid #d8dde3; border-radius: 6px; }}
.bar {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border-bottom: 1px solid #e6e9ee; }}
.label {{ font-weight: 650; }}
.buttons {{ display: flex; gap: 8px; }}
button {{ height: 28px; border: 1px solid #c8d0d8; background: #fff; border-radius: 5px; padding: 0 10px; cursor: pointer; }}
button:hover {{ background: #f0f3f6; }}
canvas {{ display: block; width: 100%; height: 260px; cursor: crosshair; }}
.legend {{ font-size: 12px; color: #53606c; }}
</style>
</head>
<body>
<header>
  <h1>{safe_title}</h1>
  <div class="hint">鼠标移动到曲线附近显示坐标、角速度 omega 和加速度 acc；左键拖拽框选放大 X/Y；滚轮缩放纵坐标；按住 Shift 滚轮缩放时间轴；右键或 Option/Alt+拖拽平移；双击重置。</div>
</header>
<div class="wrap" id="plots"></div>
<script id="imu-data" type="application/json">{payload_json}</script>
<script>
const data = JSON.parse(document.getElementById("imu-data").textContent);
const channels = ["roll", "pitch", "yaw", "omega_x", "omega_y", "omega_z", "acc_x", "acc_y", "acc_z"];
const plots = document.getElementById("plots");

function extent(values) {{
  let lo = Infinity, hi = -Infinity;
  for (const v of values) {{
    if (Number.isFinite(v)) {{
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }}
  }}
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) return [lo - 1, hi + 1];
  const pad = (hi - lo) * 0.08;
  return [lo - pad, hi + pad];
}}

function allX() {{
  return data.series.flatMap(s => s.x);
}}

function allY(channel) {{
  return data.series.flatMap(s => s[channel]);
}}

function buildPanel(channel) {{
  const panel = document.createElement("section");
  panel.className = "panel";
  const unit = data.units[channel] || "";
  panel.innerHTML = `<div class="bar"><div><span class="label">${{channel}} (${{unit}})</span> <span class="legend"></span></div><div class="buttons"><button data-act="auto-y">Y auto</button><button data-act="reset">Reset</button></div></div><canvas></canvas>`;
  plots.appendChild(panel);
  const canvas = panel.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const legend = panel.querySelector(".legend");
  legend.innerHTML = data.series.map(s => `<span style="color:${{s.color}}">■</span> ${{s.name}}`).join(" &nbsp; ");

  const x0 = extent(allX());
  const y0 = extent(allY(channel));
  const view = {{ xMin: x0[0], xMax: x0[1], yMin: y0[0], yMax: y0[1] }};
  let drag = null;
  let hover = null;

  function resize() {{
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }}

  function plotArea() {{
    const rect = canvas.getBoundingClientRect();
    return {{ left: 58, top: 14, right: rect.width - 18, bottom: rect.height - 36, width: rect.width - 76, height: rect.height - 50 }};
  }}

  function xToPx(x, a) {{ return a.left + (x - view.xMin) / (view.xMax - view.xMin) * a.width; }}
  function yToPx(y, a) {{ return a.bottom - (y - view.yMin) / (view.yMax - view.yMin) * a.height; }}
  function pxToX(px, a) {{ return view.xMin + (px - a.left) / a.width * (view.xMax - view.xMin); }}
  function pxToY(py, a) {{ return view.yMin + (a.bottom - py) / a.height * (view.yMax - view.yMin); }}

  function setYAuto() {{
    const ys = [];
    for (const s of data.series) {{
      const xs = s.x, yy = s[channel];
      for (let i = 0; i < xs.length; i++) if (xs[i] >= view.xMin && xs[i] <= view.xMax && Number.isFinite(yy[i])) ys.push(yy[i]);
    }}
    [view.yMin, view.yMax] = extent(ys.length ? ys : allY(channel));
    draw();
  }}

  function nearestIndex(xs, target) {{
    let lo = 0, hi = xs.length - 1;
    while (lo < hi) {{
      const mid = Math.floor((lo + hi) / 2);
      if (xs[mid] < target) lo = mid + 1; else hi = mid;
    }}
    if (lo > 0 && Math.abs(xs[lo - 1] - target) < Math.abs(xs[lo] - target)) return lo - 1;
    return lo;
  }}

  function findHover(px, py) {{
    const a = plotArea();
    if (px < a.left || px > a.right || py < a.top || py > a.bottom) return null;
    const targetX = pxToX(px, a);
    let best = null;
    for (const s of data.series) {{
      const idx = nearestIndex(s.x, targetX);
      for (const candidate of [idx - 1, idx, idx + 1]) {{
        if (candidate < 0 || candidate >= s.x.length) continue;
        if (!Number.isFinite(s[channel][candidate])) continue;
        const x = xToPx(s.x[candidate], a);
        const y = yToPx(s[channel][candidate], a);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        const dist = Math.hypot(x - px, y - py);
        if (!best || dist < best.dist) {{
          best = {{
            dist,
            x,
            y,
            t: s.x[candidate],
            value: s[channel][candidate],
            omega: s.omega[candidate],
            acc: s.acc[candidate],
            name: s.name,
            color: s.color,
          }};
        }}
      }}
    }}
    return best && best.dist <= 14 ? best : null;
  }}

  function reset() {{
    view.xMin = x0[0]; view.xMax = x0[1]; view.yMin = y0[0]; view.yMax = y0[1];
    draw();
  }}

  function drawGrid(a) {{
    ctx.strokeStyle = "#e2e6eb";
    ctx.fillStyle = "#53606c";
    ctx.lineWidth = 1;
    ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 5; i++) {{
      const y = a.top + a.height * i / 5;
      const val = view.yMax - (view.yMax - view.yMin) * i / 5;
      ctx.beginPath(); ctx.moveTo(a.left, y); ctx.lineTo(a.right, y); ctx.stroke();
      ctx.fillText(val.toFixed(3), a.left - 7, y);
    }}
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let i = 0; i <= 6; i++) {{
      const x = a.left + a.width * i / 6;
      const val = view.xMin + (view.xMax - view.xMin) * i / 6;
      ctx.beginPath(); ctx.moveTo(x, a.top); ctx.lineTo(x, a.bottom); ctx.stroke();
      ctx.fillText(val.toFixed(2), x, a.bottom + 8);
    }}
    ctx.strokeStyle = "#8f99a5";
    ctx.strokeRect(a.left, a.top, a.width, a.height);
  }}

  function drawLines(a) {{
    ctx.save();
    ctx.beginPath();
    ctx.rect(a.left, a.top, a.width, a.height);
    ctx.clip();
    for (const s of data.series) {{
      const xs = s.x, ys = s[channel];
      let start = 0, end = xs.length - 1;
      while (start < xs.length && xs[start] < view.xMin) start++;
      while (end > 0 && xs[end] > view.xMax) end--;
      if (end <= start) continue;
      const stride = Math.max(1, Math.floor((end - start) / Math.max(1, a.width * 2)));
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      let moved = false;
      for (let i = start; i <= end; i += stride) {{
        if (!Number.isFinite(ys[i])) continue;
        const x = xToPx(xs[i], a), y = yToPx(ys[i], a);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        if (!moved) {{ ctx.moveTo(x, y); moved = true; }} else {{ ctx.lineTo(x, y); }}
      }}
      ctx.stroke();
    }}
    ctx.restore();
  }}

  function drawSelection() {{
    if (!drag || drag.mode !== "select") return;
    const x = Math.min(drag.x0, drag.x1), y = Math.min(drag.y0, drag.y1);
    const w = Math.abs(drag.x1 - drag.x0), h = Math.abs(drag.y1 - drag.y0);
    ctx.fillStyle = "rgba(52, 116, 203, .14)";
    ctx.strokeStyle = "rgba(52, 116, 203, .85)";
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
  }}

  function drawHover() {{
    if (!hover) return;
    const a = plotArea();
    const vecText = vec => Array.isArray(vec) ? `[${{vec.map(v => Number.isFinite(v) ? v.toFixed(6) : "n/a").join(", ")}}]` : "n/a";
    ctx.save();
    ctx.strokeStyle = "rgba(23, 33, 43, .35)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(hover.x, a.top);
    ctx.lineTo(hover.x, a.bottom);
    ctx.moveTo(a.left, hover.y);
    ctx.lineTo(a.right, hover.y);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = hover.color;
    ctx.beginPath();
    ctx.arc(hover.x, hover.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();

    const lines = [
      hover.name,
      `t=${{hover.t.toFixed(4)}} min`,
      `${{channel}}=${{hover.value.toFixed(6)}} ${{unit}}`,
      `omega=${{vecText(hover.omega)}}`,
      `acc=${{vecText(hover.acc)}}`,
    ];
    ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    const width = Math.max(...lines.map(line => ctx.measureText(line).width)) + 18;
    const height = 90;
    let x = hover.x + 12;
    let y = hover.y - height - 10;
    if (x + width > a.right) x = hover.x - width - 12;
    if (y < a.top) y = hover.y + 12;
    if (y + height > a.bottom) y = a.bottom - height;

    ctx.fillStyle = "rgba(255,255,255,.96)";
    ctx.strokeStyle = "#9aa4af";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, width, height);
    ctx.strokeRect(x, y, width, height);
    ctx.fillStyle = "#17212b";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    lines.forEach((line, index) => ctx.fillText(line, x + 9, y + 7 + index * 16));
    ctx.restore();
  }}

  function draw() {{
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    const a = plotArea();
    drawGrid(a);
    drawLines(a);
    drawSelection();
    drawHover();
  }}

  canvas.addEventListener("mousedown", ev => {{
    const rect = canvas.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    const mode = ev.button === 2 || ev.altKey ? "pan" : "select";
    drag = {{ mode, x0: x, y0: y, x1: x, y1: y, view: {{...view}} }};
    ev.preventDefault();
  }});

  window.addEventListener("mousemove", ev => {{
    if (!drag) return;
    const rect = canvas.getBoundingClientRect();
    const a = plotArea();
    drag.x1 = ev.clientX - rect.left;
    drag.y1 = ev.clientY - rect.top;
    if (drag.mode === "pan") {{
      const dx = (drag.x1 - drag.x0) / a.width * (drag.view.xMax - drag.view.xMin);
      const dy = (drag.y1 - drag.y0) / a.height * (drag.view.yMax - drag.view.yMin);
      view.xMin = drag.view.xMin - dx; view.xMax = drag.view.xMax - dx;
      view.yMin = drag.view.yMin + dy; view.yMax = drag.view.yMax + dy;
    }}
    draw();
  }});

  canvas.addEventListener("mousemove", ev => {{
    if (drag) return;
    const rect = canvas.getBoundingClientRect();
    hover = findHover(ev.clientX - rect.left, ev.clientY - rect.top);
    draw();
  }});

  canvas.addEventListener("mouseleave", () => {{
    hover = null;
    draw();
  }});

  window.addEventListener("mouseup", () => {{
    if (!drag) return;
    if (drag.mode === "select") {{
      const a = plotArea();
      const w = Math.abs(drag.x1 - drag.x0), h = Math.abs(drag.y1 - drag.y0);
      if (w > 8 && h > 8) {{
        const xA = pxToX(Math.max(a.left, Math.min(drag.x0, drag.x1)), a);
        const xB = pxToX(Math.min(a.right, Math.max(drag.x0, drag.x1)), a);
        const yA = pxToY(Math.min(a.bottom, Math.max(drag.y0, drag.y1)), a);
        const yB = pxToY(Math.max(a.top, Math.min(drag.y0, drag.y1)), a);
        view.xMin = Math.min(xA, xB); view.xMax = Math.max(xA, xB);
        view.yMin = Math.min(yA, yB); view.yMax = Math.max(yA, yB);
      }}
    }}
    drag = null;
    hover = null;
    draw();
  }});

  canvas.addEventListener("wheel", ev => {{
    const rect = canvas.getBoundingClientRect();
    const a = plotArea();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const factor = ev.deltaY < 0 ? 0.86 : 1.16;
    if (ev.shiftKey) {{
      const cx = pxToX(mx, a);
      view.xMin = cx + (view.xMin - cx) * factor;
      view.xMax = cx + (view.xMax - cx) * factor;
    }} else {{
      const cy = pxToY(my, a);
      view.yMin = cy + (view.yMin - cy) * factor;
      view.yMax = cy + (view.yMax - cy) * factor;
    }}
    draw();
    ev.preventDefault();
  }}, {{ passive: false }});

  canvas.addEventListener("dblclick", reset);
  canvas.addEventListener("contextmenu", ev => ev.preventDefault());
  panel.querySelector('[data-act="auto-y"]').addEventListener("click", setYAuto);
  panel.querySelector('[data-act="reset"]').addEventListener("click", reset);
  window.addEventListener("resize", resize);
  resize();
}}

channels.forEach(buildPanel);
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--html", action="store_true", help="write an interactive HTML plot")
    parser.add_argument("--html-output", type=Path, help="write an interactive HTML plot")
    parser.add_argument("--degrees", action="store_true", help="plot RPY in degrees instead of radians")
    args = parser.parse_args()

    log_file = args.log_file.expanduser().resolve()
    output = args.output
    if output is None:
        output = Path("outputs") / f"{log_file.stem}_rpy.png"

    data = parse_log(log_file)
    title = f"{log_file.name} - RPY"
    plot_rpy(data, output, title, args.degrees)

    print(f"wrote {output}")
    if args.html or args.html_output is not None:
        html_output = args.html_output
        if html_output is None:
            html_output = output.with_suffix(".html")
        write_interactive_html(data, html_output, title, args.degrees)
        print(f"wrote {html_output}")
    for imu, rows in data.items():
        print(f"{imu} samples: {len(rows)}")


if __name__ == "__main__":
    main()
