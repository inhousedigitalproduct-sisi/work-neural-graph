from __future__ import annotations

import json
import math
from typing import Any

import networkx as nx
import pandas as pd


COMMUNITY_COLORS = [
    "#60a5fa",
    "#34d399",
    "#f472b6",
    "#a78bfa",
    "#fb923c",
    "#22d3ee",
    "#facc15",
    "#4ade80",
    "#c084fc",
    "#fb7185",
]
ISOLATED_COLOR = "#555861"
COLLABORATION_LOW_COLOR = (75, 78, 88)
COLLABORATION_HIGH_COLOR = (139, 92, 246)


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


def _linear_scaled(values: pd.Series, minimum: float = 0.55, maximum: float = 2.3) -> dict[str, float]:
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
    communities: list[set[str]] = []
    if connected.number_of_nodes() > 0:
        try:
            communities = [
                set(group)
                for group in nx.community.greedy_modularity_communities(
                    connected,
                    weight="shared_task_count",
                )
            ]
        except Exception:
            communities = [set(component) for component in nx.connected_components(connected)]
    communities.sort(key=lambda group: (-len(group), sorted(group)[0] if group else ""))
    for index, members in enumerate(communities):
        for node in members:
            mapping[str(node)] = index + 1
    for node, degree in graph.degree():
        if degree == 0:
            mapping[str(node)] = 0
    return mapping


