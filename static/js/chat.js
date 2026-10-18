/* ============================================================
   CrowdCloud · private student <-> staff chat
   - one thread per ticket, addressed by the ticket number
   - STUDENT cannot send anything (text, image, file) until his
     turn arrives (ticket status becomes SERVING); enforced
     server-side too, this UI only mirrors the state
   - live updates by polling the messages endpoint
   ============================================================ */

"use strict";

(function () {
  const page = document.getElementById("chatPage");
  if (!page) return;

  const NUMBER = page.dataset.ticket;
  const MODE = page.dataset.roleMode === "staff" ? "staff" : "student";
  const SENDER = MODE === "staff" ? "staff" : "student";
  const POLL_MS = 2500;

  const listEl = document.getElementById("chatMessages");
  const lockEl = document.getElementById("chatLock");
  const lockTextEl = document.getElementById("chatLockText");
  const form = document.getElementById("chatForm");
  const textEl = document.getElementById("chatText");
  const sendBtn = document.getElementById("sendBtn");
  const attachBtn = document.getElementById("attachBtn");
  const fileInput = document.getElementById("chatFile");
  const fileRow = document.getElementById("composerFile");
  const fileNameEl = document.getElementById("composerFileName");
  const fileRemove = document.getElementById("fileRemove");
  const errorEl = document.getElementById("chatError");
  const statusEl = document.querySelector('[data-role="status"]');

  let canSend = false;        // for THIS side of the conversation
  let lastRenderedId = -1;
  let selectedFile = null;

  /* ------------------------------------------------ helpers */

  function fmtSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB";
    return bytes + " B";
  }

  function isImage(mime, name) {
    if (mime && mime.startsWith("image/")) return true;
    return /\.(png|jpe?g|gif|webp|bmp)$/i.test(name || "");
  }

  function attachmentHtml(m) {
    const url = "/uploads/" + encodeURIComponent(NUMBER) + "/" + encodeURIComponent(m.stored_name);
    const name = escapeHtml(m.file_name || "attachment");
    if (isImage(m.file_mime, m.file_name)) {
      return `<a href="${url}" target="_blank" rel="noopener" class="msg-attachment" title="${t("chat_download")}">
                <img src="${url}" alt="${name}" loading="lazy">
              </a>`;
    }
    return `<a href="${url}" target="_blank" rel="noopener" class="msg-file" title="${t("chat_download")}">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/>
                <path d="M14 3v5h5"/>
              </svg>
              <span class="msg-file-name">${name}</span>
              <span class="msg-file-size">${fmtSize(m.file_size || 0)}</span>
            </a>`;
  }

  function messageHtml(m) {
    const mine = m.sender === SENDER.toUpperCase();
    const who = mine
      ? t("chat_me")
      : (m.sender === "STAFF" ? t("chat_peer_staff") : t("chat_peer_student"));
    const body = [
      m.text ? `<p class="msg-text">${escapeHtml(m.text)}</p>` : "",
      m.stored_name ? attachmentHtml(m) : ""
    ].filter(Boolean).join("");
    return `<div class="msg ${mine ? "mine" : "theirs"}">
              <div class="msg-bubble">
                <span class="msg-who">${who}</span>
                ${body}
                <span class="msg-time">${fmtTime(m.created_at)}</span>
              </div>
            </div>`;
  }

  function render(data) {
    // thread header state
    const st = data.ticket.status;
    if (statusEl) {
      statusEl.dataset.status = st;
      statusEl.className = "status-pill status-" + st.toLowerCase();
      statusEl.textContent = statusLabel(st);
    }

    canSend = MODE === "staff" ? data.can_staff_send : data.can_student_send;

    if (canSend) {
      lockEl.hidden = true;
    } else {
      lockEl.hidden = false;
      if (st === "DONE" || st === "CANCELLED") {
        lockTextEl.textContent = t("chat_closed");
      } else {
        lockTextEl.textContent = MODE === "staff"
          ? t("chat_note")
          : t("chat_lock_hint");
      }
    }
    form.classList.toggle("locked", !canSend);
    textEl.disabled = !canSend;
    attachBtn.disabled = !canSend;
    sendBtn.disabled = !canSend;
    textEl.placeholder = canSend
      ? t("chat_ph")
      : (st === "DONE" || st === "CANCELLED" ? t("chat_closed") : t("chat_send_locked"));

    // messages (render only when the list actually changed)
    const msgs = data.messages || [];
    const topId = msgs.length ? msgs[msgs.length - 1].id : -1;
    if (topId !== lastRenderedId) {
      lastRenderedId = topId;
      listEl.innerHTML = msgs.length
        ? msgs.map(messageHtml).join("")
        : `<div class="chat-empty">${t("chat_no_messages")}</div>`;
      listEl.scrollTop = listEl.scrollHeight;
    }
  }

  async function poll() {
    try {
      const data = await fetchJSON("/api/tickets/" + encodeURIComponent(NUMBER) + "/messages");
      render(data);
    } catch (err) {
      /* transient network error: keep last state, retry next tick */
    }
  }

  /* ------------------------------------------------ sending */

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
    setTimeout(() => { errorEl.hidden = true; }, 4000);
  }

  function pickFile() {
    if (!canSend) return;
    fileInput.click();
  }

  fileInput.addEventListener("change", () => {
    selectedFile = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
    if (selectedFile) {
      fileNameEl.textContent = selectedFile.name + " · " + fmtSize(selectedFile.size);
      fileRow.hidden = false;
    } else {
      fileRow.hidden = true;
    }
  });

  fileRemove.addEventListener("click", () => {
    selectedFile = null;
    fileInput.value = "";
    fileRow.hidden = true;
  });

  attachBtn.addEventListener("click", pickFile);

  textEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!form.classList.contains("locked")) form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canSend) {
      showError(t("chat_send_locked"));
      return;
    }
    const text = textEl.value.trim();
    if (!text && !selectedFile) {
      showError(t("chat_msg_empty"));
      return;
    }

    sendBtn.disabled = true;
    try {
      if (selectedFile) {
        const fd = new FormData();
        fd.append("sender", SENDER);
        fd.append("text", text);
        fd.append("file", selectedFile);
        await fetchJSON("/api/tickets/" + encodeURIComponent(NUMBER) + "/messages", {
          method: "POST",
          body: fd
        });
      } else {
        await fetchJSON("/api/tickets/" + encodeURIComponent(NUMBER) + "/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender: SENDER, text: text })
        });
      }
      textEl.value = "";
      selectedFile = null;
      fileInput.value = "";
      fileRow.hidden = true;
      errorEl.hidden = true;
      await poll();
    } catch (err) {
      if (err.status === 403) {
        await poll();            // refresh the lock state, then explain
        showError(err.body && err.body.reason === "not_your_turn"
          ? t("chat_send_locked")
          : t("chat_closed"));
      } else if (err.status === 400) {
        showError((err.body && err.body.error) || t("chat_file_too_large"));
      } else {
        showError(t("chat_send_failed"));
      }
    } finally {
      sendBtn.disabled = !canSend;
    }
  });

  /* ------------------------------------------------ boot */

  poll();
  setInterval(poll, POLL_MS);
})();
