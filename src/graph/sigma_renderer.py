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


def _linear_scaled(values: pd.Series, minimum: float = 0.75, maximum: float = 3.2) -> dict[str, float]:
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
    """Build a lightweight Sigma.js collaboration explorer."""
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#94a3b8'>Tidak ada node untuk ditampilkan.</div>"

    n_nodes = max(graph.number_of_nodes(), 1)
    k = max(0.28, min(0.95, 3.0 / math.sqrt(n_nodes)))
    positions = nx.spring_layout(
        graph,
        seed=42,
        weight="shared_task_count",
        k=k,
        iterations=220,
        scale=1.55,
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
                "size": float(edge_sizes.get(str(index), 1.0)),
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
    html, body {{ margin:0; padding:0; background:#020617; color:#e2e8f0; font-family:Inter,system-ui,-apple-system,sans-serif; overflow:hidden; }}
    .toolbar {{ height:52px; display:flex; align-items:center; gap:8px; padding:0 10px; border:1px solid #1e293b; border-bottom:0; border-radius:10px 10px 0 0; background:#0f172a; box-sizing:border-box; }}
    .toolbar select, .toolbar button {{ height:32px; border-radius:7px; border:1px solid #334155; background:#111827; color:#e2e8f0; padding:0 9px; }}
    .toolbar select {{ min-width:240px; flex:1; }}
    .toolbar button {{ cursor:pointer; white-space:nowrap; }}
    .toolbar .hint {{ color:#64748b; font-size:10px; white-space:nowrap; }}
    #stage {{ height:560px; position:relative; border:1px solid #1e293b; background:#020617; box-sizing:border-box; }}
    #sigma-container {{ position:absolute; inset:0; }}
    #info-panel {{ position:absolute; display:none; z-index:9; right:12px; top:12px; width:310px; max-height:190px; overflow:auto; padding:10px 12px; border:1px solid #334155; border-radius:9px; background:rgba(15,23,42,.96); font-size:12px; line-height:1.45; }}
    #legend {{ position:absolute; left:12px; bottom:12px; z-index:7; width:238px; padding:10px 11px; border:1px solid rgba(71,85,105,.72); border-radius:11px; background:rgba(15,23,42,.92); }}
    .legend-title {{ color:#f8fafc; font-size:11px; font-weight:800; }}
    .legend-subtitle {{ color:#94a3b8; font-size:9px; margin-top:2px; line-height:1.3; }}
    .scale-bar {{ height:8px; border-radius:999px; margin:9px 0 5px; border:1px solid rgba(255,255,255,.12); }}
    .scale-labels {{ display:flex; justify-content:space-between; color:#cbd5e1; font-size:9px; font-weight:700; }}
    .legend-note {{ color:#64748b; font-size:9px; margin-top:7px; }}
    #detail {{ height:190px; padding:12px; border:1px solid #1e293b; border-top:0; border-radius:0 0 10px 10px; background:#0f172a; font-size:12px; line-height:1.45; box-sizing:border-box; overflow:hidden; }}
    .detail-grid {{ display:grid; grid-template-columns:minmax(210px,.8fr) minmax(300px,1.2fr); gap:14px; height:100%; }}
    .summary-card {{ border:1px solid #243244; border-radius:8px; padding:10px; background:#111827; height:100%; box-sizing:border-box; overflow:hidden; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:6px; margin-top:8px; }}
    .metric {{ border:1px solid #253247; border-radius:7px; padding:6px; background:#0b1220; }}
    .metric b {{ display:block; font-size:14px; color:#f8fafc; }}
    .muted {{ color:#94a3b8; }}
    .title {{ color:#f8fafc; font-size:14px; font-weight:700; margin-bottom:3px; }}
    .section-title {{ color:#cbd5e1; font-weight:700; margin-bottom:5px; }}
    .detail-scroll {{ min-height:0; height:100%; overflow-y:auto; padding-right:4px; }}
    .list-row {{ display:flex; justify-content:space-between; gap:10px; padding:4px 0; border-bottom:1px solid rgba(51,65,85,.4); }}
    .pill {{ display:inline-block; margin:3px 3px 0 0; padding:2px 6px; border:1px solid #334155; border-radius:999px; color:#cbd5e1; font-size:10px; }}
  </style>
</head>
<body>
  <div class="toolbar">
    <select id="employee-search"><option value="">Cari / fokus karyawan…</option></select>
    <button id="fit">Fit Graph</button>
    <button id="isolate">Hide Isolated</button>
    <button id="reset">Reset View</button>
    <span class="hint">hover · click focus · drag · scroll zoom</span>
  </div>
  <div id="stage">
    <div id="sigma-container"></div>
    <div id="info-panel"></div>
    <div id="legend"></div>
  </div>
  <div id="detail"><span class="muted">Klik node untuk melihat evidence relasi utama. Gunakan scroll untuk zoom jauh dan drag untuk eksplorasi.</span></div>

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
    legend.innerHTML = `<div class="legend-title">Evidence kolaborasi (Note)</div>` +
      `<div class="legend-subtitle">Warna & ketebalan garis = jumlah evidence penyebutan nama</div>` +
      `<div class="scale-bar" style="background:linear-gradient(90deg,${{scale.low_color}},${{scale.high_color}})"></div>` +
      `<div class="scale-labels"><span>${{scale.min}} evidence</span><span>${{scale.max}} evidence</span></div>` +
      `<div class="legend-note">Warna node = community/cluster evidence Note.</div>`;

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
      labelSize: 11,
      labelDensity: 0.46,
      labelGridCellSize: 72,
      defaultNodeColor: "#60a5fa",
      defaultEdgeColor: "#526175",
      enableEdgeEvents: true,
      minCameraRatio: 0.004,
      maxCameraRatio: 10,
      nodeReducer: (node, attrs) => {{
        const result = {{...attrs, color: attrs.base_color || attrs.color, labelColor: "#e2e8f0"}};
        if (hideIsolated && attrs.isolated) {{ result.hidden = true; return result; }}
        const focus = selectedNode || hoveredNode;
        const isNeighbor = focus && graph.areNeighbors(node, focus);
        const important = attrs.collaborator_count >= 5;
        const zoomAllowsLabel = cameraRatio < 0.55;
        if (!{label_setting} || (!focus && !important && !zoomAllowsLabel)) result.label = "";
        if (focus && node !== focus && !isNeighbor) {{
          result.color = "#1d293b";
          result.labelColor = "#475569";
          result.size = Math.max(1.7, attrs.size * 0.84);
          result.zIndex = 0;
        }} else if (node === focus) {{
          result.color = "#fbbf24";
          result.labelColor = "#f8fafc";
          result.size = Math.max(3.0, Math.min(6.2, attrs.size * 1.05));
          result.forceLabel = true;
          result.zIndex = 4;
        }} else if (isNeighbor) {{
          result.size = Math.max(2.4, Math.min(5.8, attrs.size));
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
            result.color = "#172033";
            result.size = Math.max(0.35, attrs.size * 0.45);
          }} else {{
            result.size = Math.max(1.0, Math.min(3.8, attrs.size * 1.15));
            result.zIndex = 4;
          }}
        }}
        return result;
      }},
    }});

    renderer.getCamera().on("updated", state => {{ cameraRatio = state.ratio; renderer.refresh(); }});

    function topCollaboratorRows(items) {{
      if (!items || !items.length) return '<span class="muted">Belum ada collaborator evidence.</span>';
      return items.slice(0,5).map(item => {{
        const match = String(item).match(/^(.*) [(]([0-9]+) (?:task|evidence)[)]$/);
        if (!match) return `<div class="list-row"><span>${{item}}</span></div>`;
        return `<div class="list-row"><span>${{match[1]}}</span><b>${{match[2]}} evidence</b></div>`;
      }}).join("");
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

    function focusNode(node, navigate=false) {{
      selectedNode = node || null;
      if (!node) {{
        search.value = "";
        detail.innerHTML = '<span class="muted">Klik node untuk melihat evidence relasi utama. Gunakan scroll untuk zoom jauh dan drag untuk eksplorasi.</span>';
        renderer.refresh();
        return;
      }}
      search.value = node;
      nodeDetail(node);
      if (navigate) {{
        // Sigma camera uses framed/display coordinates, not raw NetworkX graph coordinates.
        const position = renderer.getNodeDisplayData(node);
        if (position) {{
          renderer.getCamera().animate({{x: position.x, y: position.y, ratio: 0.28}}, {{duration: 360}});
        }}
      }}
      renderer.refresh();
    }}

    renderer.on("clickNode", ({{node}}) => focusNode(node, false));
    renderer.on("clickStage", () => focusNode(null));
    renderer.on("enterNode", ({{node}}) => {{ hoveredNode = node; showNodeInfo(node); renderer.refresh(); }});
    renderer.on("leaveNode", () => {{ hoveredNode = null; infoPanel.style.display = "none"; renderer.refresh(); }});
    renderer.on("enterEdge", ({{edge}}) => showEdgeInfo(edge));
    renderer.on("leaveEdge", () => {{ infoPanel.style.display = "none"; }});

    renderer.on("downNode", ({{node}}) => {{ isDragging = true; draggedNode = node; renderer.getCamera().disable(); }});
    renderer.getMouseCaptor().on("mousemovebody", event => {{
      if (!isDragging || !draggedNode) return;
      const pos = renderer.viewportToGraph(event);
      graph.setNodeAttribute(draggedNode, "x", pos.x);
      graph.setNodeAttribute(draggedNode, "y", pos.y);
      event.preventSigmaDefault?.();
      event.original?.preventDefault?.();
      event.original?.stopPropagation?.();
    }});
    renderer.getMouseCaptor().on("mouseup", () => {{ isDragging = false; draggedNode = null; renderer.getCamera().enable(); }});

    search.addEventListener("change", () => focusNode(search.value || null, true));
    fitButton.addEventListener("click", () => renderer.getCamera().animatedReset({{duration:360}}));
    isolateButton.addEventListener("click", () => {{
      hideIsolated = !hideIsolated;
      isolateButton.textContent = hideIsolated ? "Show Isolated" : "Hide Isolated";
      renderer.refresh();
    }});
    resetButton.addEventListener("click", () => {{
      focusNode(null);
      hideIsolated = false;
      isolateButton.textContent = "Hide Isolated";
      renderer.getCamera().animatedReset({{duration:360}});
      renderer.refresh();
    }});
  </script>
</body>
</html>
"""
