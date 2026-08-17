from src.graph.pinball_animation import inject_pinball_effect


def test_pinball_animation_uses_explicit_one_way_directional_signals() -> None:
    html = "<html><style></style><div id=\"sigma-container\"></div><script>const graph = {};</script></html>"
    rendered = inject_pinball_effect(
        html,
        [{"source": "Alice Example", "target": "Bob Builder", "count": 3}],
    )

    assert 'id="pinball-signal-layer"' in rendered
    assert '"source": "Alice Example"' in rendered
    assert '"target": "Bob Builder"' in rendered
    assert "MAX_ANIMATED_SIGNALS = 120" in rendered
    assert "const travel = cycle" in rendered
    assert "1 - Math.abs(1 - 2 * phase)" not in rendered
    assert "active ? 5.0 : 3.7 + edge.intensity * 0.5" in rendered
    assert "shadowBlur" not in rendered
    assert "createLinearGradient" not in rendered


def test_pinball_animation_pauses_and_guards_invalid_viewport_coordinates() -> None:
    html = "<style></style><div id=\"sigma-container\"></div><script></script>"
    rendered = inject_pinball_effect(html, [])

    assert "document.hidden || prefersReducedMotion" in rendered
    assert "requestAnimationFrame(drawPinball)" in rendered
    assert "Number.isFinite(point.x)" in rendered
    assert "Number.isFinite(point.y)" in rendered
    assert "console.warn" in rendered
    assert "pinballEdges.length" in rendered
