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


def _sqrt_scaled(values: pd.Series, minimum: float = 3.8, maximum: float = 9.5) -> dict[str, float]:
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


def _linear_scaled(values: pd.Series, minimum: float = 0.7, maximum: float = 3.5) -> dict[str, float]:
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
        community_id = index + 1
        for node in members:
            mapping[str(node)] = community_id

    for node, degree in graph.degree():
        if degree == 0:
            mapping[str(node)] = 0
    return mapping


def _edge_color(value: float, minimum: float, maximum: float) -> str:
    if maximum <= minimum:
        ratio = 0.5
    else:
        ratio = max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
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
    """Build an interactive Sigma.js employee-collaboration view."""
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#94a3b8'>Tidak ada node untuk ditampilkan.</div>"

    n_nodes = max(graph.number_of_nodes(), 1)
    k = max(0.30, min(1.05, 3.4 / math.sqrt(n_nodes)))
    positions = nx.spring_layout(
        graph,
        seed=42,
        weight="shared_task_count",
        k=k,
        iterations=220,
        scale=1.35,
    )

    node_sizes = _sqrt_scaled(node_dataframe[node_size_metric])
    edge_sizes = _linear_scaled(edge_dataframe[edge_width_metric]) if not edge_dataframe.empty else {}
    community_by_node = _community_map(graph)

    collaboration_values = (
        pd.to_numeric(edge_dataframe["shared_task_count"], errors="coerce").fillna(0.0).tolist()
        if not edge_dataframe.empty
        else []
    )
    collaboration_min = float(min(collaboration_values)) if collaboration_values else 0.0
    collaboration_max = float(max(collaboration_values)) if collaboration_values else 0.0

    nodes: list[dict[str, Any]] = []
    for index, row in node_dataframe.reset_index(drop=True).iterrows():
        employee = str(row["employee"])
        x, y = positions.get(employee, (0.0, 0.0))
        community = int(community_by_node.get(employee, 0))
        collaborator_count = int(row.get("collaborator_count", 0))
        community_color = (
            COMMUNITY_COLORS[(community - 1) % len(COMMUNITY_COLORS)]
            if community > 0
            else ISOLATED_COLOR
        )
        nodes.append(
            {
                "id": employee,
                "label": employee,
                "x": float(x),
                "y": float(y),
                "size": float(node_sizes.get(str(index), 6.0)),
                "base_color": community_color,
                "color": community_color,
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
        collaboration_count = int(row.get("shared_task_count", 0))
        edges.append(
            {
                "id": f"edge-{index}",
                "source": str(row["source"]),
                "target": str(row["target"]),
                "size": float(edge_sizes.get(str(index), 1.0)),
                "color": _edge_color(collaboration_count, collaboration_min, collaboration_max),
                "collaboration_count": collaboration_count,
                "shared_task_count": collaboration_count,
                "shared_tasks": list(row.get("shared_tasks", []) or []),
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
    html, body {{ margin:0; padding:0; background:#020617; color:#e2e8f0; font-family:Inter,system-ui,-apple-system,sans-serif; overflow:hidden; }}
    .toolbar {{ height:58px; display:flex; align-items:center; gap:8px; padding:0 12px; border:1px solid #1e293b; border-bottom:0; border-radius:12px 12px 0 0; background:#0f172a; box-sizing:border-box; }}
    .toolbar select, .toolbar button {{ height:34px; border-radius:8px; border:1px solid #334155; background:#111827; color:#e2e8f0; padding:0 10px; }}
    .toolbar select {{ min-width:250px; flex:1; }}
    .toolbar button {{ cursor:pointer; white-space:nowrap; }}
    .toolbar button.active {{ border-color:#60a5fa; background:#172554; color:#dbeafe; }}
    .toolbar .hint {{ color:#64748b; font-size:11px; white-space:nowrap; }}
    #stage {{ height:500px; position:relative; border:1px solid #1e293b; background:radial-gradient(circle at center,#0f172a 0,#020617 72%); box-sizing:border-box; }}
    #sigma-container {{ position:absolute; inset:0; }}
    #info-panel {{ position:absolute; display:none; z-index:9; right:14px; top:14px; width:310px; max-height:190px; overflow:auto; padding:11px 13px; border:1px solid #334155; border-radius:10px; background:rgba(15,23,42,.96); box-shadow:0 10px 35px rgba(0,0,0,.35); font-size:12px; line-height:1.45; }}
    #legend {{ position:absolute; left:14px; bottom:14px; z-index:7; width:260px; padding:13px; border:1px solid rgba(71,85,105,.75); border-radius:14px; background:linear-gradient(180deg,rgba(15,23,42,.97),rgba(8,15,30,.93)); box-shadow:0 16px 38px rgba(0,0,0,.32); backdrop-filter:blur(8px); }}
    .legend-title {{ color:#f8fafc; font-size:12px; font-weight:800; letter-spacing:.02em; }}
    .legend-subtitle {{ color:#94a3b8; font-size:10px; margin-top:3px; line-height:1.35; }}
    .scale-bar {{ height:12px; border-radius:999px; margin:12px 0 6px; border:1px solid rgba(255,255,255,.14); }}
    .scale-labels {{ display:flex; align-items:center; justify-content:space-between; color:#e2e8f0; font-size:10px; font-weight:700; }}
    .scale-hints {{ display:flex; align-items:center; justify-content:space-between; color:#64748b; font-size:9px; margin-top:2px; }}
    .legend-note {{ color:#64748b; font-size:9px; margin-top:10px; padding-top:8px; border-top:1px solid rgba(71,85,105,.45); }}
    #detail {{ height:270px; padding:14px; border:1px solid #1e293b; border-top:0; border-radius:0 0 12px 12px; background:#0f172a; font-size:13px; line-height:1.5; box-sizing:border-box; overflow:hidden; }}
    .detail-grid {{ display:grid; grid-template-columns:minmax(220px,.8fr) minmax(320px,1.2fr); gap:18px; height:100%; }}
    .summary-card {{ border:1px solid #243244; border-radius:10px; padding:12px; background:#111827; height:100%; box-sizing:border-box; overflow:hidden; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:10px; }}
    .metric {{ border:1px solid #253247; border-radius:8px; padding:8px; background:#0b1220; }}
    .metric b {{ display:block; font-size:17px; color:#f8fafc; }}
    .muted {{ color:#94a3b8; }}
    .title {{ color:#f8fafc; font-size:15px; font-weight:700; margin-bottom:4px; }}
    .section-title {{ color:#cbd5e1; font-weight:700; margin-bottom:6px; }}
    .detail-scroll {{ min-height:0; height:100%; overflow-y:auto; padding-right:6px; }}
    .list-row {{ display:flex; justify-content:space-between; gap:12px; padding:5px 0; border-bottom:1px solid rgba(51,65,85,.45); }}
    .list-row:last-child {{ border-bottom:0; }}
    .pill {{ display:inline-block; margin:4px 4px 0 0; padding:2px 7px; border:1px solid #334155; border-radius:999px; color:#cbd5e1; font-size:11px; }}
    @media(max-width:900px) {{ .toolbar .hint {{ display:none; }} #legend {{ width:220px; }} }}
    @media(max-width:760px) {{
      #stage {{ height:430px; }} #detail {{ height:335px; overflow-y:auto; }}
      .detail-grid {{ grid-template-columns:1fr; height:auto; }} .summary-card {{ height:auto; }} .detail-scroll {{ height:auto; overflow:visible; }}
      #info-panel {{ width:250px; }} #legend {{ width:190px; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar">
    <select id="employee-search"><option value="">Cari / fokus karyawan…</option></select>
    <button id="fit">Fit Graph</button>
    <button id="isolate">Hide Isolated</button>
    <button id="reset">Reset View</button>
    <span class="hint">hover quick info · click focus · drag · scroll zoom</span>
  </div>
  <div id="stage">
    <div id="sigma-container"></div>
    <div id="info-panel"></div>
    <div id="legend"></div>
  </div>
  <div id="detail"><span class="muted">Klik node untuk Focus Mode. Hover node/garis untuk quick insight tanpa menutupi network.</span></div>

  <script type="module">
    import Graph from "https://cdn.jsdelivr.net/npm/graphology@0.26.0/+esm";
    import Sigma from "https://cdn.jsdelivr.net/npm/sigma@3/+esm";

    const data = {payload};
    const graph = new Graph({{type: "undirected", multi: false}});
    data.nodes.forEach(n => graph.addNode(n.id, n));
    data.edges.forEach(e => graph.addEdgeWithKey(e.id, e.source, e.target, e));

    const container = document.getElementById("sigma-container");
    const detail = document.getElementById("detail");
    const infoPanel = document.getElementById("info-panel");
    const legend = document.getElementById("legend");
    const search = document.getElementById("employee-search");
    const fitButton = document.getElementById("fit");
    const isolateButton = document.getElementById("isolate");
    const resetButton = document.getElementById("reset");

    const scale = data.collaboration_scale || {{min:0, max:0, low_color:"#475569", high_color:"#fb923c"}};
    const lowLabel = `${{scale.min}} task`;
    const highLabel = `${{scale.max}} task`;
    legend.innerHTML = `<div class="legend-title">Frekuensi kolaborasi</div>` +
      `<div class="legend-subtitle">Warna & ketebalan garis = jumlah task bersama antar-karyawan</div>` +
      `<div class="scale-bar" style="background:linear-gradient(90deg,${{scale.low_color}},${{scale.high_color}})"></div>` +
      `<div class="scale-labels"><span>${{lowLabel}}</span><span>${{highLabel}}</span></div>` +
      `<div class="scale-hints"><span>Sedikit</span><span>Banyak</span></div>` +
      `<div class="legend-note">Warna node menunjukkan community/cluster kolaborasi.</div>`;

    data.nodes.slice().sort((a,b) => a.label.localeCompare(b.label)).forEach(n => {{
      const option = document.createElement("option");
      option.value = n.id;
      option.textContent = n.label;
      search.appendChild(option);
    }});

    let selectedNode = null;
    let hoveredNode = null;
    let draggedNode = null;
    let isDragging = false;
    let hideIsolated = false;
    let cameraRatio = 1;

    const renderer = new Sigma(graph, container, {{
      renderLabels: {label_setting},
      labelColor: {{attribute: "labelColor", color: "#e2e8f0"}},
      labelSize: 12,
      labelDensity: 0.55,
      labelGridCellSize: 86,
      defaultNodeColor: "#60a5fa",
      defaultEdgeColor: "#526175",
      enableEdgeEvents: true,
      minCameraRatio: 0.035,
      maxCameraRatio: 6,
      nodeReducer: (node, attrs) => {{
        const result = {{...attrs, color: attrs.base_color || attrs.color, labelColor: "#e2e8f0"}};
        if (hideIsolated && attrs.isolated) {{ result.hidden = true; return result; }}

        const focus = selectedNode || hoveredNode;
        const isNeighbor = focus && graph.areNeighbors(node, focus);
        const important = attrs.collaborator_count >= 5;
        const zoomAllowsLabel = cameraRatio < 0.7;
        if (!{label_setting} || (!focus && !important && !zoomAllowsLabel)) result.label = "";

        if (focus && node !== focus && !isNeighbor) {{
          result.color = "#172033";
          result.labelColor = "#42536a";
          result.size = Math.max(2.8, attrs.size * 0.62);
          result.zIndex = 0;
        }} else if (node === focus) {{
          result.color = "#fbbf24";
          result.labelColor = "#f8fafc";
          result.size = Math.max(5.5, Math.min(9.8, attrs.size * 0.88));
          result.forceLabel = true;
          result.zIndex = 4;
        }} else if (isNeighbor) {{
          result.color = attrs.base_color || "#93c5fd";
          result.size = Math.max(4.0, Math.min(8.5, attrs.size * 0.78));
          result.forceLabel = true;
          result.zIndex = 3;
        }}
        return result;
      }},
      edgeReducer: (edge, attrs) => {{
        const result = {{...attrs}};
        const focus = selectedNode || hoveredNode;
        if (focus) {{
          const ends = graph.extremities(edge);
          if (!ends.includes(focus)) {{
            result.color = "#131c2d";
            result.size = Math.max(0.22, attrs.size * 0.24);
          }} else {{
            result.color = attrs.color;
            result.size = Math.max(1.5, Math.min(5.5, attrs.size * 1.75));
            result.zIndex = 4;
          }}
        }}
        return result;
      }},
    }});

    renderer.getCamera().on("updated", state => {{
      cameraRatio = state.ratio;
      renderer.refresh();
    }});

    function topCollaboratorRows(items) {{
      if (!items || !items.length) return '<span class="muted">Belum ada collaborator.</span>';
      return items.slice(0,5).map(item => {{
        const match = String(item).match(/^(.*) \((\d+) task\)$/);
        if (!match) return `<div class="list-row"><span>${{item}}</span></div>`;
        return `<div class="list-row"><span>${{match[1]}}</span><b>${{match[2]}} task</b></div>`;
      }}).join("");
    }}

    function nodeDetail(node) {{
      const a = graph.getNodeAttributes(node);
      const tasks = (a.top_tasks || []).slice(0,5).map(x => `<span class="pill">${{x}}</span>`).join("");
      detail.innerHTML = `<div class="detail-grid"><div class="summary-card"><div class="title">${{a.label}}</div><div class="muted">Focus Mode</div><div class="summary-grid"><div class="metric"><b>${{a.collaborator_count}}</b><span class="muted">Collaborators</span></div><div class="metric"><b>${{a.collaborative_task_count}}</b><span class="muted">Shared tasks</span></div><div class="metric"><b>${{a.project_count}}</b><span class="muted">Projects</span></div><div class="metric"><b>${{Number(a.collaborative_hours).toFixed(2)}}</b><span class="muted">Collaborative hours</span></div></div></div><div class="detail-scroll"><div class="section-title">Top Collaborators</div>${{topCollaboratorRows(a.top_collaborators)}}<div class="section-title" style="margin-top:12px">Dominant Tasks</div>${{tasks || '<span class="muted">Belum ada task dominan.</span>'}}</div></div>`;
    }}

    function showNodeInfo(node) {{
      const a = graph.getNodeAttributes(node);
      infoPanel.style.display = "block";
      infoPanel.innerHTML = `<div class="title">${{a.label}}</div><b>${{a.collaborator_count}}</b> collaborator · <b>${{a.collaborative_task_count}}</b> shared task · <b>${{Number(a.collaborative_hours).toFixed(2)}}</b> jam<br><span class="muted">Top:</span> ${{(a.top_collaborators || []).slice(0,3).join(", ") || "-"}}<br><span class="muted">${{a.community ? `Community ${{a.community}}` : "Isolated"}}</span>`;
    }}

    function showEdgeInfo(edge) {{
      const a = graph.getEdgeAttributes(edge);
      infoPanel.style.display = "block";
      infoPanel.innerHTML = `<div class="title">${{a.source}} ↔ ${{a.target}}</div><b>Frekuensi kolaborasi: ${{a.collaboration_count}} task bersama</b><br><span class="muted">Total jam terkait:</span> ${{Number(a.related_hours).toFixed(2)}} jam<br><span class="muted">Task:</span> ${{(a.shared_tasks || []).join(", ") || "-"}}<br><span class="muted">Project:</span> ${{(a.projects || []).join(", ") || "-"}}`;
    }}

    function focusNode(node, navigate=false) {{
      selectedNode = node || null;
      if (!node) {{
        search.value = "";
        detail.innerHTML = '<span class="muted">Klik node untuk Focus Mode. Hover node/garis untuk quick insight tanpa menutupi network.</span>';
        renderer.refresh();
        return;
      }}
      search.value = node;
      nodeDetail(node);
      if (navigate) {{
        const attrs = graph.getNodeAttributes(node);
        renderer.getCamera().animate({{x: attrs.x, y: attrs.y, ratio: 0.48}}, {{duration: 420}});
      }}
      renderer.refresh();
    }}

    renderer.on("clickNode", ({{node}}) => focusNode(node, false));
    renderer.on("clickStage", () => focusNode(null));
    renderer.on("enterNode", ({{node}}) => {{ hoveredNode = node; showNodeInfo(node); renderer.refresh(); }});
    renderer.on("leaveNode", () => {{ hoveredNode = null; infoPanel.style.display = "none"; renderer.refresh(); }});
    renderer.on("enterEdge", ({{edge}}) => showEdgeInfo(edge));
    renderer.on("leaveEdge", () => {{ infoPanel.style.display = "none"; }});

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
    }});

    search.addEventListener("change", () => focusNode(search.value || null, true));
    fitButton.addEventListener("click", () => renderer.getCamera().animatedReset({{duration:420}}));
    isolateButton.addEventListener("click", () => {{
      hideIsolated = !hideIsolated;
      isolateButton.textContent = hideIsolated ? "Show Isolated" : "Hide Isolated";
      isolateButton.classList.toggle("active", hideIsolated);
      renderer.refresh();
    }});
    resetButton.addEventListener("click", () => {{
      focusNode(null);
      hideIsolated = false;
      isolateButton.textContent = "Hide Isolated";
      isolateButton.classList.remove("active");
      renderer.getCamera().animatedReset({{duration:420}});
      renderer.refresh();
    }});
  </script>
</body>
</html>
"""
