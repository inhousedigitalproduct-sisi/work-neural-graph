from __future__ import annotations

import json
from typing import Any

import networkx as nx
import pandas as pd


def _scaled(values: pd.Series, minimum: float, maximum: float) -> dict[str, float]:
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


def build_sigma_html(
    graph: nx.Graph,
    node_dataframe: pd.DataFrame,
    edge_dataframe: pd.DataFrame,
    *,
    node_size_metric: str,
    edge_width_metric: str,
    show_labels: bool,
) -> str:
    """Build a self-contained Sigma.js view for Streamlit's HTML component."""
    if node_dataframe.empty:
        return "<div style='padding:24px;color:#94a3b8'>Tidak ada node untuk ditampilkan.</div>"

    positions = nx.spring_layout(graph, seed=42, weight="shared_task_count", k=None)
    node_sizes = _scaled(node_dataframe[node_size_metric], 7.0, 20.0)
    edge_sizes = _scaled(edge_dataframe[edge_width_metric], 1.0, 6.0) if not edge_dataframe.empty else {}

    nodes: list[dict[str, Any]] = []
    for index, row in node_dataframe.reset_index(drop=True).iterrows():
        employee = str(row["employee"])
        x, y = positions.get(employee, (0.0, 0.0))
        nodes.append(
            {
                "id": employee,
                "label": employee,
                "x": float(x),
                "y": float(y),
                "size": float(node_sizes.get(str(index), 10.0)),
                "color": "#60a5fa",
                "collaborator_count": int(row.get("collaborator_count", 0)),
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
        edges.append(
            {
                "id": f"edge-{index}",
                "source": str(row["source"]),
                "target": str(row["target"]),
                "size": float(edge_sizes.get(str(index), 1.5)),
                "color": "#475569",
                "shared_task_count": int(row.get("shared_task_count", 0)),
                "shared_tasks": list(row.get("shared_tasks", []) or []),
                "projects": list(row.get("projects", []) or []),
                "related_hours": float(row.get("related_hours", 0.0)),
            }
        )

    payload = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False).replace("</", "<\\/")
    label_setting = "true" if show_labels else "false"

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin:0; padding:0; background:#020617; color:#e2e8f0; font-family:Inter,system-ui,-apple-system,sans-serif; }}
    .toolbar {{ height:54px; display:flex; align-items:center; gap:10px; padding:0 12px; border:1px solid #1e293b; border-bottom:0; border-radius:12px 12px 0 0; background:#0f172a; }}
    .toolbar select, .toolbar button {{ height:34px; border-radius:8px; border:1px solid #334155; background:#111827; color:#e2e8f0; padding:0 10px; }}
    .toolbar select {{ min-width:260px; flex:1; }}
    .toolbar button {{ cursor:pointer; }}
    .toolbar .hint {{ color:#64748b; font-size:12px; white-space:nowrap; }}
    #stage {{ height:570px; position:relative; border:1px solid #1e293b; background:radial-gradient(circle at center,#0f172a 0,#020617 72%); }}
    #sigma-container {{ position:absolute; inset:0; }}
    #tooltip {{ position:absolute; display:none; z-index:8; max-width:340px; pointer-events:none; padding:10px 12px; border:1px solid #334155; border-radius:9px; background:rgba(15,23,42,.97); color:#e2e8f0; font-size:12px; line-height:1.45; box-shadow:0 10px 35px rgba(0,0,0,.35); }}
    #detail {{ min-height:96px; padding:14px; border:1px solid #1e293b; border-top:0; border-radius:0 0 12px 12px; background:#0f172a; font-size:13px; line-height:1.5; }}
    .detail-grid {{ display:grid; grid-template-columns:minmax(220px,.8fr) minmax(320px,1.2fr); gap:18px; }}
    .summary-card {{ border:1px solid #243244; border-radius:10px; padding:12px; background:#111827; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:10px; }}
    .metric {{ border:1px solid #253247; border-radius:8px; padding:8px; background:#0b1220; }}
    .metric b {{ display:block; font-size:17px; color:#f8fafc; }}
    .muted {{ color:#94a3b8; }}
    .title {{ color:#f8fafc; font-size:15px; font-weight:700; margin-bottom:4px; }}
    .section-title {{ color:#cbd5e1; font-weight:700; margin-bottom:6px; }}
    .list-row {{ display:flex; justify-content:space-between; gap:12px; padding:5px 0; border-bottom:1px solid rgba(51,65,85,.45); }}
    .list-row:last-child {{ border-bottom:0; }}
    .pill {{ display:inline-block; margin:4px 4px 0 0; padding:2px 7px; border:1px solid #334155; border-radius:999px; color:#cbd5e1; font-size:11px; }}
    @media(max-width:760px) {{ .detail-grid {{ grid-template-columns:1fr; }} .toolbar .hint {{ display:none; }} }}
  </style>
</head>
<body>
  <div class="toolbar">
    <select id="employee-search"><option value="">Cari / fokus karyawan…</option></select>
    <button id="reset">Reset View</button>
    <span class="hint">Drag node · scroll zoom · hover info · click detail</span>
  </div>
  <div id="stage">
    <div id="sigma-container"></div>
    <div id="tooltip"></div>
  </div>
  <div id="detail"><span class="muted">Klik node untuk melihat detail kolaborasi. Hover node untuk quick insight dan hover garis untuk detail relasi.</span></div>

  <script type="module">
    import Graph from "https://cdn.jsdelivr.net/npm/graphology@0.26.0/+esm";
    import Sigma from "https://cdn.jsdelivr.net/npm/sigma@3/+esm";

    const data = {payload};
    const graph = new Graph({{type: "undirected", multi: false}});
    data.nodes.forEach(n => graph.addNode(n.id, n));
    data.edges.forEach(e => graph.addEdgeWithKey(e.id, e.source, e.target, e));

    const container = document.getElementById("sigma-container");
    const detail = document.getElementById("detail");
    const tooltip = document.getElementById("tooltip");
    const search = document.getElementById("employee-search");
    const resetButton = document.getElementById("reset");

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

    const renderer = new Sigma(graph, container, {{
      renderLabels: {label_setting},
      labelColor: {{attribute: "labelColor", color: "#e2e8f0"}},
      labelSize: 12,
      defaultNodeColor: "#60a5fa",
      defaultEdgeColor: "#475569",
      enableEdgeEvents: true,
      nodeReducer: (node, attrs) => {{
        const result = {{...attrs, labelColor: "#e2e8f0"}};
        const focus = selectedNode || hoveredNode;
        if (focus && node !== focus && !graph.areNeighbors(node, focus)) {{
          result.color = "#1e293b";
          result.labelColor = "#64748b";
          result.zIndex = 0;
        }} else if (node === focus) {{
          result.color = "#fbbf24";
          result.labelColor = "#0f172a";
          result.size = attrs.size * 1.25;
          result.zIndex = 2;
        }} else if (focus) {{
          result.color = "#93c5fd";
          result.labelColor = "#e2e8f0";
          result.zIndex = 1;
        }}
        return result;
      }},
      edgeReducer: (edge, attrs) => {{
        const result = {{...attrs}};
        const focus = selectedNode || hoveredNode;
        if (focus) {{
          const ends = graph.extremities(edge);
          if (!ends.includes(focus)) {{
            result.color = "#1f2937";
            result.size = Math.max(0.4, attrs.size * 0.4);
          }} else {{
            result.color = "#94a3b8";
            result.size = attrs.size * 1.2;
          }}
        }}
        return result;
      }},
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
      detail.innerHTML = `
        <div class="detail-grid">
          <div class="summary-card">
            <div class="title">${{a.label}}</div>
            <div class="muted">Selected employee</div>
            <div class="summary-grid">
              <div class="metric"><b>${{a.collaborator_count}}</b><span class="muted">Collaborators</span></div>
              <div class="metric"><b>${{a.collaborative_task_count}}</b><span class="muted">Shared tasks</span></div>
              <div class="metric"><b>${{a.project_count}}</b><span class="muted">Projects</span></div>
              <div class="metric"><b>${{Number(a.collaborative_hours).toFixed(2)}}</b><span class="muted">Collaborative hours</span></div>
            </div>
          </div>
          <div>
            <div class="section-title">Top Collaborators</div>
            ${{topCollaboratorRows(a.top_collaborators)}}
            <div class="section-title" style="margin-top:12px">Dominant Tasks</div>
            ${{tasks || '<span class="muted">Belum ada task dominan.</span>'}}
          </div>
        </div>`;
    }}

    function showNodeTooltip(node, event) {{
      const a = graph.getNodeAttributes(node);
      tooltip.style.display = "block";
      tooltip.innerHTML = `<b>${{a.label}}</b><br>` +
        `${{a.collaborator_count}} collaborator · ${{a.collaborative_task_count}} shared task · ` +
        `${{Number(a.collaborative_hours).toFixed(2)}} jam kolaboratif<br>` +
        `<span class="muted">Top collaborator:</span> ${{(a.top_collaborators || []).slice(0,3).join(", ") || "-"}}`;
      tooltip.style.left = `${{Math.min(event.x + 14, container.clientWidth - 355)}}px`;
      tooltip.style.top = `${{Math.max(event.y - 10, 10)}}px`;
    }}

    function focusNode(node, navigate=false) {{
      selectedNode = node || null;
      if (!node) {{
        search.value = "";
        detail.innerHTML = '<span class="muted">Klik node untuk melihat detail kolaborasi. Hover node untuk quick insight dan hover garis untuk detail relasi.</span>';
        renderer.refresh();
        return;
      }}
      search.value = node;
      nodeDetail(node);
      if (navigate) {{
        const attrs = graph.getNodeAttributes(node);
        renderer.getCamera().animate({{x: attrs.x, y: attrs.y, ratio: 0.7}}, {{duration: 450}});
      }}
      renderer.refresh();
    }}

    renderer.on("clickNode", ({{node}}) => focusNode(node, false));
    renderer.on("clickStage", () => focusNode(null));
    renderer.on("enterNode", ({{node, event}}) => {{ hoveredNode = node; showNodeTooltip(node, event); renderer.refresh(); }});
    renderer.on("leaveNode", () => {{ hoveredNode = null; tooltip.style.display = "none"; renderer.refresh(); }});

    renderer.on("enterEdge", ({{edge, event}}) => {{
      const a = graph.getEdgeAttributes(edge);
      tooltip.style.display = "block";
      tooltip.innerHTML = `<b>${{a.source}} ↔ ${{a.target}}</b><br>` +
        `${{a.shared_task_count}} task bersama · ${{Number(a.related_hours).toFixed(2)}} jam terkait<br>` +
        `<span class="muted">Task:</span> ${{(a.shared_tasks || []).join(", ") || "-"}}<br>` +
        `<span class="muted">Project:</span> ${{(a.projects || []).join(", ") || "-"}}`;
      tooltip.style.left = `${{Math.min(event.x + 14, container.clientWidth - 355)}}px`;
      tooltip.style.top = `${{Math.max(event.y - 10, 10)}}px`;
    }});
    renderer.on("leaveEdge", () => {{ tooltip.style.display = "none"; }});

    renderer.on("downNode", ({{node}}) => {{
      isDragging = true;
      draggedNode = node;
      graph.setNodeAttribute(node, "highlighted", true);
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
      if (draggedNode) graph.removeNodeAttribute(draggedNode, "highlighted");
      isDragging = false;
      draggedNode = null;
      renderer.getCamera().enable();
    }});
    renderer.getMouseCaptor().on("mousedown", () => {{
      if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
    }});

    search.addEventListener("change", () => focusNode(search.value || null, true));
    resetButton.addEventListener("click", () => {{
      focusNode(null);
      renderer.getCamera().animatedReset({{duration: 450}});
    }});
  </script>
</body>
</html>
"""
