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
ISOLATED_COLOR = "#475569"
COLLABORATION_LOW_COLOR = (71, 85, 105)
COLLABORATION_HIGH_COLOR = (251, 146, 60)


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
    """Build a smooth Obsidian-inspired Sigma.js collaboration explorer."""
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#94a3b8'>Tidak ada node untuk ditampilkan.</div>"

    n_nodes = max(graph.number_of_nodes(), 1)
    k = max(0.32, min(1.05, 3.2 / math.sqrt(n_nodes)))
    positions = nx.spring_layout(
        graph,
        seed=42,
        weight="shared_task_count",
        k=k,
        iterations=260,
        scale=1.7,
    )

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
        x, y = positions.get(employee, (0.0, 0.0))
        community = int(community_by_node.get(employee, 0))
        collaborator_count = int(row.get("collaborator_count", 0))
        color = COMMUNITY_COLORS[(community - 1) % len(COMMUNITY_COLORS)] if community > 0 else ISOLATED_COLOR
        nodes.append(
            {
                "id": employee,
                "label": employee,
                "x": float(x),
                "y": float(y),
                "size": float(node_sizes.get(str(index), 3.5)),
                "base_color": color,
                "color": color,
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
                "size": float(edge_sizes.get(str(index), 0.9)),
                "base_color": _edge_color(evidence_count, collaboration_min, collaboration_max),
                "color": _edge_color(evidence_count, collaboration_min, collaboration_max),
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
    label_setting = "true" if show_labels else "false"

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin:0; padding:0; background:#111318; color:#e5e7eb; font-family:Inter,system-ui,-apple-system,sans-serif; overflow:hidden; }}
    .toolbar {{ height:48px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid #272a31; border-bottom:0; border-radius:9px 9px 0 0; background:#191b20; box-sizing:border-box; position:relative; z-index:10; }}
    .toolbar input, .toolbar button {{ height:30px; border-radius:6px; border:1px solid #353842; background:#202228; color:#e5e7eb; padding:0 9px; }}
    .toolbar input {{ width:100%; box-sizing:border-box; outline:none; }}
    .toolbar input:focus {{ border-color:#7c5cff; box-shadow:0 0 0 2px rgba(124,92,255,.16); }}
    .toolbar button {{ cursor:pointer; white-space:nowrap; transition:background .14s ease,border-color .14s ease; }}
    .toolbar button:hover {{ background:#292c34; border-color:#4a4e5b; }}
    .toolbar .hint {{ color:#737782; font-size:10px; white-space:nowrap; }}
    .search-wrap {{ position:relative; min-width:240px; flex:1; }}
    .search-results {{ display:none; position:absolute; top:34px; left:0; right:0; z-index:30; max-height:260px; overflow-y:auto; border:1px solid #3a3d46; border-radius:7px; background:#202228; box-shadow:0 12px 30px rgba(0,0,0,.35); }}
    .search-result {{ width:100%; border:0; border-bottom:1px solid rgba(80,84,96,.4); border-radius:0; background:#202228; color:#e5e7eb; text-align:left; padding:8px 10px; cursor:pointer; font-size:12px; }}
    .search-result:hover, .search-result:focus {{ background:#2b273a; color:#fff; outline:none; }}
    .search-empty {{ padding:9px 10px; color:#7d828d; font-size:11px; }}
    #stage {{ height:568px; position:relative; border:1px solid #272a31; background:#111318; box-sizing:border-box; }}
    #sigma-container {{ position:absolute; inset:0; cursor:grab; }}
    #sigma-container:active {{ cursor:grabbing; }}
    #info-panel {{ position:absolute; display:none; z-index:9; right:12px; top:12px; width:300px; max-height:180px; overflow:auto; padding:10px 12px; border:1px solid #3a3d46; border-radius:8px; background:rgba(27,29,35,.94); backdrop-filter:blur(6px); font-size:12px; line-height:1.45; }}
    #legend {{ position:absolute; left:12px; bottom:12px; z-index:7; width:226px; padding:9px 10px; border:1px solid rgba(70,74,86,.78); border-radius:9px; background:rgba(27,29,35,.90); backdrop-filter:blur(6px); }}
    .legend-title {{ color:#f3f4f6; font-size:11px; font-weight:750; }}
    .legend-subtitle {{ color:#969ba6; font-size:9px; margin-top:2px; line-height:1.3; }}
    .scale-bar {{ height:7px; border-radius:999px; margin:8px 0 5px; border:1px solid rgba(255,255,255,.09); }}
    .scale-labels {{ display:flex; justify-content:space-between; color:#c4c7ce; font-size:9px; font-weight:650; }}
    .legend-note {{ color:#777c87; font-size:9px; margin-top:6px; }}
    #detail {{ height:185px; padding:12px; border:1px solid #272a31; border-top:0; border-radius:0 0 9px 9px; background:#191b20; font-size:12px; line-height:1.45; box-sizing:border-box; overflow:hidden; }}
    .detail-grid {{ display:grid; grid-template-columns:minmax(210px,.8fr) minmax(300px,1.2fr); gap:14px; height:100%; }}
    .summary-card {{ border:1px solid #30333b; border-radius:8px; padding:10px; background:#202228; height:100%; box-sizing:border-box; overflow:hidden; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:6px; margin-top:8px; }}
    .metric {{ border:1px solid #30333b; border-radius:7px; padding:6px; background:#181a1f; }}
    .metric b {{ display:block; font-size:14px; color:#f3f4f6; }}
    .muted {{ color:#969ba6; }}
    .title {{ color:#f3f4f6; font-size:14px; font-weight:700; margin-bottom:3px; }}
    .section-title {{ color:#cfd2d8; font-weight:700; margin-bottom:5px; }}
    .detail-scroll {{ min-height:0; height:100%; overflow-y:auto; padding-right:4px; }}
    .list-row {{ display:flex; justify-content:space-between; gap:10px; padding:4px 0; border-bottom:1px solid rgba(80,84,96,.35); }}
    .pill {{ display:inline-block; margin:3px 3px 0 0; padding:2px 6px; border:1px solid #3a3d46; border-radius:999px; color:#cfd2d8; font-size:10px; }}
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
    <span class="hint">hover · click focus · drag · smooth zoom</span>
  </div>
  <div id="stage">
    <div id="sigma-container"></div>
    <div id="info-panel"></div>
    <div id="legend"></div>
  </div>
  <div id="detail"><span class="muted">Klik node untuk fokus relasi langsung. Scroll untuk zoom jauh dan drag untuk eksplorasi.</span></div>

  <script type="module">
    import Graph from "https://cdn.jsdelivr.net/npm/graphology@0.26.0/+esm";
    import Sigma from "https://cdn.jsdelivr.net/npm/sigma@3/+esm";

    const data = {payload};
    const graph = new Graph({{type:"undirected", multi:false}});
    data.nodes.forEach(n => graph.addNode(n.id, n));
    data.edges.forEach(e => graph.addEdgeWithKey(e.id, e.source, e.target, e));

    const container = document.getElementById("sigma-container");
    const detail = document.getElementById("detail");
    const infoPanel = document.getElementById("info-panel");
    const legend = document.getElementById("legend");
    const searchWrap = document.getElementById("employee-search-wrap");
    const search = document.getElementById("employee-search");
    const searchResults = document.getElementById("employee-search-results");
    const fitButton = document.getElementById("fit");
    const isolateButton = document.getElementById("isolate");
    const resetButton = document.getElementById("reset");

    const scale = data.collaboration_scale || {{min:0,max:0,low_color:"#475569",high_color:"#fb923c"}};
    legend.innerHTML = `<div class="legend-title">Evidence kolaborasi (Note)</div>` +
      `<div class="legend-subtitle">Garis makin kuat ketika evidence makin banyak.</div>` +
      `<div class="scale-bar" style="background:linear-gradient(90deg,${{scale.low_color}},${{scale.high_color}})"></div>` +
      `<div class="scale-labels"><span>${{scale.min}}</span><span>${{scale.max}} evidence</span></div>` +
      `<div class="legend-note">Klik node untuk mode focus ala Obsidian.</div>`;

    const employeeOptions = data.nodes.slice().sort((a,b) => a.label.localeCompare(b.label)).map(n => ({{...n, searchLabel:n.label.toLocaleLowerCase()}}));
    let selectedNode = null;
    let hoveredNode = null;
    let hoveredEdge = null;
    let draggedNode = null;
    let isDragging = false;
    let hideIsolated = false;
    let cameraRatio = 1;
    let refreshQueued = false;
    let suppressNextStageClick = false;

    const neighborCache = new Map();
    graph.forEachNode(node => neighborCache.set(node, new Set(graph.neighbors(node))));
    const isNeighbor = (node, focus) => !!focus && (neighborCache.get(focus)?.has(node) || false);

    const renderer = new Sigma(graph, container, {{
      renderLabels: {label_setting},
      labelColor: {{attribute:"labelColor", color:"#d7d9df"}},
      labelSize: 10,
      labelDensity: 0.52,
      labelGridCellSize: 70,
      defaultNodeColor: "#a5a7ad",
      defaultEdgeColor: "#393c45",
      enableEdgeEvents: true,
      minCameraRatio: 0.0025,
      maxCameraRatio: 14,
      nodeReducer: (node, attrs) => {{
        const result = {{...attrs, color:attrs.base_color || attrs.color, labelColor:"#d7d9df"}};
        if (hideIsolated && attrs.isolated) {{ result.hidden = true; return result; }}
        const focus = selectedNode || hoveredNode;
        const neighbor = isNeighbor(node, focus);
        const important = attrs.collaborator_count >= 4;
        const zoomAllowsLabel = cameraRatio < 0.72;
        if (!{label_setting} || (!focus && !important && !zoomAllowsLabel)) result.label = "";

        if (focus && node !== focus && !neighbor) {{
          result.color = "#2a2d34";
          result.labelColor = "#4f535d";
          result.size = Math.max(1.45, attrs.size * 0.78);
          result.zIndex = 0;
        }} else if (node === focus) {{
          result.color = "#8b5cf6";
          result.labelColor = "#ffffff";
          result.size = Math.max(4.0, Math.min(7.4, attrs.size * 1.22));
          result.forceLabel = true;
          result.zIndex = 8;
        }} else if (neighbor) {{
          result.color = attrs.base_color || attrs.color;
          result.labelColor = "#f3f4f6";
          result.size = Math.max(2.6, Math.min(6.4, attrs.size * 1.04));
          result.forceLabel = true;
          result.zIndex = 5;
        }}
        return result;
      }},
      edgeReducer: (edge, attrs) => {{
        const result = {{...attrs, color:attrs.base_color || attrs.color}};
        const focus = selectedNode || hoveredNode;
        if (focus) {{
          const [source, target] = graph.extremities(edge);
          const connected = source === focus || target === focus;
          if (!connected) {{
            result.color = "#24272d";
            result.size = Math.max(0.22, attrs.size * 0.36);
            result.zIndex = 0;
          }} else {{
            result.color = selectedNode ? "#7655d9" : "#6d5aa8";
            result.size = Math.max(1.0, Math.min(3.8, attrs.size * 1.12));
            result.zIndex = 6;
          }}
        }} else {{
          result.size = Math.max(0.45, attrs.size * 0.78);
        }}
        return result;
      }},
    }});

    function scheduleRefresh() {{
      if (refreshQueued) return;
      refreshQueued = true;
      requestAnimationFrame(() => {{ refreshQueued = false; renderer.refresh(); }});
    }}

    renderer.getCamera().on("updated", state => {{
      cameraRatio = state.ratio;
      scheduleRefresh();
    }});

    function closeSearchResults() {{ searchResults.style.display = "none"; searchResults.innerHTML = ""; }}
    function matchingEmployees(query) {{
      const normalized = String(query || "").trim().toLocaleLowerCase();
      if (!normalized) return [];
      return employeeOptions.filter(n => n.searchLabel.includes(normalized)).slice(0,20);
    }}
    function renderSearchResults(query) {{
      const matches = matchingEmployees(query);
      searchResults.innerHTML = "";
      if (!String(query || "").trim()) {{ closeSearchResults(); return; }}
      if (!matches.length) {{
        const empty = document.createElement("div");
        empty.className = "search-empty";
        empty.textContent = "Nama karyawan tidak ditemukan";
        searchResults.appendChild(empty);
        searchResults.style.display = "block";
        return;
      }}
      matches.forEach(n => {{
        const button = document.createElement("button");
        button.type = "button";
        button.className = "search-result";
        button.textContent = n.label;
        button.addEventListener("mousedown", event => event.preventDefault());
        button.addEventListener("click", () => {{ search.value = n.label; closeSearchResults(); focusNode(n.id, true); search.blur(); }});
        searchResults.appendChild(button);
      }});
      searchResults.style.display = "block";
    }}

    function topCollaboratorRows(items) {{
      if (!items || !items.length) return '<span class="muted">Belum ada collaborator evidence.</span>';
      return items.slice(0,5).map(item => `<div class="list-row"><span>${{item}}</span></div>`).join("");
    }}
    function nodeDetail(node) {{
      const a = graph.getNodeAttributes(node);
      const tasks = (a.top_tasks || []).slice(0,5).map(x => `<span class="pill">${{x}}</span>`).join("");
      detail.innerHTML = `<div class="detail-grid"><div class="summary-card"><div class="title">${{a.label}}</div><div class="summary-grid"><div class="metric"><b>${{a.collaborator_count}}</b><span class="muted">Collaborators</span></div><div class="metric"><b>${{a.collaborative_task_count}}</b><span class="muted">Note evidence</span></div><div class="metric"><b>${{a.project_count}}</b><span class="muted">Projects</span></div><div class="metric"><b>${{Number(a.collaborative_hours).toFixed(1)}}</b><span class="muted">Related hours</span></div></div></div><div class="detail-scroll"><div class="section-title">Top Collaborators</div>${{topCollaboratorRows(a.top_collaborators)}}<div class="section-title" style="margin-top:9px">Task Context</div>${{tasks || '<span class="muted">Belum ada task context.</span>'}}</div></div>`;
    }}
    function showNodeInfo(node) {{
      const a = graph.getNodeAttributes(node);
      infoPanel.style.display = "block";
      infoPanel.innerHTML = `<div class="title">${{a.label}}</div><b>${{a.collaborator_count}}</b> collaborator · <b>${{a.collaborative_task_count}}</b> Note evidence · <b>${{Number(a.collaborative_hours).toFixed(2)}}</b> related hours`;
    }}
    function showEdgeInfo(edge) {{
      const a = graph.getEdgeAttributes(edge);
      infoPanel.style.display = "block";
      infoPanel.innerHTML = `<div class="title">${{a.source}} ↔ ${{a.target}}</div><b>${{a.collaboration_count}} evidence Note</b><br><span class="muted">A → B:</span> ${{a.a_to_b_count}} · <span class="muted">B → A:</span> ${{a.b_to_a_count}}<br><span class="muted">Jam terkait:</span> ${{Number(a.related_hours).toFixed(2)}}<br><span class="muted">Task context:</span> ${{(a.tasks || []).join(", ") || "-"}}<br><span class="muted">Project:</span> ${{(a.projects || []).join(", ") || "-"}}`;
    }}
    function restoreInfoPanel() {{
      if (hoveredNode) showNodeInfo(hoveredNode);
      else if (hoveredEdge) showEdgeInfo(hoveredEdge);
      else if (selectedNode) showNodeInfo(selectedNode);
      else infoPanel.style.display = "none";
    }}

    function focusNode(node, navigate=false) {{
      selectedNode = node || null;
      if (!node) {{
        search.value = "";
        closeSearchResults();
        detail.innerHTML = '<span class="muted">Klik node untuk fokus relasi langsung. Scroll untuk zoom jauh dan drag untuk eksplorasi.</span>';
        restoreInfoPanel();
        scheduleRefresh();
        return;
      }}
      const attrs = graph.getNodeAttributes(node);
      search.value = attrs.label || node;
      nodeDetail(node);
      showNodeInfo(node);
      if (navigate) {{
        const position = renderer.getNodeDisplayData(node);
        if (position) renderer.getCamera().animate({{x:position.x,y:position.y,ratio:Math.min(0.34, cameraRatio)}}, {{duration:520, easing:"quadraticInOut"}});
      }}
      scheduleRefresh();
    }}

    renderer.on("clickNode", ({{node}}) => {{
      suppressNextStageClick = true;
      focusNode(node, false);
      setTimeout(() => {{ suppressNextStageClick = false; }}, 0);
    }});
    renderer.on("clickStage", () => {{
      if (suppressNextStageClick) {{ suppressNextStageClick = false; return; }}
      focusNode(null);
    }});
    renderer.on("enterNode", ({{node}}) => {{ hoveredNode = node; showNodeInfo(node); scheduleRefresh(); }});
    renderer.on("leaveNode", () => {{ hoveredNode = null; restoreInfoPanel(); scheduleRefresh(); }});
    renderer.on("enterEdge", ({{edge}}) => {{ hoveredEdge = edge; if (!hoveredNode) showEdgeInfo(edge); }});
    renderer.on("leaveEdge", () => {{ hoveredEdge = null; restoreInfoPanel(); }});

    renderer.on("downNode", ({{node}}) => {{
      isDragging = true;
      draggedNode = node;
      renderer.getCamera().disable();
    }});
    renderer.getMouseCaptor().on("mousemovebody", event => {{
      if (!isDragging || !draggedNode) return;
      const pos = renderer.viewportToGraph(event);
      graph.setNodeAttribute(draggedNode, "x", pos.x);
      graph.setNodeAttribute(draggedNode, "y", pos.y);
      event.preventSigmaDefault?.();
      event.original?.preventDefault?.();
      event.original?.stopPropagation?.();
    }});
    renderer.getMouseCaptor().on("mouseup", () => {{
      isDragging = false;
      draggedNode = null;
      renderer.getCamera().enable();
      scheduleRefresh();
    }});

    search.addEventListener("input", () => renderSearchResults(search.value));
    search.addEventListener("focus", () => renderSearchResults(search.value));
    search.addEventListener("keydown", event => {{
      if (event.key === "Escape") {{ closeSearchResults(); search.blur(); return; }}
      if (event.key !== "Enter") return;
      const first = matchingEmployees(search.value)[0];
      if (!first) return;
      event.preventDefault();
      search.value = first.label;
      closeSearchResults();
      focusNode(first.id, true);
      search.blur();
    }});
    search.addEventListener("search", () => {{ if (!search.value.trim()) focusNode(null); }});
    document.addEventListener("click", event => {{ if (!searchWrap.contains(event.target)) closeSearchResults(); }});

    fitButton.addEventListener("click", () => renderer.getCamera().animatedReset({{duration:520, easing:"quadraticInOut"}}));
    isolateButton.addEventListener("click", () => {{
      hideIsolated = !hideIsolated;
      isolateButton.textContent = hideIsolated ? "Show Isolated" : "Hide Isolated";
      scheduleRefresh();
    }});
    resetButton.addEventListener("click", () => {{
      focusNode(null);
      hideIsolated = false;
      isolateButton.textContent = "Hide Isolated";
      renderer.getCamera().animatedReset({{duration:520, easing:"quadraticInOut"}});
      scheduleRefresh();
    }});
  </script>
</body>
</html>
"""
