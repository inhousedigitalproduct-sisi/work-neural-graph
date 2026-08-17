from src.graph.pinball_animation import inject_pinball_effect


def test_pinball_animation_uses_explicit_one_way_directional_chevrons() -> None:
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
    assert "drawDirectionalChevron" in rendered
    assert "Math.atan2(dy, dx)" in rendered
    assert "context.rotate(angle)" in rendered
    assert "context.moveTo(size, 0)" in rendered
    assert "context.arc(" not in rendered
    assert "shadowBlur" not in rendered
    assert "createLinearGradient" not in rendered


def test_pinball_animation_dims_unfocused_markers_and_highlights_active_path() -> None:
    html = "<style></style><div id=\"sigma-container\"></div><script></script>"
    rendered = inject_pinball_effect(
        html,
        [{"source": "Alice Example", "target": "Bob Builder", "count": 1}],
    )

    assert "const hasFocus = Boolean(focusNode && graph.hasNode(focusNode))" in rendered
    assert "const active = hasFocus && (edge.source === focusNode || edge.target === focusNode)" in rendered
    assert "hasFocus ? (active ? 1.0 : 0.16) : 0.92" in rendered
    assert "active ? 8.8 : 6.6 + edge.intensity * 1.0" in rendered


def test_pinball_animation_pauses_and_guards_invalid_viewport_coordinates() -> None:
    html = "<style></style><div id=\"sigma-container\"></div><script></script>"
    rendered = inject_pinball_effect(html, [])

    assert "document.hidden || prefersReducedMotion" in rendered
    assert "requestAnimationFrame(drawPinball)" in rendered
    assert "Number.isFinite(point.x)" in rendered
    assert "Number.isFinite(point.y)" in rendered
    assert "console.warn" in rendered
    assert "pinballEdges.length" in rendered
