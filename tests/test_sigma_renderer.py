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
            {
                "employee": "Alice",
                "collaborator_count": 1,
                "collaborative_task_count": 5,
                "collaborative_hours": 8.0,
                "project_count": 1,
                "collaborators": ["Bob"],
                "top_collaborators": ["Bob (5 evidence)"],
                "top_tasks": ["T-1"],
            },
            {
                "employee": "Bob",
                "collaborator_count": 2,
                "collaborative_task_count": 7,
                "collaborative_hours": 12.0,
                "project_count": 1,
                "collaborators": ["Alice", "Carol"],
                "top_collaborators": ["Alice (5 evidence)", "Carol (2 evidence)"],
                "top_tasks": ["T-1", "T-2"],
            },
            {
                "employee": "Carol",
                "collaborator_count": 1,
                "collaborative_task_count": 2,
                "collaborative_hours": 4.0,
                "project_count": 1,
                "collaborators": ["Bob"],
                "top_collaborators": ["Bob (2 evidence)"],
                "top_tasks": ["T-2"],
            },
        ]
    )
    edges = pd.DataFrame(
        [
            {
                "source": "Alice",
                "target": "Bob",
                "shared_task_count": 5,
                "a_to_b_count": 3,
                "b_to_a_count": 2,
                "shared_tasks": ["T-1"],
                "projects": ["Alpha"],
                "related_hours": 8.0,
            },
            {
                "source": "Bob",
                "target": "Carol",
                "shared_task_count": 2,
                "a_to_b_count": 2,
                "b_to_a_count": 0,
                "shared_tasks": ["T-2"],
                "projects": ["Alpha"],
                "related_hours": 4.0,
            },
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


def test_renderer_uses_pixijs_webgl_and_d3_force() -> None:
    rendered = _render()

    assert "pixi.js@8.13.2" in rendered
    assert "d3-force@3" in rendered
    assert 'preference: "webgl"' in rendered
    assert "new PIXI.Application()" in rendered
    assert "forceSimulation(data.nodes)" in rendered
    assert 'force("link", forceLink(data.edges)' in rendered
    assert 'force("charge", forceManyBody()' in rendered
    assert 'force("center", forceCenter(0, 0)' in rendered
    assert 'force("collide", forceCollide()' in rendered
    assert ".velocityDecay(0.38)" in rendered
    assert "Sigma" not in rendered
    assert "spring_layout" not in rendered


def test_renderer_supports_smooth_zoom_pan_focus_and_physics_restart() -> None:
    rendered = _render()

    assert "requestAnimationFrame" in rendered
    assert "animateWorld(" in rendered
    assert 'stageEl.addEventListener("wheel"' in rendered
    assert "Math.exp(-event.deltaY * 0.0013)" in rendered
    assert "world.toLocal(event.global)" in rendered
    assert "simulation.alphaTarget(0.16).restart()" in rendered
    assert "simulation.alphaTarget(0).alpha(0.34).restart()" in rendered
    assert "focusNode(n.id, true)" in rendered
    assert "Evidence kolaborasi (Note)" in rendered


def test_employee_search_uses_case_insensitive_contains_matching() -> None:
    rendered = _render()

    assert '<input id="employee-search" type="search"' in rendered
    assert "employee-search-results" in rendered
    assert "n.searchLabel.includes(normalized)" in rendered
    assert 'search.addEventListener("input"' in rendered
    assert "focusNode(n.id, true)" in rendered
    assert '<select id="employee-search">' not in rendered


def test_renderer_has_force_settle_without_idle_wobble() -> None:
    rendered = _render()

    assert ".alphaDecay(0.021)" in rendered
    assert ".alphaMin(0.002)" in rendered
    assert 'simulation.on("tick.fit"' in rendered
    assert "const MOTION_FPS" not in rendered
    assert "runIdleMotion" not in rendered
    assert "MOTION_INTERVAL_MS" not in rendered
    assert "Math.sin(time *" not in rendered
    assert "Math.cos(time *" not in rendered


def test_sigma_renderer_source_compiles_without_escape_warnings() -> None:
    source_path = Path("src/graph/sigma_renderer.py")
    source = source_path.read_text(encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        compile(source, str(source_path), "exec")
