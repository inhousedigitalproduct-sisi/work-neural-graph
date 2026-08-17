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
    let pinballRuntimeWarned = false;

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

    function rgbaFromHex(hex, alpha) {
      const normalized = String(hex || "#94a3b8").replace("#", "");
      if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return `rgba(148,163,184,${alpha})`;
      const value = parseInt(normalized, 16);
      const r = (value >> 16) & 255;
      const g = (value >> 8) & 255;
      const b = value & 255;
      return `rgba(${r},${g},${b},${alpha})`;
    }

    const pinballEdges = data.edges.map(edge => {
      const count = Number(edge.collaboration_count || edge.shared_task_count || 1);
      return {
        key: edge.id,
        source: edge.source,
        target: edge.target,
        color: edge.color || "#94a3b8",
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
        try {
          const attrs = graph.getNodeAttributes(nodeId);
          const point = renderer.graphToViewport({x: attrs.x, y: attrs.y});
          if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
          pointCache.set(nodeId, point);
          return point;
        } catch (error) {
          if (!pinballRuntimeWarned) {
            console.warn("Pinball animation disabled for an invalid Sigma viewport coordinate.", error);
            pinballRuntimeWarned = true;
          }
          return null;
        }
      };

      pinballEdges.forEach(edge => {
        const sourcePoint = viewportPoint(edge.source);
        const targetPoint = viewportPoint(edge.target);
        if (!sourcePoint || !targetPoint) return;

        const active = hasFocus && (edge.source === focusNode || edge.target === focusNode);
        const speed = active ? 0.00034 + edge.intensity * 0.00012 : 0.00022 + edge.intensity * 0.00008;
        const phase = (now * speed + edge.phase) % 1;
        const travel = 1 - Math.abs(1 - 2 * phase);
        const x = sourcePoint.x + (targetPoint.x - sourcePoint.x) * travel;
        const y = sourcePoint.y + (targetPoint.y - sourcePoint.y) * travel;
        const radius = active ? 5.0 : 3.7 + edge.intensity * 0.5;

        // High-contrast white core keeps the dot visible on the dark graph without expensive glow/shadow effects.
        pinballContext.beginPath();
        pinballContext.arc(x, y, radius, 0, Math.PI * 2);
        pinballContext.fillStyle = active ? "rgba(255,255,255,1)" : "rgba(255,255,255,0.96)";
        pinballContext.fill();

        // Thin edge-colored outline preserves collaboration-frequency color context at negligible cost.
        pinballContext.beginPath();
        pinballContext.arc(x, y, radius + (active ? 1.4 : 0.9), 0, Math.PI * 2);
        pinballContext.strokeStyle = rgbaFromHex(edge.color, active ? 0.95 : 0.82);
        pinballContext.lineWidth = active ? 1.5 : 1.1;
        pinballContext.stroke();
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
