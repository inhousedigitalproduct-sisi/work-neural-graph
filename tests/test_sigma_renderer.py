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


def test_node_scale_stays_compact() -> None:
    scaled = _sqrt_scaled(pd.Series([1, 4, 16]))

    assert min(scaled.values()) >= 2.2
    assert max(scaled.values()) <= 5.8


def test_sigma_renderer_supports_deep_zoom_note_evidence_and_display_coordinate_focus() -> None:
    graph, nodes, edges = _sample_graph()

    rendered = build_sigma_html(
        graph,
        nodes,
        edges,
        node_size_metric="collaborator_count",
        edge_width_metric="shared_task_count",
        show_labels=True,
    )

    assert "minCameraRatio: 0.004" in rendered
    assert "maxCameraRatio: 10" in rendered
    assert "Evidence kolaborasi (Note)" in rendered
    assert "renderer.getNodeDisplayData(node)" in rendered
    assert "ratio: 0.28" in rendered
    assert "const attrs = graph.getNodeAttributes(node);\n        renderer.getCamera().animate" not in rendered
    assert "Math.min(6.2, attrs.size * 1.05)" in rendered
    assert "Math.min(3.8, attrs.size * 1.15)" in rendered
    assert "requestAnimationFrame" not in rendered


def test_employee_search_uses_case_insensitive_contains_matching() -> None:
    graph, nodes, edges = _sample_graph()

    rendered = build_sigma_html(
        graph,
        nodes,
        edges,
        node_size_metric="collaborator_count",
        edge_width_metric="shared_task_count",
        show_labels=True,
    )

    assert '<input id="employee-search" type="search"' in rendered
    assert "employee-search-results" in rendered
    assert "n.searchLabel.includes(normalized)" in rendered
    assert "search.addEventListener(\"input\"" in rendered
    assert "chooseEmployee(first)" in rendered
    assert '<select id="employee-search">' not in rendered


def test_sigma_renderer_source_compiles_without_escape_warnings() -> None:
    source_path = Path("src/graph/sigma_renderer.py")
    source = source_path.read_text(encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        compile(source, str(source_path), "exec")
