from src.graph.pinball_animation import inject_pinball_effect


def test_pinball_animation_is_bounded_and_bidirectional() -> None:
    html = "<html><style></style><div id=\"sigma-container\"></div><script>const graph = {};</script></html>"
    rendered = inject_pinball_effect(html)

    assert 'id="pinball-signal-layer"' in rendered
    assert "MAX_ANIMATED_EDGES = 120" in rendered
    assert "1 - Math.abs(1 - 2 * phase)" in rendered
    assert "shadowBlur" not in rendered
    assert "createLinearGradient" not in rendered


def test_pinball_animation_pauses_when_hidden_or_reduced_motion() -> None:
    html = "<style></style><div id=\"sigma-container\"></div><script></script>"
    rendered = inject_pinball_effect(html)

    assert "document.hidden || prefersReducedMotion" in rendered
    assert "requestAnimationFrame(drawPinball)" in rendered
