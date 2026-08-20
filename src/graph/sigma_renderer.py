from __future__ import annotations

import json
import math
from typing import Any

import networkx as nx
import pandas as pd

COMMUNITY_COLORS = [
    "#60a5fa", "#34d399", "#f472b6", "#a78bfa", "#fb923c",
    "#22d3ee", "#facc15", "#4ade80", "#c084fc", "#fb7185",
]
ISOLATED_COLOR = "#666666"
COLLABORATION_LOW_COLOR = (72, 72, 78)
COLLABORATION_HIGH_COLOR = (124, 92, 255)


def _sqrt_scaled(values: pd.Series, minimum: float = 2.2, maximum: float = 5.8) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    if numeric.empty:
        return {}
    transformed = numeric.map(math.sqrt)
    low = float(transformed.min())
    high = float(transformed.max())
    if high <= low:
        midpoint = (minimum + maximum) / 2
        return {str(index): midpoint for index in transformed.index}
    return {
        str(index): minimum + (float(value) - low) / (high - low) * (maximum - minimum)
        for index, value in transformed.items()
    }


def _linear_scaled(values: pd.Series, minimum: float = 0.65, maximum: float = 2.8) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if numeric.empty:
        return {}
    low = float(numeric.min())
    high = float(numeric.max())
    if high <= low:
        midpoint = (minimum + maximum) / 2
        return {str(index): midpoint for index in numeric.index}
    return {
        str(index): minimum + (float(value) - low) / (high - low) * (maximum - minimum)
        for index, value in numeric.items()
    }


def _community_map(graph: nx.Graph) -> dict[str, int]:
    mapping: dict[str, int] = {}
    connected = graph.subgraph([node for node, degree in graph.degree() if degree > 0]).copy()
    groups: list[set[str]] = []
    if connected.number_of_nodes() > 0:
        try:
            groups = [set(g) for g in nx.community.greedy_modularity_communities(connected, weight="shared_task_count")]
        except Exception:
            groups = [set(c) for c in nx.connected_components(connected)]
    groups.sort(key=lambda g: (-len(g), sorted(g)[0] if g else ""))
    for index, members in enumerate(groups):
        for node in members:
            mapping[str(node)] = index + 1
    for node, degree in graph.degree():
        if degree == 0:
            mapping[str(node)] = 0
    return mapping


def _edge_color(value: float, minimum: float, maximum: float) -> str:
    ratio = 0.5 if maximum <= minimum else max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
    rgb = tuple(round(low + (high - low) * ratio) for low, high in zip(COLLABORATION_LOW_COLOR, COLLABORATION_HIGH_COLOR))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def build_sigma_html(
    graph: nx.Graph,
    node_dataframe: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    *,
    node_size_metric: str,
    edge_width_metric: str,
    show_labels: bool,
) -> str:
    """Build PixiJS + d3-force collaboration graph.

    Function name is kept for backward compatibility with the Streamlit page.
    """
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#999'>Tidak ada node untuk ditampilkan.</div>"

    node_sizes = _sqrt_scaled(node_dataframe[node_size_metric])
    edge_sizes = _linear_scaled(edge_dataframe[edge_width_metric]) if not edge_dataframe.empty else {}
    community_by_node = _community_map(graph)
    values = pd.to_numeric(edge_dataframe[edge_width_metric], errors="coerce").fillna(0.0).tolist() if not edge_dataframe.empty else []
    minimum = float(min(values)) if values else 0.0
    maximum = float(max(values)) if values else 0.0

    nodes: list[dict[str, Any]] = []
    for index, row in node_dataframe.reset_index(drop=True).iterrows():
        employee = str(row["employee"])
        community = int(community_by_node.get(employee, 0))
        color = COMMUNITY_COLORS[(community - 1) % len(COMMUNITY_COLORS)] if community > 0 else ISOLATED_COLOR
        nodes.append({
            "id": employee,
            "label": employee,
            "size": float(node_sizes.get(str(index), 3.5)),
            "color": color,
            "isolated": int(row.get("collaborator_count", 0)) == 0,
            "collaborator_count": int(row.get("collaborator_count", 0)),
            "collaborative_task_count": int(row.get("collaborative_task_count", 0)),
            "project_count": int(row.get("project_count", 0)),
            "collaborative_hours": float(row.get("collaborative_hours", 0.0)),
            "top_collaborators": list(row.get("top_collaborators", []) or []),
            "top_tasks": list(row.get("top_tasks", []) or []),
        })

    edges: list[dict[str, Any]] = []
    for index, row in edge_dataframe.reset_index(drop=True).iterrows():
        evidence_count = int(row.get(edge_width_metric, 0) or 0)
        edges.append({
            "id": f"edge-{index}",
            "source": str(row["source"]),
            "target": str(row["target"]),
            "size": float(edge_sizes.get(str(index), 0.8)),
            "color": _edge_color(evidence_count, minimum, maximum),
            "collaboration_count": evidence_count,
        })

    payload = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False).replace("</", "<\\/")
    label_setting = "true" if show_labels else "false"

    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
