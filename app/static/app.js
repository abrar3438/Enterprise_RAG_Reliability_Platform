const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const tickerSel = document.getElementById("ticker");
const btn = document.getElementById("submit");
const statusEl = document.getElementById("status");
const answerEl = document.getElementById("answer");
const citeEl = document.getElementById("citations");

const MESSAGES = {
  429: "Too many requests. Please wait a minute and try again.",
  502: "The answer service is temporarily unavailable. Please try again shortly.",
  503: "The answer service is unavailable right now. Please try again later.",
};

function setBusy(busy) {
  btn.disabled = busy;
  if (busy) statusEl.textContent = "Searching the filings...";
}

function clearResults() {
  answerEl.textContent = "";
  answerEl.classList.remove("refused");
  citeEl.replaceChildren();
}

function renderCitations(list) {
  citeEl.replaceChildren();
  for (const c of list) {
    const li = document.createElement("li");

    const head = document.createElement("strong");
    head.textContent = `[${c.number}] ${c.ticker || ""} · ${c.filing_date || ""}`;

    const section = document.createElement("div");
    section.className = "section";
    section.textContent = c.section || "";

    const preview = document.createElement("blockquote");
    preview.textContent = c.preview || "";

    li.append(head, section, preview);
    citeEl.append(li);
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  clearResults();
  setBusy(true);

  const body = { question };
  if (tickerSel.value) body.ticker = tickerSel.value;

  try {
    const res = await fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      statusEl.textContent = MESSAGES[res.status] || "Something went wrong. Please try again.";
      return;
    }

    const data = await res.json();
    answerEl.textContent = data.answer;
    answerEl.classList.toggle("refused", Boolean(data.refused));
    renderCitations(data.citations || []);
    statusEl.textContent = data.cache_hit ? "Answered from cache." : "";
  } catch {
    statusEl.textContent = "Network error. Check your connection and try again.";
  } finally {
    btn.disabled = false;
  }
});

document.querySelectorAll("[data-example]").forEach((b) => {
  b.addEventListener("click", () => {
    input.value = b.dataset.example;
    form.requestSubmit();
  });
});