const form = document.getElementById("research-form");
const runBtn = document.getElementById("run-btn");
const loadingBox = document.getElementById("loading");
const metricsBox = document.getElementById("metrics");
const claimsBox = document.getElementById("claims");
const sourcesBox = document.getElementById("sources");
const reportBox = document.getElementById("report");
const traceBox = document.getElementById("trace");

function show(el, yes = true) {
  if (yes) {
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}

function card(label, value) {
  return `
    <article class="metric-card">
      <p class="metric-label">${label}</p>
      <p class="metric-value">${value}</p>
    </article>
  `;
}

function sanitize(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMetrics(metrics) {
  const cards = [
    card("Sources", metrics.source_count),
    card("Full-Text Sources", metrics.fulltext_source_count),
    card("Claims", metrics.claim_count),
    card("Latency", `${metrics.total_elapsed_ms} ms`),
    card("Source Fetch", `${metrics.source_fetch_elapsed_ms} ms`),
    card("Tokens", metrics.estimated_tokens.toLocaleString()),
    card("Est. Cost", `$${metrics.estimated_cost_usd}`),
  ];
  if (typeof metrics.memory_recall_hits === "number") {
    cards.push(card("Memory Hits", metrics.memory_recall_hits));
  }
  if (typeof metrics.memory_injection_tokens === "number") {
    cards.push(card("Memory Tokens", metrics.memory_injection_tokens));
  }
  if (typeof metrics.memory_queue_latency_ms === "number") {
    cards.push(card("Memory Queue", `${metrics.memory_queue_latency_ms} ms`));
  }
  metricsBox.innerHTML = cards.join("");
  show(metricsBox, true);
}

function renderClaims(claims) {
  if (!claims.length) {
    claimsBox.innerHTML = "<h2>Claims</h2><p>No claims were extracted.</p>";
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
    sourcesBox.innerHTML = "<h2>Source Quality</h2><p>No sources found.</p>";
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

function renderReport(markdown) {
  reportBox.innerHTML = `<h2>Report Draft</h2><pre>${sanitize(markdown)}</pre>`;
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