html,body{{margin:0;background:#1e1e1e;color:#ddd;font-family:Inter,system-ui,-apple-system,sans-serif;overflow:hidden}}
.toolbar{{height:46px;display:flex;gap:7px;align-items:center;padding:0 9px;background:#252525;border:1px solid #323232;border-bottom:0;border-radius:8px 8px 0 0;box-sizing:border-box}}
.toolbar input,.toolbar button{{height:29px;background:#2b2b2b;color:#ddd;border:1px solid #3d3d3d;border-radius:5px;padding:0 9px}}
.toolbar input{{flex:1;min-width:0}}
#stage{{height:585px;position:relative;border:1px solid #323232;background:#1e1e1e;overflow:hidden;touch-action:none}}
#pixi-container{{position:absolute;inset:0;cursor:grab}}
#pixi-container.dragging{{cursor:grabbing}}
#status{{position:absolute;right:12px;top:12px;padding:7px 9px;border-radius:6px;background:rgba(37,37,37,.92);border:1px solid #404040;color:#aaa;font-size:11px;pointer-events:none}}
#error{{position:absolute;left:12px;right:12px;top:12px;display:none;padding:10px;background:#4b1f24;border:1px solid #7f1d1d;border-radius:6px;color:#fecaca;font-size:12px;z-index:20}}
</style>
<script src="https://cdn.jsdelivr.net/npm/pixi.js@7.4.3/dist/pixi.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
</head>
<body>
<div class="toolbar">
<input id="search" type="search" placeholder="Cari nama karyawan…" />
<button id="fit">Fit Graph</button>
<button id="reset">Reset View</button>
</div>
<div id="stage">
<div id="pixi-container"></div>
<div id="status">PixiJS + d3-force</div>
<div id="error"></div>
</div>
<script>
(function() {{
  const data = {payload};
  const SHOW_LABELS = {label_setting};
  const stageEl = document.getElementById('stage');
  const container = document.getElementById('pixi-container');
  const errorBox = document.getElementById('error');
  const statusBox = document.getElementById('status');

  function fail(err) {{
    console.error(err);
    errorBox.style.display = 'block';
    errorBox.textContent = 'Graph renderer error: ' + (err && err.message ? err.message : String(err));
  }}

  try {{
    if (!window.PIXI) throw new Error('PixiJS gagal dimuat dari CDN');
    if (!window.d3) throw new Error('d3-force gagal dimuat dari CDN');

    const app = new PIXI.Application({{
      width: stageEl.clientWidth,
      height: stageEl.clientHeight,
      backgroundColor: 0x1e1e1e,
      antialias: true,
      autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
    }});
    container.appendChild(app.view);

    const world = new PIXI.Container();
    const edgeLayer = new PIXI.Graphics();
    const nodeLayer = new PIXI.Container();
    const labelLayer = new PIXI.Container();
    world.addChild(edgeLayer, nodeLayer, labelLayer);
    app.stage.addChild(world);
    world.position.set(stageEl.clientWidth / 2, stageEl.clientHeight / 2);

    const byId = new Map(data.nodes.map(n => [n.id, n]));
    const neighbors = new Map(data.nodes.map(n => [n.id, new Set()]));
    data.edges.forEach(e => {{ neighbors.get(e.source)?.add(e.target); neighbors.get(e.target)?.add(e.source); }});

    data.nodes.forEach((n, i) => {{
      const angle = i * 2.399963229728653;
      const radius = 18 * Math.sqrt(i + 1);
      n.x = Math.cos(angle) * radius;
      n.y = Math.sin(angle) * radius;
    }});

    let selected = null;
    let hovered = null;
    let dragged = null;
    let panning = false;
    let panStart = null;
    let worldStart = null;
    let zoom = 1;

    const sprites = new Map();
    const labels = new Map();
    const hex = value => parseInt(String(value || '#777777').replace('#',''), 16);
    const radiusOf = n => Math.max(3.5, Math.min(8.5, 2.5 + Number(n.size || 3.5) * 0.8));

    data.nodes.forEach(n => {{
      const g = new PIXI.Graphics();
      g.beginFill(hex(n.color), 0.95).drawCircle(0,0,radiusOf(n)).endFill();
      g.eventMode = 'static';
      g.cursor = 'pointer';
      g.on('pointerover', () => {{ hovered = n.id; restyle(); }});
      g.on('pointerout', () => {{ hovered = null; restyle(); }});
      g.on('pointertap', e => {{ e.stopPropagation(); selected = selected === n.id ? null : n.id; restyle(); }});
      g.on('pointerdown', e => {{
        e.stopPropagation();
        dragged = n;
        n.fx = n.x; n.fy = n.y;
        simulation.alphaTarget(0.18).restart();
      }});
      nodeLayer.addChild(g);
      sprites.set(n.id, g);

      const label = new PIXI.Text(n.label, {{fontFamily:'Inter, Arial, sans-serif', fontSize:10, fill:0xd8d8d8}});
      label.anchor.set(0.5,0);
      label.visible = SHOW_LABELS;
      labelLayer.addChild(label);
      labels.set(n.id, label);
    }});

    const simulation = d3.forceSimulation(data.nodes)
      .force('link', d3.forceLink(data.edges).id(d => d.id).distance(d => Math.max(72, 138 - Math.min(50, Number(d.collaboration_count || 1) * 5))).strength(0.24))
      .force('charge', d3.forceManyBody().strength(d => d.isolated ? -110 : -210).distanceMax(700))
      .force('center', d3.forceCenter(0,0))
      .force('collide', d3.forceCollide().radius(d => radiusOf(d) + 16).strength(0.9).iterations(2))
      .force('x', d3.forceX(0).strength(0.018))
      .force('y', d3.forceY(0).strength(0.018))
      .alpha(1).alphaDecay(0.022).alphaMin(0.002).velocityDecay(0.36)
      .on('tick', draw)
      .on('end', () => {{ draw(); fitGraph(true); statusBox.textContent = 'Graph settled'; }});

    function edgeEndpoint(value) {{ return typeof value === 'object' ? value : byId.get(value); }}

    function draw() {{
      edgeLayer.clear();
      const focus = selected || hovered;
      data.edges.forEach(e => {{
        const s = edgeEndpoint(e.source), t = edgeEndpoint(e.target);
        if (!s || !t) return;
        const active = focus && (s.id === focus || t.id === focus);
        const dim = focus && !active;
        edgeLayer.lineStyle(active ? Math.max(1.1,e.size) : Math.max(0.5,e.size*0.7), active ? 0x7c5cff : hex(e.color), active ? 0.9 : dim ? 0.05 : 0.22);
        edgeLayer.moveTo(s.x,s.y).lineTo(t.x,t.y);
      }});
      data.nodes.forEach(n => {{
        const s = sprites.get(n.id), l = labels.get(n.id);
        s.position.set(n.x,n.y);
        l.position.set(n.x,n.y + radiusOf(n) + 3);
      }});
      restyle(false);
    }}

    function restyle(redraw=true) {{
      const focus = selected || hovered;
      data.nodes.forEach(n => {{
        const s = sprites.get(n.id), l = labels.get(n.id);
        const neighbor = focus && neighbors.get(focus)?.has(n.id);
        const active = n.id === focus;
        const unrelated = focus && !active && !neighbor;
        s.clear();
        s.beginFill(active ? 0x8b5cf6 : hex(n.color), unrelated ? 0.14 : 0.95).drawCircle(0,0,radiusOf(n) * (active ? 1.22 : 1)).endFill();
        l.alpha = unrelated ? 0.15 : 1;
        l.visible = SHOW_LABELS && (active || neighbor || Number(n.collaborator_count || 0) >= 4 || zoom >= 1.25);
      }});
      if (redraw) draw();
    }}

    function bounds() {{
      return {{
        minX: Math.min(...data.nodes.map(n => n.x)), maxX: Math.max(...data.nodes.map(n => n.x)),
        minY: Math.min(...data.nodes.map(n => n.y)), maxY: Math.max(...data.nodes.map(n => n.y)),
      }};
    }}

    function fitGraph(animated) {{
      const b = bounds();
      const w = Math.max(1,b.maxX-b.minX), h = Math.max(1,b.maxY-b.minY);
      const target = Math.max(0.16, Math.min(2.6, 0.82*Math.min(stageEl.clientWidth/w, stageEl.clientHeight/h)));
      const cx = (b.minX+b.maxX)/2, cy=(b.minY+b.maxY)/2;
      const tx = stageEl.clientWidth/2 - cx*target, ty=stageEl.clientHeight/2 - cy*target;
      if (!animated) {{ world.position.set(tx,ty); world.scale.set(target); zoom=target; return; }}
      const sx=world.x, sy=world.y, sz=zoom, start=performance.now();
      const step = now => {{
        const t=Math.min(1,(now-start)/420), e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
        zoom=sz+(target-sz)*e;
        world.position.set(sx+(tx-sx)*e, sy+(ty-sy)*e); world.scale.set(zoom);
        if(t<1) requestAnimationFrame(step); else restyle();
      }};
      requestAnimationFrame(step);
    }}

    app.stage.eventMode='static';
    app.stage.hitArea=app.screen;
    app.stage.on('pointerdown', e => {{
      if (dragged) return;
      panning=true; panStart={{x:e.global.x,y:e.global.y}}; worldStart={{x:world.x,y:world.y}}; container.classList.add('dragging');
    }});
    app.stage.on('pointermove', e => {{
      if (dragged) {{
        const local=world.toLocal(e.global); dragged.fx=local.x; dragged.fy=local.y; dragged.x=local.x; dragged.y=local.y; draw(); return;
      }}
      if (panning) world.position.set(worldStart.x+e.global.x-panStart.x, worldStart.y+e.global.y-panStart.y);
    }});
    const up=()=>{{
      if(dragged){{dragged.fx=null;dragged.fy=null;simulation.alphaTarget(0).alpha(.32).restart();}}
      dragged=null;panning=false;container.classList.remove('dragging');
    }};
    app.stage.on('pointerup',up); app.stage.on('pointerupoutside',up);

    stageEl.addEventListener('wheel', e => {{
      e.preventDefault();
      const rect=stageEl.getBoundingClientRect();
      const p=new PIXI.Point(e.clientX-rect.left,e.clientY-rect.top);
      const before=world.toLocal(p);
      zoom=Math.max(.08,Math.min(8,zoom*Math.exp(-e.deltaY*.0013)));
      world.scale.set(zoom);
      const after=world.toGlobal(before);
      world.position.x += p.x-after.x; world.position.y += p.y-after.y;
      restyle();
    }},{{passive:false}});

    document.getElementById('fit').onclick=()=>fitGraph(true);
    document.getElementById('reset').onclick=()=>{{selected=null;hovered=null;simulation.alpha(.45).restart();setTimeout(()=>fitGraph(true),160);}};
    document.getElementById('search').addEventListener('input', e => {{
      const q=String(e.target.value||'').trim().toLocaleLowerCase();
      if(!q){{selected=null;restyle();return;}}
      const n=data.nodes.find(x=>x.label.toLocaleLowerCase().includes(q));
      if(n){{selected=n.id;const target=Math.max(zoom,1.35);world.scale.set(target);zoom=target;world.position.set(stageEl.clientWidth/2-n.x*target,stageEl.clientHeight/2-n.y*target);restyle();}}
    }});

    setTimeout(() => fitGraph(true), 550);
  }} catch (err) {{ fail(err); }}
}})();
</script>
</body>
</html>
"""
