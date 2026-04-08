const form = document.getElementById("research-form");
const runBtn = document.getElementById("run-btn");
const loadingBox = document.getElementById("loading");
const metricsBox = document.getElementById("metrics");
const claimsBox = document.getElementById("claims");
const sourcesBox = document.getElementById("sources");
const reportBox = document.getElementById("report");
const traceBox = document.getElementById("trace");

let previousMetrics = null;

function show(el, yes = true) {
  if (yes) {
    el.classList.remove("hidden");
    el.classList.remove("reveal-in");
    requestAnimationFrame(() => {
      el.classList.add("reveal-in");
    });
  } else {
    el.classList.add("hidden");
  }
}

function sanitize(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDeltaNumber(delta) {
  const abs = Math.abs(delta);
  const value = abs >= 1 ? abs.toFixed(0) : abs.toFixed(2);
  return `${delta > 0 ? "+" : "-"}${value}`;
}

function buildTrend(meta, currentValue, previousValue) {
  if (previousValue === null || previousValue === undefined || Number.isNaN(previousValue)) {
    return { label: "NEW", cls: "trend-neutral" };
  }

  const delta = currentValue - previousValue;
  if (Math.abs(delta) < 0.0001) {
    return { label: "UNCHANGED", cls: "trend-neutral" };
  }

  const improved = meta.higherBetter ? delta > 0 : delta < 0;
  const arrow = improved ? "▲" : "▼";
  const cls = improved ? "trend-up" : "trend-down";
  const unit = meta.unit || "";
  return { label: `${arrow} ${formatDeltaNumber(delta)}${unit}`, cls };
}

function metricCard(meta, metrics) {
  const currentValue = metrics[meta.key];
  const previousValue = previousMetrics ? previousMetrics[meta.key] : null;
  const trend = buildTrend(meta, Number(currentValue || 0), Number(previousValue || 0));
  const display = meta.formatter ? meta.formatter(currentValue) : currentValue;
  return `
    <article class="metric-card">
      <p class="metric-label">${meta.label}</p>
      <p class="metric-value">${display}</p>
      <span class="metric-trend ${trend.cls}">${trend.label}</span>
    </article>
  `;
}

function renderMetrics(metrics) {
  const specs = [
    { key: "source_count", label: "Sources", higherBetter: true },
    { key: "fulltext_source_count", label: "Full-Text", higherBetter: true },
    { key: "claim_count", label: "Claims", higherBetter: true },
    { key: "total_elapsed_ms", label: "Latency", higherBetter: false, unit: "ms", formatter: (v) => `${v} ms` },
    { key: "source_fetch_elapsed_ms", label: "Source Fetch", higherBetter: false, unit: "ms", formatter: (v) => `${v} ms` },
    { key: "estimated_tokens", label: "Tokens", higherBetter: false, formatter: (v) => Number(v).toLocaleString() },
    { key: "estimated_cost_usd", label: "Est. Cost", higherBetter: false, formatter: (v) => `$${v}` },
  ];

  if (typeof metrics.memory_recall_hits === "number") {
    specs.push({ key: "memory_recall_hits", label: "Memory Hits", higherBetter: true });
  }
  if (typeof metrics.memory_injection_tokens === "number") {
    specs.push({
      key: "memory_injection_tokens",
      label: "Memory Tokens",
      higherBetter: false,
    });
  }
  if (typeof metrics.memory_queue_latency_ms === "number") {
    specs.push({
      key: "memory_queue_latency_ms",
      label: "Memory Queue",
      higherBetter: false,
      unit: "ms",
      formatter: (v) => `${v} ms`,
    });
  }

  metricsBox.innerHTML = specs.map((spec) => metricCard(spec, metrics)).join("");
  previousMetrics = metrics;
  show(metricsBox, true);
}

function renderClaims(claims) {
  if (!claims.length) {
    claimsBox.innerHTML = "<h2>Claim-Evidence Chain</h2><p>No claims were extracted in this run.</p>";
    show(claimsBox, true);
    return;
  }

  const html = claims
    .map((c) => {
      const support = c.supporting_sources
        .map(
          (s) =>
            `<li><a href="${s.url}" target="_blank" rel="noreferrer">${sanitize(s.title)}</a> <small>(score ${s.relevance_score}, ${sanitize(s.evidence_origin)})</small><br/><small>${sanitize(s.snippet)}</small></li>`
        )
        .join("");
      const conflict = c.conflicting_sources
        .map(
          (s) =>
            `<li><a href="${s.url}" target="_blank" rel="noreferrer">${sanitize(s.title)}</a> <small>(${sanitize(s.evidence_origin)})</small><br/><small>${sanitize(s.snippet)}</small></li>`
        )
        .join("");

      return `
        <article class="claim">
          <h3>${sanitize(c.claim_id)} - ${sanitize(c.statement)}</h3>
          <p><small>${sanitize(c.rationale)}</small></p>
          <p class="confidence">Confidence: ${c.confidence}</p>
          <p><strong>Supporting Evidence</strong></p>
          <ul class="list">${support || "<li>None</li>"}</ul>
          <p class="conflict">Conflicts: ${c.conflicting_sources.length}</p>
          <ul class="list">${conflict || "<li>None</li>"}</ul>
        </article>
      `;
    })
    .join("");

  claimsBox.innerHTML = `<h2>Claim-Evidence Chain</h2>${html}`;
  show(claimsBox, true);
}

function renderSources(sources) {
  if (!sources.length) {
    sourcesBox.innerHTML = "<h2>Source Quality</h2><p>No source candidates were returned.</p>";
    show(sourcesBox, true);
    return;
  }
  const rows = sources
    .slice(0, 14)
    .map((s) => {
      const preview = s.content_preview || s.snippet;
      const statusClass = s.fetch_status.startsWith("fulltext") ? "ok-badge" : "warn-badge";
      return `
        <article class="source-row">
          <p>
            <a href="${s.url}" target="_blank" rel="noreferrer">${sanitize(s.title)}</a>
            <span class="${statusClass}">${sanitize(s.fetch_status)}</span>
          </p>
          <p><small>${sanitize(preview.slice(0, 260))}</small></p>
        </article>
      `;
    })
    .join("");

  sourcesBox.innerHTML = `<h2>Source Quality</h2>${rows}`;
  show(sourcesBox, true);
}

function applyInlineMarkdown(line) {
  let html = sanitize(line);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return html;
}

function renderMarkdown(mdText) {
  const src = String(mdText || "").replace(/\r\n/g, "\n");
  const blocks = src.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const htmlBlocks = [];

  for (const block of blocks) {
    const lines = block.split("\n");
    if (lines.every((l) => l.trim().startsWith("- "))) {
      const items = lines
        .map((l) => `<li>${applyInlineMarkdown(l.trim().slice(2))}</li>`)
        .join("");
      htmlBlocks.push(`<ul>${items}</ul>`);
      continue;
    }
    if (lines.every((l) => /^\d+\.\s+/.test(l.trim()))) {
      const items = lines
        .map((l) => `<li>${applyInlineMarkdown(l.trim().replace(/^\d+\.\s+/, ""))}</li>`)
        .join("");
      htmlBlocks.push(`<ol>${items}</ol>`);
      continue;
    }
    if (/^#{1,4}\s+/.test(lines[0])) {
      const match = lines[0].match(/^(#{1,4})\s+(.*)$/);
      const level = Math.min(4, match[1].length);
      const title = applyInlineMarkdown(match[2]);
      const rest = lines.slice(1).map((l) => applyInlineMarkdown(l)).join("<br/>");
      htmlBlocks.push(`<h${level}>${title}</h${level}>${rest ? `<p>${rest}</p>` : ""}`);
      continue;
    }
    const paragraph = lines.map((l) => applyInlineMarkdown(l)).join("<br/>");
    htmlBlocks.push(`<p>${paragraph}</p>`);
  }

  return htmlBlocks.join("\n");
}

function renderReport(markdown) {
  const html = renderMarkdown(markdown);
  reportBox.innerHTML = `<h2>Report Draft</h2><article class="markdown">${html}</article>`;
  show(reportBox, true);
}

function renderTrace(steps) {
  const html = steps
    .map(
      (s) => `
      <div class="step">
        <h4>Loop ${s.loop_index}</h4>
        <p><strong>Query:</strong> ${sanitize(s.query)}</p>
        <p><strong>Sources:</strong> +${s.new_sources} (total ${s.total_sources})</p>
        <p><strong>Claims in loop:</strong> ${s.claims.length}</p>
      </div>
    `
    )
    .join("");
  traceBox.innerHTML = `<h2>Execution Trace</h2>${html}`;
  show(traceBox, true);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const topic = document.getElementById("topic").value.trim();
  const loops = Number(document.getElementById("loops").value);
  const topK = Number(document.getElementById("top_k").value);
  const sessionId = document.getElementById("session_id").value.trim();
  const useMemory = document.getElementById("use_memory").checked;
  const memoryBackend = document.getElementById("memory_backend").value;
  const memoryBudget = Number(document.getElementById("memory_budget_tokens").value);
  const memoryScope = document.getElementById("memory_scope").value;

  if (!topic) return;

  show(loadingBox, true);
  show(metricsBox, false);
  show(claimsBox, false);
  show(sourcesBox, false);
  show(reportBox, false);
  show(traceBox, false);
  runBtn.disabled = true;

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        loops,
        top_k: topK,
        session_id: sessionId,
        use_memory: useMemory,
        memory_backend: memoryBackend,
        memory_budget_tokens: memoryBudget,
        memory_scope: memoryScope,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Unknown error");
    }
    const data = await response.json();

    renderMetrics(data.metrics);
    if (data.session_id) {
      document.getElementById("session_id").value = data.session_id;
    }
    renderClaims(data.final_claims);
    renderSources(data.sources);
    renderReport(data.report_markdown);
    renderTrace(data.steps);
  } catch (error) {
    reportBox.innerHTML = `<h2>Error</h2><p>${sanitize(error.message)}</p>`;
    show(reportBox, true);
  } finally {
    show(loadingBox, false);
    runBtn.disabled = false;
  }
});
