const symbolEl = document.getElementById("symbol");
const quantityEl = document.getElementById("quantity");
const livePrice = document.getElementById("livePrice");
const liveTotal = document.getElementById("liveTotal");
const submitBtn = document.getElementById("submitBtn");
const orderMsg = document.getElementById("orderMsg");
const marketBody = document.getElementById("marketBody");
const posBody = document.getElementById("posBody");
const tradeBody = document.getElementById("tradeBody");
const equityValue = document.getElementById("equityValue");
const equityPnl = document.getElementById("equityPnl");
const cashLine = document.getElementById("cashLine");
const orderForm = document.getElementById("orderForm");
const tabBuy = document.getElementById("tabBuy");
const tabSell = document.getElementById("tabSell");

let side = "BUY";
let quotes = [];

function money(n) {
  return Number(n).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " TL";
}

function setSide(next) {
  side = next;
  tabBuy.classList.toggle("is-active", side === "BUY");
  tabSell.classList.toggle("is-active", side === "SELL");
  submitBtn.textContent = side === "BUY" ? "Al" : "Sat";
  submitBtn.className = side === "BUY" ? "btn-buy" : "btn-sell";
  updateTotals();
}

tabBuy.addEventListener("click", () => setSide("BUY"));
tabSell.addEventListener("click", () => setSide("SELL"));

function selectedQuote() {
  return quotes.find((q) => q.symbol === symbolEl.value);
}

function updateTotals() {
  const q = selectedQuote();
  const qty = Number(quantityEl.value || 0);
  if (!q) {
    livePrice.textContent = "Fiyat: —";
    liveTotal.textContent = "Toplam: —";
    return;
  }
  livePrice.textContent = `Fiyat: ${money(q.price)}`;
  liveTotal.textContent = `Toplam: ${money(q.price * qty)}`;
}

symbolEl.addEventListener("change", updateTotals);
quantityEl.addEventListener("input", updateTotals);

async function loadMarket() {
  const res = await fetch("/api/market");
  const data = await res.json();
  quotes = data.quotes || [];
  const current = symbolEl.value;
  symbolEl.innerHTML = quotes
    .map((q) => `<option value="${q.symbol}">${q.symbol} — ${q.name}</option>`)
    .join("");
  if (current && quotes.some((q) => q.symbol === current)) symbolEl.value = current;
  marketBody.innerHTML = quotes
    .map((q) => {
      const cls = q.change_pct >= 0 ? "up" : "down";
      const sign = q.change_pct >= 0 ? "+" : "";
      return `<tr class="row-click" data-symbol="${q.symbol}"><td>${q.symbol}<br><small style="color:var(--mute)">${q.name}</small></td><td>${money(q.price)}</td><td class="${cls}">${sign}${q.change_pct}%</td></tr>`;
    })
    .join("");
  marketBody.querySelectorAll("tr[data-symbol]").forEach((row) => {
    row.addEventListener("click", () => {
      symbolEl.value = row.dataset.symbol;
      updateTotals();
    });
  });
  updateTotals();
}

async function loadPortfolio() {
  const res = await fetch("/api/portfolio");
  const data = await res.json();
  equityValue.textContent = money(data.equity);
  equityPnl.textContent = `${data.pnl >= 0 ? "+" : ""}${money(data.pnl)}`;
  equityPnl.className = `equity__pnl ${data.pnl >= 0 ? "up" : "down"}`;
  cashLine.textContent = `Nakit: ${money(data.cash)}`;

  posBody.innerHTML = (data.positions || []).length
    ? data.positions
        .map((p) => {
          const cls = p.pnl >= 0 ? "up" : "down";
          return `<tr class="row-click" data-symbol="${p.symbol}"><td>${p.symbol}</td><td>${p.quantity}</td><td>${money(p.avg_cost)}</td><td class="${cls}">${money(p.pnl)} (${p.pnl_pct}%)</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="4" style="color:var(--mute)">Pozisyon yok</td></tr>`;

  posBody.querySelectorAll("tr[data-symbol]").forEach((row) => {
    row.addEventListener("click", () => {
      symbolEl.value = row.dataset.symbol;
      setSide("SELL");
    });
  });

  tradeBody.innerHTML = (data.trades || []).length
    ? data.trades
        .map((t) => {
          const cls = t.side === "BUY" ? "up" : "down";
          const label = t.side === "BUY" ? "AL" : "SAT";
          return `<tr><td class="${cls}">${label}</td><td>${t.symbol}</td><td>${t.quantity}</td><td>${money(t.price)}</td></tr>`;
        })
        .join("")
    : `<tr><td colspan="4" style="color:var(--mute)">İşlem yok</td></tr>`;
}

orderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  orderMsg.textContent = "";
  submitBtn.disabled = true;
  try {
    const endpoint = side === "BUY" ? "/api/buy" : "/api/sell";
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: symbolEl.value,
        quantity: Number(quantityEl.value),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Emir reddedildi");
    const o = data.order;
    orderMsg.textContent = `${o.side === "BUY" ? "Alındı" : "Satıldı"}: ${o.quantity} ${o.symbol} @ ${money(o.price)}`;
    await Promise.all([loadMarket(), loadPortfolio()]);
  } catch (err) {
    orderMsg.textContent = err.message || "Hata";
  } finally {
    submitBtn.disabled = false;
  }
});

document.getElementById("refreshBtn").addEventListener("click", () => {
  loadMarket();
  loadPortfolio();
});

document.getElementById("resetBtn").addEventListener("click", async () => {
  if (!confirm("Portföy sıfırlansın mı?")) return;
  await fetch("/api/reset", { method: "POST" });
  await Promise.all([loadMarket(), loadPortfolio()]);
  orderMsg.textContent = "Portföy sıfırlandı.";
});

async function boot() {
  await loadMarket();
  await loadPortfolio();
  setInterval(() => {
    loadMarket();
    loadPortfolio();
  }, 4000);
}

boot();
