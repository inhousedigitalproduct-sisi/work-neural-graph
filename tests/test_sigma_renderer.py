from pathlib import Path
import warnings

import networkx as nx
import pandas as pd

from src.graph.sigma_renderer import _sqrt_scaled, build_sigma_html


def _sample_graph() -> tuple[nx.Graph, pd.DataFrame, pd.DataFrame]:
    graph = nx.Graph()
    graph.add_edge("Alice", "Bob", shared_task_count=5)
    graph.add_edge("Bob", "Carol", shared_task_count=2)

    nodes = pd.DataFrame(
        [
            {"employee": "Alice", "collaborator_count": 1, "collaborative_task_count": 5, "collaborative_hours": 8.0, "project_count": 1, "collaborators": ["Bob"], "top_collaborators": ["Bob (5 evidence)"], "top_tasks": ["T-1"]},
            {"employee": "Bob", "collaborator_count": 2, "collaborative_task_count": 7, "collaborative_hours": 12.0, "project_count": 1, "collaborators": ["Alice", "Carol"], "top_collaborators": ["Alice (5 evidence)", "Carol (2 evidence)"], "top_tasks": ["T-1", "T-2"]},
            {"employee": "Carol", "collaborator_count": 1, "collaborative_task_count": 2, "collaborative_hours": 4.0, "project_count": 1, "collaborators": ["Bob"], "top_collaborators": ["Bob (2 evidence)"], "top_tasks": ["T-2"]},
        ]
    )
    edges = pd.DataFrame(
        [
            {"source": "Alice", "target": "Bob", "shared_task_count": 5, "a_to_b_count": 3, "b_to_a_count": 2, "shared_tasks": ["T-1"], "projects": ["Alpha"], "related_hours": 8.0},
            {"source": "Bob", "target": "Carol", "shared_task_count": 2, "a_to_b_count": 2, "b_to_a_count": 0, "shared_tasks": ["T-2"], "projects": ["Alpha"], "related_hours": 4.0},
        ]
    )
    return graph, nodes, edges


def _render() -> str:
    graph, nodes, edges = _sample_graph()
    return build_sigma_html(
        graph,
        nodes,
        edges,
        node_size_metric="collaborator_count",
        edge_width_metric="shared_task_count",
        show_labels=True,
    )


def test_node_scale_stays_compact() -> None:
    scaled = _sqrt_scaled(pd.Series([1, 4, 16]))
    assert min(scaled.values()) >= 2.2
    assert max(scaled.values()) <= 5.8


def test_renderer_uses_streamlit_safe_pixijs_and_d3_force() -> None:
    rendered = _render()
    assert "pixi.js@7.4.3" in rendered
    assert "d3@7" in rendered
    assert "new PIXI.Application" in rendered
    assert "d3.forceSimulation(data.nodes)" in rendered
    assert "d3.forceLink(data.edges)" in rendered
    assert "d3.forceManyBody()" in rendered
    assert "d3.forceCenter(0,0)" in rendered
    assert "d3.forceCollide()" in rendered
    assert ".velocityDecay(0.36)" in rendered
    assert "Sigma" not in rendered
    assert "spring_layout" not in rendered


def test_renderer_supports_zoom_pan_drag_and_force_restart() -> None:
    rendered = _render()
    assert "requestAnimationFrame" in rendered
    assert "fitGraph(" in rendered
    assert "addEventListener('wheel'" in rendered
    assert "Math.exp(-e.deltaY*.0013)" in rendered
    assert "world.toLocal(e.global)" in rendered
    assert "simulation.alphaTarget(0.18).restart()" in rendered
    assert "simulation.alphaTarget(0).alpha(.32).restart()" in rendered


def test_renderer_has_visible_error_diagnostics() -> None:
    rendered = _render()
    assert "Graph renderer error:" in rendered
    assert "PixiJS gagal dimuat dari CDN" in rendered
    assert "d3-force gagal dimuat dari CDN" in rendered


def test_employee_search_uses_case_insensitive_contains_matching() -> None:
    rendered = _render()
    assert '<input id="search" type="search"' in rendered
    assert "toLocaleLowerCase" in rendered
    assert ".includes(q)" in rendered


def test_renderer_has_force_settle_without_idle_wobble() -> None:
    rendered = _render()
    assert ".alphaDecay(0.022)" in rendered
    assert ".alphaMin(0.002)" in rendered
    assert "Graph settled" in rendered
    assert "const MOTION_FPS" not in rendered
    assert "runIdleMotion" not in rendered


def test_sigma_renderer_source_compiles_without_escape_warnings() -> None:
    source_path = Path("src/graph/sigma_renderer.py")
    source = source_path.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        compile(source, str(source_path), "exec")