def _edge_color(value: float, minimum: float, maximum: float) -> str:
    ratio = 0.5 if maximum <= minimum else max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
    rgb = tuple(
        round(low + (high - low) * ratio)
        for low, high in zip(COLLABORATION_LOW_COLOR, COLLABORATION_HIGH_COLOR)
    )
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
    """Build a PixiJS + d3-force collaboration explorer.

    The function name is kept for backward compatibility with the Streamlit page.
    Physics and rendering now run client-side instead of using Sigma.js or a
    server-side spring layout.
    """
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#94a3b8'>Tidak ada node untuk ditampilkan.</div>"

    node_sizes = _sqrt_scaled(node_dataframe[node_size_metric])
    edge_sizes = _linear_scaled(edge_dataframe[edge_width_metric]) if not edge_dataframe.empty else {}
    community_by_node = _community_map(graph)
    values = (
        pd.to_numeric(edge_dataframe[edge_width_metric], errors="coerce").fillna(0.0).tolist()
        if not edge_dataframe.empty
        else []
    )
    collaboration_min = float(min(values)) if values else 0.0
    collaboration_max = float(max(values)) if values else 0.0

    nodes: list[dict[str, Any]] = []
    for index, row in node_dataframe.reset_index(drop=True).iterrows():
        employee = str(row["employee"])
        community = int(community_by_node.get(employee, 0))
        collaborator_count = int(row.get("collaborator_count", 0))
        color = COMMUNITY_COLORS[(community - 1) % len(COMMUNITY_COLORS)] if community > 0 else ISOLATED_COLOR
        nodes.append(
            {
                "id": employee,
                "label": employee,
                "size": float(node_sizes.get(str(index), 3.5)),
                "base_color": color,
                "community": community,
                "isolated": collaborator_count == 0,
                "collaborator_count": collaborator_count,
                "collaborative_task_count": int(row.get("collaborative_task_count", 0)),
                "project_count": int(row.get("project_count", 0)),
                "collaborative_hours": float(row.get("collaborative_hours", 0.0)),
                "collaborators": list(row.get("collaborators", []) or []),
                "top_collaborators": list(row.get("top_collaborators", []) or []),
                "top_tasks": list(row.get("top_tasks", []) or []),
            }
        )

    edges: list[dict[str, Any]] = []
    for index, row in edge_dataframe.reset_index(drop=True).iterrows():
        evidence_count = int(row.get(edge_width_metric, 0) or 0)
        edges.append(
            {
                "id": f"edge-{index}",
                "source": str(row["source"]),
                "target": str(row["target"]),
                "size": float(edge_sizes.get(str(index), 0.8)),
                "base_color": _edge_color(evidence_count, collaboration_min, collaboration_max),
                "collaboration_count": evidence_count,
                "a_to_b_count": int(row.get("a_to_b_count", 0) or 0),
                "b_to_a_count": int(row.get("b_to_a_count", 0) or 0),
                "tasks": list(row.get("shared_tasks", []) or []),
                "projects": list(row.get("projects", []) or []),
                "related_hours": float(row.get("related_hours", 0.0)),
            }
        )

    payload = json.dumps(
        {
            "nodes": nodes,
            "edges": edges,
            "collaboration_scale": {
                "min": int(collaboration_min),
                "max": int(collaboration_max),
                "low_color": "#{:02x}{:02x}{:02x}".format(*COLLABORATION_LOW_COLOR),
                "high_color": "#{:02x}{:02x}{:02x}".format(*COLLABORATION_HIGH_COLOR),
            },
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    html = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body { margin:0; padding:0; background:#1e1e1e; color:#d8d8d8; font-family:Inter,system-ui,-apple-system,sans-serif; overflow:hidden; }
    .toolbar { height:46px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid #323232; border-bottom:0; border-radius:8px 8px 0 0; background:#252525; box-sizing:border-box; position:relative; z-index:20; }
    .toolbar input, .toolbar button { height:29px; border-radius:5px; border:1px solid #3d3d3d; background:#2b2b2b; color:#ddd; padding:0 9px; }
    .toolbar input { width:100%; box-sizing:border-box; outline:none; }
    .toolbar input:focus { border-color:#7c5cff; box-shadow:0 0 0 2px rgba(124,92,255,.16); }
    .toolbar button { cursor:pointer; white-space:nowrap; }
    .toolbar button:hover { background:#333; border-color:#4a4a4a; }
    .toolbar .hint { color:#777; font-size:10px; white-space:nowrap; }
    .search-wrap { position:relative; min-width:240px; flex:1; }
    .search-results { display:none; position:absolute; top:33px; left:0; right:0; z-index:30; max-height:260px; overflow-y:auto; border:1px solid #454545; border-radius:6px; background:#292929; box-shadow:0 12px 30px rgba(0,0,0,.35); }
    .search-result { width:100%; border:0; border-bottom:1px solid #343434; border-radius:0; background:#292929; color:#ddd; text-align:left; padding:8px 10px; cursor:pointer; font-size:12px; }
    .search-result:hover, .search-result:focus { background:#34303f; color:#fff; outline:none; }
    .search-empty { padding:9px 10px; color:#818181; font-size:11px; }
    #stage { height:585px; position:relative; border:1px solid #323232; background:#1e1e1e; box-sizing:border-box; overflow:hidden; touch-action:none; }
    #pixi-container { position:absolute; inset:0; cursor:grab; }
    #pixi-container.dragging { cursor:grabbing; }
    #info-panel { position:absolute; display:none; z-index:15; right:12px; top:12px; width:300px; max-height:180px; overflow:auto; padding:10px 12px; border:1px solid #454545; border-radius:7px; background:rgba(37,37,37,.95); font-size:12px; line-height:1.45; pointer-events:none; }
    #legend { position:absolute; left:12px; bottom:12px; z-index:14; width:228px; padding:9px 10px; border:1px solid #404040; border-radius:8px; background:rgba(37,37,37,.92); pointer-events:none; }
    .legend-title { color:#efefef; font-size:11px; font-weight:700; }
    .legend-subtitle { color:#999; font-size:9px; margin-top:2px; line-height:1.3; }
    .scale-bar { height:7px; border-radius:999px; margin:8px 0 5px; border:1px solid rgba(255,255,255,.08); }
    .scale-labels { display:flex; justify-content:space-between; color:#c5c5c5; font-size:9px; font-weight:650; }
    .legend-note { color:#858585; font-size:9px; margin-top:6px; }
    #detail { height:185px; padding:12px; border:1px solid #323232; border-top:0; border-radius:0 0 8px 8px; background:#252525; font-size:12px; line-height:1.45; box-sizing:border-box; overflow:hidden; }
    .detail-grid { display:grid; grid-template-columns:minmax(210px,.8fr) minmax(300px,1.2fr); gap:14px; height:100%; }
    .summary-card { border:1px solid #393939; border-radius:7px; padding:10px; background:#2b2b2b; height:100%; box-sizing:border-box; overflow:hidden; }
    .summary-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:6px; margin-top:8px; }
    .metric { border:1px solid #393939; border-radius:6px; padding:6px; background:#222; }
    .metric b { display:block; font-size:14px; color:#f0f0f0; }
    .muted { color:#999; }
    .title { color:#f0f0f0; font-size:14px; font-weight:700; margin-bottom:3px; }
    .section-title { color:#d3d3d3; font-weight:700; margin-bottom:5px; }
    .detail-scroll { min-height:0; height:100%; overflow-y:auto; padding-right:4px; }
    .list-row { display:flex; justify-content:space-between; gap:10px; padding:4px 0; border-bottom:1px solid #383838; }
    .pill { display:inline-block; margin:3px 3px 0 0; padding:2px 6px; border:1px solid #444; border-radius:999px; color:#ccc; font-size:10px; }
  </style>
</head>
<body>
  <div class="toolbar">
    <div id="employee-search-wrap" class="search-wrap">
      <input id="employee-search" type="search" placeholder="Cari nama karyawan…" autocomplete="off" aria-label="Cari karyawan" />
      <div id="employee-search-results" class="search-results" role="listbox"></div>
    </div>
    <button id="fit">Fit Graph</button>
    <button id="isolate">Hide Isolated</button>
    <button id="reset">Reset View</button>
    <span class="hint">drag · scroll zoom · physics settle</span>
  </div>
  <div id="stage">
    <div id="pixi-container"></div>
    <div id="info-panel"></div>
    <div id="legend"></div>
  </div>
  <div id="detail"><span class="muted">Klik node untuk fokus relasi langsung. Drag node untuk mengaktifkan physics sementara.</span></div>

  <script type="module">
    import * as PIXI from "https://cdn.jsdelivr.net/npm/pixi.js@8.13.2/+esm";
    import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide, forceX, forceY } from "https://cdn.jsdelivr.net/npm/d3-force@3/+esm";

    const data = __PAYLOAD__;
    const SHOW_LABELS = __LABEL_SETTING__;
    const container = document.getElementById("pixi-container");
    const stageEl = document.getElementById("stage");
    const detail = document.getElementById("detail");
    const infoPanel = document.getElementById("info-panel");
    const legend = document.getElementById("legend");
    const searchWrap = document.getElementById("employee-search-wrap");
    const search = document.getElementById("employee-search");
    const searchResults = document.getElementById("employee-search-results");
    const fitButton = document.getElementById("fit");
    const isolateButton = document.getElementById("isolate");
    const resetButton = document.getElementById("reset");

    const scale = data.collaboration_scale || {min:0,max:0,low_color:"#4b4e58",high_color:"#8b5cf6"};
    legend.innerHTML = `<div class="legend-title">Evidence kolaborasi (Note)</div>` +
      `<div class="legend-subtitle">d3-force mengatur posisi; PixiJS/WebGL merender graph.</div>` +
      `<div class="scale-bar" style="background:linear-gradient(90deg,${scale.low_color},${scale.high_color})"></div>` +
      `<div class="scale-labels"><span>${scale.min}</span><span>${scale.max} evidence</span></div>` +
      `<div class="legend-note">Node settle otomatis seperti force graph, bukan idle wobble.</div>`;

    const app = new PIXI.Application();
    await app.init({
      resizeTo: stageEl,
      background: "#1e1e1e",
      antialias: true,
      autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      preference: "webgl",
    });
    container.appendChild(app.canvas);

    const world = new PIXI.Container();
    const edgeLayer = new PIXI.Graphics();
    const nodeLayer = new PIXI.Container();
    const labelLayer = new PIXI.Container();
    world.addChild(edgeLayer, nodeLayer, labelLayer);
    app.stage.addChild(world);

    const nodeById = new Map(data.nodes.map(n => [n.id, n]));
    const neighbors = new Map(data.nodes.map(n => [n.id, new Set()]));
    for (const edge of data.edges) {
      neighbors.get(edge.source)?.add(edge.target);
      neighbors.get(edge.target)?.add(edge.source);
    }

    const colorToNumber = value => Number.parseInt(String(value || "#777777").replace("#", ""), 16);
    const employeeOptions = data.nodes.slice().sort((a,b) => a.label.localeCompare(b.label)).map(n => ({...n, searchLabel:n.label.toLocaleLowerCase()}));
    let selectedNode = null;
    let hoveredNode = null;
    let hideIsolated = false;
    let draggedNode = null;
    let draggingNode = false;
    let panning = false;
    let panStart = null;
    let worldStart = null;
    let scaleFactor = 1;
    let suppressStageTap = false;

    for (let i = 0; i < data.nodes.length; i += 1) {
      const n = data.nodes[i];
      const angle = i * 2.399963229728653;
      const radius = 14 * Math.sqrt(i + 1);
      n.x = Math.cos(angle) * radius;
      n.y = Math.sin(angle) * radius;
    }

    const nodeSprites = new Map();
    const labelSprites = new Map();

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[ch]));
    }

    function nodeRadius(node) {
      return Math.max(3.4, Math.min(8.5, 2.6 + Number(node.size || 3.5) * 0.8));
    }

    function makeNodeSprite(node) {
      const g = new PIXI.Graphics();
      g.circle(0, 0, nodeRadius(node)).fill(colorToNumber(node.base_color));
      g.eventMode = "static";
      g.cursor = "pointer";
      g.on("pointerover", () => {
        hoveredNode = node.id;
        showNodeInfo(node.id);
        refreshStyles();
      });
      g.on("pointerout", () => {
        hoveredNode = null;
        restoreInfoPanel();
        refreshStyles();
      });
      g.on("pointertap", event => {
        event.stopPropagation();
        suppressStageTap = true;
        focusNode(node.id, false);
        queueMicrotask(() => { suppressStageTap = false; });
      });
      g.on("pointerdown", event => {
        event.stopPropagation();
        draggingNode = true;
        draggedNode = node;
        node.fx = node.x;
        node.fy = node.y;
        simulation.alphaTarget(0.16).restart();
      });
      nodeLayer.addChild(g);
      nodeSprites.set(node.id, g);

      const label = new PIXI.Text({
        text: node.label,
        style: new PIXI.TextStyle({fontFamily:"Inter, system-ui, sans-serif", fontSize:10, fill:"#cfcfcf"}),
      });
      label.anchor.set(0.5, 0);
      label.eventMode = "none";
      labelLayer.addChild(label);
      labelSprites.set(node.id, label);
    }

    data.nodes.forEach(makeNodeSprite);

    const simulation = forceSimulation(data.nodes)
      .force("link", forceLink(data.edges).id(d => d.id).distance(d => Math.max(72, 138 - Math.min(50, Number(d.collaboration_count || 1) * 5))).strength(d => Math.min(0.55, 0.10 + Number(d.collaboration_count || 1) * 0.045)))
      .force("charge", forceManyBody().strength(d => d.isolated ? -95 : -185).distanceMax(650))
      .force("center", forceCenter(0, 0).strength(0.055))
      .force("collide", forceCollide().radius(d => nodeRadius(d) + 18).strength(0.92).iterations(2))
      .force("x", forceX(0).strength(0.018))
      .force("y", forceY(0).strength(0.018))
      .alpha(1)
      .alphaDecay(0.021)
      .alphaMin(0.002)
      .velocityDecay(0.38)
      .on("tick", drawGraph)
      .on("end", () => drawGraph());

    function connectedToFocus(edge, focus) {
      const source = typeof edge.source === "object" ? edge.source.id : edge.source;
      const target = typeof edge.target === "object" ? edge.target.id : edge.target;
      return source === focus || target === focus;
    }

    function drawGraph() {
      edgeLayer.clear();
      const focus = selectedNode || hoveredNode;
      for (const edge of data.edges) {
        const source = typeof edge.source === "object" ? edge.source : nodeById.get(edge.source);
        const target = typeof edge.target === "object" ? edge.target : nodeById.get(edge.target);
        if (!source || !target) continue;
        if (hideIsolated && (source.isolated || target.isolated)) continue;
        const active = !!focus && connectedToFocus(edge, focus);
        const dimmed = !!focus && !active;
        const edgeColor = active ? 0x7c5cff : colorToNumber(edge.base_color);
        const alpha = active ? 0.88 : dimmed ? 0.07 : 0.22;
        const width = active ? Math.max(1.05, Number(edge.size || 0.8) * 1.15) : Math.max(0.45, Number(edge.size || 0.8) * 0.72);
        edgeLayer.moveTo(source.x, source.y).lineTo(target.x, target.y).stroke({width, color:edgeColor, alpha});
      }

      for (const node of data.nodes) {
        const sprite = nodeSprites.get(node.id);
        const label = labelSprites.get(node.id);
        if (!sprite || !label) continue;
        sprite.position.set(node.x, node.y);
        label.position.set(node.x, node.y + nodeRadius(node) + 3);
      }
      refreshStyles(false);
    }

    function refreshStyles(redraw=true) {
      const focus = selectedNode || hoveredNode;
      for (const node of data.nodes) {
        const sprite = nodeSprites.get(node.id);
        const label = labelSprites.get(node.id);
        if (!sprite || !label) continue;
        const hidden = hideIsolated && node.isolated;
        sprite.visible = !hidden;
        label.visible = !hidden;
        if (hidden) continue;
        const neighbor = !!focus && (neighbors.get(focus)?.has(node.id) || false);
        const active = node.id === focus;
        const unrelated = !!focus && !active && !neighbor;
        sprite.clear();
        sprite.circle(0, 0, active ? nodeRadius(node) * 1.24 : neighbor ? nodeRadius(node) * 1.07 : nodeRadius(node))
          .fill(active ? 0x8b5cf6 : colorToNumber(node.base_color));
        sprite.alpha = unrelated ? 0.16 : neighbor ? 0.96 : 0.90;
        label.alpha = unrelated ? 0.18 : 1;
        label.style.fill = active ? "#ffffff" : unrelated ? "#666666" : "#d2d2d2";
        const important = Number(node.collaborator_count || 0) >= 4;
        label.visible = !hidden && SHOW_LABELS && (active || neighbor || important || scaleFactor >= 1.25);
      }
      if (redraw) drawGraph();
    }

    function boundsOfVisibleNodes() {
      const visible = data.nodes.filter(n => !(hideIsolated && n.isolated));
      if (!visible.length) return {minX:-1,maxX:1,minY:-1,maxY:1};
      return {
        minX: Math.min(...visible.map(n => n.x)), maxX: Math.max(...visible.map(n => n.x)),
        minY: Math.min(...visible.map(n => n.y)), maxY: Math.max(...visible.map(n => n.y)),
      };
    }

    function fitGraph(animated=true) {
      const bounds = boundsOfVisibleNodes();
      const width = Math.max(1, bounds.maxX - bounds.minX);
      const height = Math.max(1, bounds.maxY - bounds.minY);
      const targetScale = Math.max(0.18, Math.min(2.4, 0.82 * Math.min(stageEl.clientWidth / width, stageEl.clientHeight / height)));
      const centerX = (bounds.minX + bounds.maxX) / 2;
      const centerY = (bounds.minY + bounds.maxY) / 2;
      const targetX = stageEl.clientWidth / 2 - centerX * targetScale;
      const targetY = stageEl.clientHeight / 2 - centerY * targetScale;
      animateWorld(targetX, targetY, targetScale, animated ? 420 : 0);
    }

    function animateWorld(targetX, targetY, targetScale, duration=420) {
      const fromX = world.x, fromY = world.y, fromScale = scaleFactor;
      if (!duration) {
        world.position.set(targetX, targetY);
        world.scale.set(targetScale);
        scaleFactor = targetScale;
        refreshStyles();
        return;
      }
      const started = performance.now();
      const tick = now => {
        const t = Math.min(1, (now - started) / duration);
        const eased = t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t+2, 2)/2;
        scaleFactor = fromScale + (targetScale - fromScale) * eased;
        world.position.set(fromX + (targetX - fromX)*eased, fromY + (targetY - fromY)*eased);
        world.scale.set(scaleFactor);
        if (t < 1) requestAnimationFrame(tick);
        else refreshStyles();
      };
      requestAnimationFrame(tick);
    }

    function focusNode(id, navigate=false) {
      selectedNode = id || null;
      if (!selectedNode) {
        search.value = "";
        closeSearchResults();
        detail.innerHTML = '<span class="muted">Klik node untuk fokus relasi langsung. Drag node untuk mengaktifkan physics sementara.</span>';
        restoreInfoPanel();
        refreshStyles();
        return;
      }
      const node = nodeById.get(selectedNode);
      if (!node) return;
      search.value = node.label || node.id;
      nodeDetail(selectedNode);
      showNodeInfo(selectedNode);
      refreshStyles();
      if (navigate) {
        const targetScale = Math.max(scaleFactor, 1.35);
        animateWorld(stageEl.clientWidth/2 - node.x*targetScale, stageEl.clientHeight/2 - node.y*targetScale, targetScale, 420);
      }
    }

    function closeSearchResults() { searchResults.style.display = "none"; searchResults.innerHTML = ""; }
    function matchingEmployees(query) {
      const normalized = String(query || "").trim().toLocaleLowerCase();
      if (!normalized) return [];
      return employeeOptions.filter(n => n.searchLabel.includes(normalized)).slice(0,20);
    }
    function renderSearchResults(query) {
      const matches = matchingEmployees(query);
      searchResults.innerHTML = "";
      if (!String(query || "").trim()) { closeSearchResults(); return; }
      if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "search-empty";
        empty.textContent = "Nama karyawan tidak ditemukan";
        searchResults.appendChild(empty);
        searchResults.style.display = "block";
        return;
      }
      matches.forEach(n => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "search-result";
        button.textContent = n.label;
        button.addEventListener("mousedown", event => event.preventDefault());
        button.addEventListener("click", () => { search.value = n.label; closeSearchResults(); focusNode(n.id, true); search.blur(); });
        searchResults.appendChild(button);
      });
      searchResults.style.display = "block";
    }

    function topCollaboratorRows(items) {
      if (!items || !items.length) return '<span class="muted">Belum ada collaborator evidence.</span>';
      return items.slice(0,5).map(item => `<div class="list-row"><span>${escapeHtml(item)}</span></div>`).join("");
    }
    function nodeDetail(id) {
      const a = nodeById.get(id);
      const tasks = (a.top_tasks || []).slice(0,5).map(x => `<span class="pill">${escapeHtml(x)}</span>`).join("");
      detail.innerHTML = `<div class="detail-grid"><div class="summary-card"><div class="title">${escapeHtml(a.label)}</div><div class="summary-grid"><div class="metric"><b>${a.collaborator_count}</b><span class="muted">Collaborators</span></div><div class="metric"><b>${a.collaborative_task_count}</b><span class="muted">Note evidence</span></div><div class="metric"><b>${a.project_count}</b><span class="muted">Projects</span></div><div class="metric"><b>${Number(a.collaborative_hours).toFixed(1)}</b><span class="muted">Related hours</span></div></div></div><div class="detail-scroll"><div class="section-title">Top Collaborators</div>${topCollaboratorRows(a.top_collaborators)}<div class="section-title" style="margin-top:9px">Task Context</div>${tasks || '<span class="muted">Belum ada task context.</span>'}</div></div>`;
    }
    function showNodeInfo(id) {
      const a = nodeById.get(id);
      if (!a) return;
      infoPanel.style.display = "block";
      infoPanel.innerHTML = `<div class="title">${escapeHtml(a.label)}</div><b>${a.collaborator_count}</b> collaborator · <b>${a.collaborative_task_count}</b> Note evidence · <b>${Number(a.collaborative_hours).toFixed(2)}</b> related hours`;
    }
    function restoreInfoPanel() {
      if (hoveredNode) showNodeInfo(hoveredNode);
      else if (selectedNode) showNodeInfo(selectedNode);
      else infoPanel.style.display = "none";
    }

    app.stage.eventMode = "static";
    app.stage.hitArea = app.screen;
    app.stage.on("pointertap", () => {
      if (suppressStageTap || draggingNode) return;
      focusNode(null);
    });
    app.stage.on("pointerdown", event => {
      if (draggingNode) return;
      panning = true;
      panStart = {x:event.global.x, y:event.global.y};
      worldStart = {x:world.x, y:world.y};
      container.classList.add("dragging");
    });
    app.stage.on("pointermove", event => {
      if (draggingNode && draggedNode) {
        const local = world.toLocal(event.global);
        draggedNode.fx = local.x;
        draggedNode.fy = local.y;
        draggedNode.x = local.x;
        draggedNode.y = local.y;
        drawGraph();
        return;
      }
      if (panning && panStart && worldStart) {
        world.position.set(worldStart.x + event.global.x - panStart.x, worldStart.y + event.global.y - panStart.y);
      }
    });
    const endPointer = () => {
      if (draggingNode && draggedNode) {
        draggedNode.fx = null;
        draggedNode.fy = null;
        simulation.alphaTarget(0).alpha(0.34).restart();
      }
      draggingNode = false;
      draggedNode = null;
      panning = false;
      panStart = null;
      worldStart = null;
      container.classList.remove("dragging");
    };
    app.stage.on("pointerup", endPointer);
    app.stage.on("pointerupoutside", endPointer);

    stageEl.addEventListener("wheel", event => {
      event.preventDefault();
      const rect = stageEl.getBoundingClientRect();
      const pointer = new PIXI.Point(event.clientX - rect.left, event.clientY - rect.top);
      const before = world.toLocal(pointer);
      const factor = Math.exp(-event.deltaY * 0.0013);
      const nextScale = Math.max(0.08, Math.min(8, scaleFactor * factor));
      scaleFactor = nextScale;
      world.scale.set(nextScale);
      const after = world.toGlobal(before);
      world.position.x += pointer.x - after.x;
      world.position.y += pointer.y - after.y;
      refreshStyles();
    }, {passive:false});

    search.addEventListener("input", () => renderSearchResults(search.value));
    search.addEventListener("focus", () => renderSearchResults(search.value));
    search.addEventListener("keydown", event => {
      if (event.key === "Escape") { closeSearchResults(); search.blur(); return; }
      if (event.key !== "Enter") return;
      const first = matchingEmployees(search.value)[0];
      if (!first) return;
      event.preventDefault();
      search.value = first.label;
      closeSearchResults();
      focusNode(first.id, true);
      search.blur();
    });
    search.addEventListener("search", () => { if (!search.value.trim()) focusNode(null); });
    document.addEventListener("click", event => { if (!searchWrap.contains(event.target)) closeSearchResults(); });

    fitButton.addEventListener("click", () => fitGraph(true));
    isolateButton.addEventListener("click", () => {
      hideIsolated = !hideIsolated;
      isolateButton.textContent = hideIsolated ? "Show Isolated" : "Hide Isolated";
      simulation.alpha(0.24).restart();
      refreshStyles();
      setTimeout(() => fitGraph(true), 120);
    });
    resetButton.addEventListener("click", () => {
      selectedNode = null;
      hoveredNode = null;
      hideIsolated = false;
      isolateButton.textContent = "Hide Isolated";
      search.value = "";
      closeSearchResults();
      detail.innerHTML = '<span class="muted">Klik node untuk fokus relasi langsung. Drag node untuk mengaktifkan physics sementara.</span>';
      simulation.alpha(0.42).restart();
      restoreInfoPanel();
      refreshStyles();
      setTimeout(() => fitGraph(true), 180);
    });

    simulation.on("tick.fit", () => {
      if (simulation.alpha() < 0.06 && !world.__initialFitDone) {
        world.__initialFitDone = true;
        fitGraph(true);
      }
    });
    setTimeout(() => { if (!world.__initialFitDone) { world.__initialFitDone = true; fitGraph(true); } }, 900);
  </script>
</body>
</html>
"""
    return html.replace("__PAYLOAD__", payload).replace("__LABEL_SETTING__", "true" if show_labels else "false")
