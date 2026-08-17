from src.graph.pinball_animation import inject_pinball_effect


def test_pinball_animation_is_bounded_bidirectional_and_visible() -> None:
    html = "<html><style></style><div id=\"sigma-container\"></div><script>const graph = {};</script></html>"
    rendered = inject_pinball_effect(html)

    assert 'id="pinball-signal-layer"' in rendered
    assert "MAX_ANIMATED_EDGES = 120" in rendered
    assert "1 - Math.abs(1 - 2 * phase)" in rendered
    assert "active ? 5.0 : 3.7 + edge.intensity * 0.5" in rendered
    assert 'rgba(255,255,255,0.96)' in rendered
    assert "rgbaFromHex(edge.color" in rendered
    assert "shadowBlur" not in rendered
    assert "createLinearGradient" not in rendered


def test_pinball_animation_pauses_and_guards_invalid_viewport_coordinates() -> None:
    html = "<style></style><div id=\"sigma-container\"></div><script></script>"
    rendered = inject_pinball_effect(html)

    assert "document.hidden || prefersReducedMotion" in rendered
    assert "requestAnimationFrame(drawPinball)" in rendered
    assert "Number.isFinite(point.x)" in rendered
    assert "Number.isFinite(point.y)" in rendered
    assert "console.warn" in rendered
