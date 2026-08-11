const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("message");
const sendButton = document.getElementById("send");
const statusEl = document.getElementById("status");

function addBubble(role, text, meta) {
  const bubble = document.createElement("div");
  bubble.className = `bubble bubble--${role}`;
  bubble.textContent = text;
  if (meta) {
    const metaEl = document.createElement("span");
    metaEl.className = "bubble__meta";
    metaEl.textContent = meta;
    bubble.appendChild(metaEl);
  }
  transcript.appendChild(bubble);
  transcript.scrollTop = transcript.scrollHeight;
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    statusEl.textContent = data.ollama
      ? `Ollama hazır · ${data.model}`
      : "Yerel mod · Ollama bağlı değil";
  } catch {
    statusEl.textContent = "Sunucuya ulaşılamadı";
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;

  addBubble("user", message);
  messageInput.value = "";
  sendButton.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      throw new Error("İstek başarısız");
    }
    const data = await res.json();
    addBubble("assistant", data.reply, `${data.intent} · ${data.source}`);
  } catch (error) {
    addBubble("assistant", "Bir sorun oldu. Biraz sonra tekrar dene.");
  } finally {
    sendButton.disabled = false;
    messageInput.focus();
  }
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

addBubble(
  "assistant",
  "Merhaba. Ben Borsa. Yerelde çalışırım — bana adını söyle, aklımda tutayım."
);
refreshStatus();
