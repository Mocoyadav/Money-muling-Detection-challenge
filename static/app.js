let lastResult = null;
let cy = null;

function setLoading(isLoading) {
  const progress = document.getElementById("progress-bar");
  progress.style.display = isLoading ? "block" : "none";
}

function setError(msg) {
  const el = document.getElementById("error-message");
  el.textContent = msg || "";
}

function scoreToColor(score) {
  // 0 → green, 50 → yellow, 100 → red
  const s = Math.max(0, Math.min(100, score || 0));
  let r, g;
  if (s <= 50) {
    // green to yellow
    const t = s / 50;
    r = Math.round(255 * t);
    g = 200;
  } else {
    // yellow to red
    const t = (s - 50) / 50;
    r = 255;
    g = Math.round(200 * (1 - t));
  }
  return `rgb(${r},${g},120)`;
}

function renderGraph(graph, accounts) {
  const container = document.getElementById("graph-container");
  if (!container) return;

  const accountMap = {};
  (accounts || []).forEach((a) => {
    accountMap[a.account_id] = a;
  });

  const elements = [];

  (graph.nodes || []).forEach((n) => {
    const acc = accountMap[n.id];
    const score = acc ? acc.risk_score : n.risk_score || 0;
    elements.push({
      data: {
        id: n.id,
        label: n.id,
        risk_score: score,
      },
    });
  });

  (graph.edges || []).forEach((e) => {
    elements.push({
      data: {
        id: e.transaction_id,
        source: e.source,
        target: e.target,
        amount: e.amount,
        timestamp: e.timestamp,
      },
    });
  });

  cy = cytoscape({
    container,
    elements,
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "background-color": (ele) =>
            scoreToColor(ele.data("risk_score")),
          "border-width": 2,
          "border-color": "#222",
          "font-size": 10,
          "text-valign": "center",
          "text-halign": "center",
        },
      },
      {
        selector: "edge",
        style: {
          width: 1,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": "#aaa",
          "target-arrow-color": "#aaa",
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#3273dc",
          "border-width": 4,
        },
      },
    ],
    layout: {
      name: "cose",
      animate: false,
    },
  });

  cy.on("tap", "node", (evt) => {
    const node = evt.target;
    const id = node.id();
    const acc = accountMap[id];
    if (!acc) return;
    alert(
      `Account: ${id}\nRisk: ${acc.risk_score}\n\nReasons:\n- ${acc.reasons.join(
        "\n- "
      )}`
    );
  });
}

function renderRings(rings) {
  const body = document.getElementById("rings-table-body");
  body.innerHTML = "";
  if (!rings || !rings.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.textContent = "No fraud rings detected.";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }

  rings.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.ring_id}</td>
      <td>${r.pattern_type}</td>
      <td>${r.risk_score.toFixed(2)}</td>
      <td>${r.members.join(", ")}</td>
    `;
    body.appendChild(tr);
  });
}

function renderAccounts(accounts) {
  const body = document.getElementById("accounts-table-body");
  body.innerHTML = "";
  if (!accounts || !accounts.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 3;
    td.textContent = "No accounts scored.";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }

  accounts.slice(0, 50).forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.account_id}</td>
      <td>${a.risk_score.toFixed(2)}</td>
      <td>${a.reasons.slice(0, 4).join("; ")}</td>
    `;
    body.appendChild(tr);
  });
}

async function handleAnalyze(event) {
  event.preventDefault();
  setError("");

  const fileInput = document.getElementById("file-input");
  const file = fileInput.files[0];
  if (!file) {
    setError("Please choose a CSV file first.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setLoading(true);
  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || "Analysis failed.");
    }
    const data = await resp.json();
    lastResult = data;

    renderGraph(data.graph || {}, data.accounts || []);
    renderRings(data.fraud_rings || []);
    renderAccounts(data.accounts || []);

    document.getElementById("download-json-btn").disabled = false;
  } catch (e) {
    console.error(e);
    setError(e.message || "Unexpected error.");
  } finally {
    setLoading(false);
  }
}

function handleDownloadJson() {
  if (!lastResult) return;
  const blob = new Blob([JSON.stringify(lastResult, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "fraud_detection_result.json";
  a.click();
  URL.revokeObjectURL(url);
}

document.addEventListener("DOMContentLoaded", () => {
  document
    .getElementById("upload-form")
    .addEventListener("submit", handleAnalyze);
  document
    .getElementById("download-json-btn")
    .addEventListener("click", handleDownloadJson);
});

