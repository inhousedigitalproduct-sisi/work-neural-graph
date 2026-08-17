from __future__ import annotations

PINBALL_STYLE = """
    #pinball-signal-layer {
      position:absolute;
      inset:0;
      width:100%;
      height:100%;
      z-index:6;
      pointer-events:none;
    }
"""

PINBALL_SCRIPT = r"""
    const pinballLayer = document.getElementById("pinball-signal-layer");
    const pinballStage = document.getElementById("stage");
    const pinballContext = pinballLayer ? pinballLayer.getContext("2d") : null;
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    const MAX_ANIMATED_EDGES = 120;
    let pinballDpr = 1;
    let lastPinballFrame = 0;

    function resizePinballLayer() {
      if (!pinballLayer || !pinballStage || !pinballContext) return;
      const rect = pinballStage.getBoundingClientRect();
      pinballDpr = Math.min(window.devicePixelRatio || 1, 1.25);
      const width = Math.max(1, Math.round(rect.width * pinballDpr));
      const height = Math.max(1, Math.round(rect.height * pinballDpr));
      if (pinballLayer.width !== width || pinballLayer.height !== height) {
        pinballLayer.width = width;
        pinballLayer.height = height;
        pinballLayer.style.width = `${rect.width}px`;
        pinballLayer.style.height = `${rect.height}px`;
      }
      pinballContext.setTransform(pinballDpr, 0, 0, pinballDpr, 0, 0);
    }

    function edgePhase(edgeKey) {
      let hash = 0;
      const text = String(edgeKey);
      for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
      return Math.abs(hash % 1000) / 1000;
    }

    function collaborationRatio(value) {
      const scale = data.collaboration_scale || {min: 0, max: 0};
      const low = Number(scale.min || 0);
      const high = Number(scale.max || 0);
      if (high <= low) return 0.55;
      return Math.max(0, Math.min(1, (Number(value || 0) - low) / (high - low)));
    }

    const pinballEdges = data.edges.map(edge => {
      const count = Number(edge.collaboration_count || edge.shared_task_count || 1);
      return {
        key: edge.id,
        source: edge.source,
        target: edge.target,
        color: edge.color || "#f8fafc",
        count,
        intensity: collaborationRatio(count),
        phase: edgePhase(edge.id),
      };
    }).sort((a, b) => b.count - a.count).slice(0, MAX_ANIMATED_EDGES);

    const frameInterval = pinballEdges.length > 90 ? 66 : pinballEdges.length > 45 ? 50 : 40;

    function drawPinball(now) {
      if (!pinballContext || !pinballLayer || !pinballStage) return;
      window.requestAnimationFrame(drawPinball);
      if (document.hidden || prefersReducedMotion) return;
      if (now - lastPinballFrame < frameInterval) return;
      lastPinballFrame = now;
      resizePinballLayer();

      const rect = pinballStage.getBoundingClientRect();
      pinballContext.clearRect(0, 0, rect.width, rect.height);
      const focusNode = selectedNode || hoveredNode;
      const hasFocus = Boolean(focusNode && graph.hasNode(focusNode));

      const pointCache = new Map();
      const viewportPoint = nodeId => {
        if (pointCache.has(nodeId)) return pointCache.get(nodeId);
        const attrs = graph.getNodeAttributes(nodeId);
        const point = renderer.graphToViewport({x: attrs.x, y: attrs.y});
        pointCache.set(nodeId, point);
        return point;
      };

      pinballEdges.forEach(edge => {
        const sourcePoint = viewportPoint(edge.source);
        const targetPoint = viewportPoint(edge.target);
        const active = hasFocus && (edge.source === focusNode || edge.target === focusNode);
        const speed = active ? 0.00034 + edge.intensity * 0.00012 : 0.00022 + edge.intensity * 0.00008;
        const phase = (now * speed + edge.phase) % 1;
        const travel = 1 - Math.abs(1 - 2 * phase);
        const x = sourcePoint.x + (targetPoint.x - sourcePoint.x) * travel;
        const y = sourcePoint.y + (targetPoint.y - sourcePoint.y) * travel;
        const radius = active ? 3.0 : 2.0 + edge.intensity * 0.55;

        pinballContext.beginPath();
        pinballContext.arc(x, y, radius, 0, Math.PI * 2);
        pinballContext.fillStyle = active ? "rgba(255,255,255,0.98)" : "rgba(248,250,252,0.82)";
        pinballContext.fill();

        if (active) {
          pinballContext.beginPath();
          pinballContext.arc(x, y, radius + 1.5, 0, Math.PI * 2);
          pinballContext.strokeStyle = edge.color;
          pinballContext.globalAlpha = 0.55;
          pinballContext.lineWidth = 1;
          pinballContext.stroke();
          pinballContext.globalAlpha = 1;
        }
      });
    }

    if (pinballLayer && pinballStage && pinballContext && !prefersReducedMotion) {
      resizePinballLayer();
      new ResizeObserver(resizePinballLayer).observe(pinballStage);
      window.requestAnimationFrame(drawPinball);
    }
"""


def inject_pinball_effect(html: str) -> str:
    """Inject a bounded, lightweight bidirectional collaboration-dot overlay."""
    html = html.replace("</style>", f"{PINBALL_STYLE}\n  </style>", 1)
    html = html.replace(
        '<div id="sigma-container"></div>',
        '<div id="sigma-container"></div>\n    <canvas id="pinball-signal-layer" aria-hidden="true"></canvas>',
        1,
    )
    script_close = html.rfind("</script>")
    if script_close >= 0:
        html = html[:script_close] + PINBALL_SCRIPT + "\n  " + html[script_close:]
    return html
