/* ============================================================
   CrowdCloud · Luxe Edition — client logic
   - Arabic-first i18n (secondary English) with live switching
   - Live polling of /api/services and /api/tickets/<n>
   - Ticket creation dialog
   - Staff panel actions (call next / serve / complete / cancel)
   All rendering updates existing DOM nodes in place, so the live
   transition NORMAL -> BUSY -> HIGH LOAD is visible without reload.
   ============================================================ */

"use strict";

const POLL_INTERVAL = {
  services: 3000,
  ticket: 3000,
  admin: 4000
};

/* ============================================================ i18n */

const I18N = {
  ar: {
    app_title: "كراود كلاود · نظام الطوابير الذكي",
    brand_name: "كراود كلاود",
    brand_sub: "منظومة الطوابير الذكية للخدمات الجامعية",
    nav_home: "الخدمات",
    nav_queue: "لوحة الطابور",
    nav_admin: "لوحة الموظف",
    footer_line: "كراود كلاود",
    footer_course: "الحوسبة السحابية والأنظمة الموزعة (3CCN314)",
    footer_mode: "نموذج عملي حي — عادي / مزدحم / حمل مرتفع",

    hero_eyebrow: "تجربة جامعية من الطبقة الأولى",
    hero_title_1: "خدمات الجامعة ",
    hero_title_2: "بنعمة الانتظار الذكي",
    hero_desc: "اختر خدمتك واحصل على تذكرتك فورًا، وتابع دورك لحظة بلحظة — يراقب كراود كلاود ضغط كل خدمة حيًّا، ويتنقل بالحالة من «عادي» إلى «مزدحم» ثم «حمل مرتفع» مع أولوية عادلة بالوصول الأول.",
    load_normal: "عادي",
    load_busy: "مزدحم",
    load_high: "حمل مرتفع",

    stat_overall: "الحالة العامة",
    stat_waiting: "في الانتظار الآن",
    stat_served: "تمت خدمتهم اليوم",
    stat_tickets: "تذاكر اليوم",

    card_waiting: "انتظار",
    card_serving: "قيد الخدمة",
    card_done: "تم اليوم",
    get_ticket: "احصل على تذكرة",
    thresholds_fmt: "«مزدحم» عند {busy} في الانتظار · «حمل مرتفع» عند {high}",

    modal_title: "إصدار تذكرة جديدة",
    modal_name: "الاسم",
    modal_optional: "اختياري",
    modal_ph: "مثال: عبدالله",
    modal_student_id: "الرقم الجامعي",
    modal_ph_id: "مثال: 441002357",
    modal_submitting: "جارٍ إصدار التذكرة…",
    val_name: "فضلاً أدخل الاسم أولًا",
    val_id: "فضلاً أدخل رقمًا جامعيًا صحيحًا (أرقام فقط، 4–15 رقمًا)",
    dup_active: "هذا الرقم الجامعي لديه تذكرة نشطة بالفعل لهذه الخدمة:",
    modal_cancel: "إلغاء",
    modal_submit: "أصدر التذكرة",
    modal_error_prefix: "خطأ: ",

    back_services: "كل الخدمات",
    ticket_sub: "تذكرة الطابور الخاصة بك",
    tk_ahead: "أمامك الآن",
    tk_eta: "الانتظار المتوقع",
    tk_created: "وقت الإصدار",
    tk_name: "الاسم",
    tk_student_id: "الرقم الجامعي",
    tk_min: "دقيقة",
    approx: "نحو",
    step_requested: "طلبت التذكرة",
    step_serving: "نُودي على دورك",
    step_done: "تمت الخدمة",
    ticket_note: "تُحدَّث هذه الصفحة تلقائيًا كل بضع ثوانٍ. الانتظار المتوقع يفترض متوسط خدمة دقيقتين للعميل الواحد عند الشبّاك (فرضية قابلة للضبط، وليست قياسًا فعليًا).",
    tk_cancel: "إلغاء تذكرتي",

    queue_title: "لوحة الطابور",
    queue_sub: "قوائم الانتظار الحية لكل خدمة — تُحدَّث تلقائيًا.",
    waiting_now: "في الانتظار",
    now_serving: "قيد الخدمة الآن",
    th_ticket: "التذكرة",
    th_customer: "العميل",
    th_since: "منذ",
    th_status: "الحالة",
    th_actions: "الإجراءات",
    empty_queue: "لا أحد في الانتظار — الطابور خالٍ.",
    waiting_count: "في الانتظار",

    admin_title: "لوحة الموظف",
    admin_sub: "نادِ العميل التالي، أكمل أو ألغِ التذاكر — تُطبَّق الإجراءات فورًا وذرّيًا.",
    st_waiting: "في الانتظار",
    st_serving: "قيد الخدمة",
    st_done: "تم اليوم",
    call_next: "نادِ التالي",
    refresh: "تحديث",
    btn_serve: "خدمة",
    btn_cancel: "إلغاء",
    btn_complete: "إكمال",
    empty_admin: "لا تذاكر بعد.",

    nf_title: "التذكرة غير موجودة",
    nf_desc: "لا توجد تذكرة بهذا الرقم — ربما أُزيلت بعد تصفير قاعدة البيانات.",
    nf_back: "العودة إلى الخدمات",

    status_waiting: "بانتظار دورك",
    status_serving: "دورك الآن",
    status_done: "تمت خدمتك",
    status_cancelled: "أُلغيت التذكرة",

    toast_now_serving: "قيد النداء الآن: {n}",
    toast_queue_empty: "الطابور فارغ",
    toast_serving: "التذكرة {n} قيد الخدمة",
    toast_completed: "أُكملت التذكرة {n}",
    toast_cancelled: "أُلغيت التذكرة {n}",

    modal_request: "طلبك أو استفسارك",
    modal_ph_request: "اكتب باختصار ما تحتاجه — مثال: حساب الجامعة معطّل ولا أستطيع الدخول للبوابة",
    tk_request: "طلبك / استفسارك",
    tk_chat: "محادثة الموظف",
    chat_lock_hint: "المحادثة شخصية بينك وبين الموظف، وتُفتح للإرسال عندما يحين دورك.",
    chat_unlocked: "حان دورك — يمكنك الآن مراسلة الموظف.",
    chat_closed: "أُغلقت هذه المحادثة بانتهاء التذكرة.",
    chat_send_locked: "سيتسنى لك الإرسال عندما يحين دورك",
    chat_msg_empty: "اكتب رسالة أو أرفق ملفًا أولًا",
    chat_file_too_large: "حجم الملف أكبر من الحد المسموح",
    chat_send_failed: "تعذّر الإرسال — حاول مجددًا",
    chat_title: "محادثة خاصة",
    chat_back_ticket: "تذكرتي",
    chat_back_admin: "لوحة الموظف",
    chat_ph: "اكتب رسالتك...",
    chat_file_remove: "إزالة",
    chat_note: "رسائل وصور وملفات فقط مع هذه التذكرة، ولا يراها أحد غيرك والموظف المسؤول.",
    chat_no_messages: "لا رسائل بعد — ابدأ المحادثة عندما يُتاح لك الإرسال.",
    chat_me: "أنا",
    chat_peer_staff: "الموظف",
    chat_peer_student: "الطالب",
    chat_download: "تنزيل المرفق",
    chat_sending: "جارٍ الإرسال...",
    btn_chat: "محادثة"
  },

  en: {
    app_title: "CrowdCloud · Smart Queue System",
    brand_name: "CrowdCloud",
    brand_sub: "Smart queue platform for campus services",
    nav_home: "Services",
    nav_queue: "Queue Board",
    nav_admin: "Staff Panel",
    footer_line: "CrowdCloud",
    footer_course: "Cloud Computing & Distributed Systems (3CCN314)",
    footer_mode: "Live working prototype — NORMAL / BUSY / HIGH LOAD",

    hero_eyebrow: "A first-class campus experience",
    hero_title_1: "Campus services ",
    hero_title_2: "with the grace of smart waiting",
    hero_desc: "Pick a service and get your ticket instantly, then track your turn live — CrowdCloud watches the pressure on every service in real time, moving its state from NORMAL to BUSY then HIGH LOAD with fair first-come priority.",
    load_normal: "NORMAL",
    load_busy: "BUSY",
    load_high: "HIGH LOAD",

    stat_overall: "Overall status",
    stat_waiting: "Waiting now",
    stat_served: "Served today",
    stat_tickets: "Tickets today",

    card_waiting: "Waiting",
    card_serving: "In service",
    card_done: "Done today",
    get_ticket: "Get a Ticket",
    thresholds_fmt: "BUSY at {busy} waiting · HIGH LOAD at {high}",

    modal_title: "Issue a new ticket",
    modal_name: "Your name",
    modal_optional: "optional",
    modal_ph: "e.g. Abdullah",
    modal_student_id: "Student ID",
    modal_ph_id: "e.g. 441002357",
    modal_submitting: "Issuing ticket…",
    val_name: "Please enter your name first",
    val_id: "Please enter a valid student ID (digits only, 4-15 digits)",
    dup_active: "This student ID already has an active ticket for this service:",
    modal_cancel: "Cancel",
    modal_submit: "Issue Ticket",
    modal_error_prefix: "Error: ",

    back_services: "All services",
    ticket_sub: "Your queue ticket",
    tk_ahead: "People ahead",
    tk_eta: "Estimated wait",
    tk_created: "Issued at",
    tk_name: "Name",
    tk_student_id: "Student ID",
    tk_min: "min",
    approx: "~",
    step_requested: "Ticket requested",
    step_serving: "Your turn called",
    step_done: "Served",
    ticket_note: "This page refreshes automatically every few seconds. The estimated wait assumes an average handling time of 2 minutes per customer at the counter (a configurable assumption, not a measured value).",
    tk_cancel: "Cancel my ticket",

    queue_title: "Queue Board",
    queue_sub: "Live waiting lists per service — refreshed automatically.",
    waiting_now: "waiting",
    now_serving: "In service now",
    th_ticket: "Ticket",
    th_customer: "Customer",
    th_since: "Since",
    th_status: "Status",
    th_actions: "Actions",
    empty_queue: "No one is waiting — queue is clear.",
    waiting_count: "waiting",

    admin_title: "Staff Panel",
    admin_sub: "Call the next customer, complete or cancel tickets — actions apply immediately and atomically.",
    st_waiting: "waiting",
    st_serving: "in service",
    st_done: "done today",
    call_next: "Call Next",
    refresh: "Refresh",
    btn_serve: "Serve",
    btn_cancel: "Cancel",
    btn_complete: "Complete",
    empty_admin: "No tickets yet.",

    nf_title: "Ticket not found",
    nf_desc: "No ticket exists with this number — it may have been removed by a database reset.",
    nf_back: "Back to services",

    status_waiting: "WAITING",
    status_serving: "YOUR TURN NOW",
    status_done: "SERVED",
    status_cancelled: "CANCELLED",

    toast_now_serving: "Now serving {n}",
    toast_queue_empty: "Queue is empty",
    toast_serving: "Ticket {n} is now being served",
    toast_completed: "Ticket {n} completed",
    toast_cancelled: "Ticket {n} cancelled",

    modal_request: "Your request or inquiry",
    modal_ph_request: "Briefly describe what you need — e.g. my university account is locked and I cannot sign in",
    tk_request: "Your request",
    tk_chat: "Chat with staff",
    chat_lock_hint: "This conversation is private between you and the staff member; sending unlocks when your turn arrives.",
    chat_unlocked: "It is your turn now — you can message the staff member.",
    chat_closed: "This conversation is closed (ticket finished).",
    chat_send_locked: "You can send once your turn arrives",
    chat_msg_empty: "Write a message or attach a file first",
    chat_file_too_large: "File is larger than the allowed limit",
    chat_send_failed: "Could not send — please retry",
    chat_title: "Private conversation",
    chat_back_ticket: "My ticket",
    chat_back_admin: "Staff panel",
    chat_ph: "Type your message...",
    chat_file_remove: "Remove",
    chat_note: "Messages, images and files stay with this ticket; nobody else can see them.",
    chat_no_messages: "No messages yet — start once sending is available.",
    chat_me: "Me",
    chat_peer_staff: "Staff",
    chat_peer_student: "Student",
    chat_download: "Download attachment",
    chat_sending: "Sending...",
    btn_chat: "Chat"
  }
};

const SERVICES_I18N = {
  ar: {
    academic_advising:    { name: "الإرشاد الأكاديمي", desc: "اختيار المقررات والخطط الدراسية والاستشارات الأكاديمية." },
    it_support:           { name: "الدعم التقني", desc: "دعم حسابات الجامعة والبريد الإلكتروني والبوابات والأنظمة." },
    registration_support: { name: "دعم التسجيل", desc: "إضافة وحذف المقررات والجداول ومشكلات التسجيل." },
    student_services:     { name: "خدمات الطلاب", desc: "الوثائق الرسمية والخطابات والطلبات العامة." }
  },
  en: {
    academic_advising:    { name: "Academic Advising", desc: "Course selection, academic plans and study advice." },
    it_support:           { name: "IT Support", desc: "Support for university accounts, email, portals and systems." },
    registration_support: { name: "Registration Support", desc: "Add/drop, schedules and registration issues." },
    student_services:     { name: "Student Services", desc: "Official documents, letters and general requests." }
  }
};

const LOADS = {
  ar: { "NORMAL": "عادي", "BUSY": "مزدحم", "HIGH LOAD": "حمل مرتفع" },
  en: { "NORMAL": "NORMAL", "BUSY": "BUSY", "HIGH LOAD": "HIGH LOAD" }
};

const STATUSES = {
  ar: { "WAITING": "بانتظار دورك", "SERVING": "دورك الآن", "DONE": "تمت خدمتك", "CANCELLED": "أُلغيت التذكرة" },
  en: { "WAITING": "WAITING", "SERVING": "YOUR TURN NOW", "DONE": "SERVED", "CANCELLED": "CANCELLED" }
};

let LANG = "ar";
try { LANG = localStorage.getItem("cc_lang") || "ar"; } catch (e) { /* private mode */ }

function t(key) {
  return (I18N[LANG] && I18N[LANG][key]) || I18N.ar[key] || key;
}
function tf(key, vars) {
  return t(key).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] !== undefined ? vars[k] : m));
}
function svcName(code) {
  const d = SERVICES_I18N[LANG] && SERVICES_I18N[LANG][code];
  return d ? d.name : code;
}
function loadLabel(load) {
  return (LOADS[LANG] && LOADS[LANG][load]) || load;
}
function statusLabel(status) {
  return (STATUSES[LANG] && STATUSES[LANG][status]) || status;
}
function minutesLabel(n) {
  if (LANG === "ar") {
    if (n === 1) return "دقيقة واحدة";
    if (n === 2) return "دقيقتين";
    if (n >= 3 && n <= 10) return n + " دقائق";
    return n + " دقيقة";
  }
  return n === 1 ? "1 min" : n + " mins";
}

/* ------------------------------------------------- language engine */

function applyLang(lang, rerender) {
  LANG = lang;
  try { localStorage.setItem("cc_lang", lang); } catch (e) { /* ignore */ }

  const html = document.documentElement;
  html.lang = lang;
  html.dir = lang === "ar" ? "rtl" : "ltr";
  document.title = t("app_title");

  const toggleLabel = document.getElementById("langLabel");
  if (toggleLabel) toggleLabel.textContent = lang === "ar" ? "EN" : "عربي";
  const toggle = document.getElementById("langToggle");
  if (toggle) toggle.setAttribute("aria-label", lang === "ar" ? "Switch to English" : "التبديل إلى العربية");

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (I18N.ar[key] !== undefined) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    const key = el.dataset.i18nPh;
    if (I18N.ar[key] !== undefined) el.placeholder = t(key);
  });
  document.querySelectorAll("[data-i18n-hint]").forEach((el) => {
    el.textContent = tf(el.dataset.i18nHint, { busy: el.dataset.busy, high: el.dataset.high });
  });

  document.querySelectorAll("[data-svc-name]").forEach((el) => {
    el.textContent = svcName(el.dataset.svcName);
  });
  document.querySelectorAll("[data-svc-desc]").forEach((el) => {
    const d = SERVICES_I18N[LANG] && SERVICES_I18N[LANG][el.dataset.svcDesc];
    if (d) el.textContent = d.desc;
  });
  document.querySelectorAll("[data-svc-ticket]").forEach((el) => {
    el.textContent = svcName(el.dataset.svcTicket);
  });

  localizeBadges();

  if (typeof modalState !== "undefined" && modalState.code && !document.getElementById("ticketModal").hidden) {
    document.getElementById("modalService").textContent = svcName(modalState.code);
  }
  if (rerender && typeof pageRefresh === "function") pageRefresh();
}

function localizeBadges() {
  document.querySelectorAll(".load-badge").forEach((el) => {
    el.textContent = loadLabel(el.dataset.load || el.textContent);
  });
  document.querySelectorAll(".status-pill").forEach((el) => {
    const raw = el.dataset.status || el.textContent;
    el.textContent = statusLabel(raw.trim().toUpperCase());
  });
}

function initLangToggle() {
  const btn = document.getElementById("langToggle");
  if (!btn) return;
  applyLang(LANG, false);
  btn.addEventListener("click", () => {
    const next = LANG === "ar" ? "en" : "ar";
    document.body.classList.add("lang-switching");
    applyLang(next, true);
    setTimeout(() => document.body.classList.remove("lang-switching"), 160);
  });
}

/* ------------------------------------------------- helpers */

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try { body = await res.json(); } catch (e) { /* non-JSON error body */ }
  if (!res.ok) {
    const message = body && body.error ? body.error : "HTTP " + res.status;
    const err = new Error(message);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

function badgeClass(load) {
  if (load === "BUSY") return "busy";
  if (load === "HIGH LOAD") return "high-load";
  return "";
}

function meterClass(load) {
  if (load === "BUSY") return "warn";
  if (load === "HIGH LOAD") return "high";
  return "";
}

function setBadge(el, load) {
  if (!el) return;
  el.dataset.load = load;
  el.className = "load-badge " + badgeClass(load);
  el.textContent = loadLabel(load);
}

function fmtTime(value) {
  if (!value) return "—";
  return String(value).replace("T", " ").slice(5, 16);
}

function toast(message, isError) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );
}

/* ------------------------------------------------- index page */

async function refreshServices() {
  const data = await fetchJSON("/api/services");
  const services = data.services || [];

  services.forEach((svc) => {
    const card = document.querySelector(`.service-card[data-service="${svc.code}"]`);
    if (!card) return;
    setBadge(card.querySelector('[data-role="load"]'), svc.load);
    card.querySelector('[data-role="waiting"]').textContent = svc.waiting;
    card.querySelector('[data-role="serving"]').textContent = svc.serving;
    card.querySelector('[data-role="done"]').textContent = svc.done_today;
    const meter = card.querySelector('[data-role="meter"]');
    if (meter) {
      meter.style.width = svc.load_percent + "%";
      meter.className = "load-meter-fill " + meterClass(svc.load);
    }
  });

  const stats = data.stats || {};
  setBadge(document.getElementById("overallBadge"), stats.overall_load);
  const totalWaiting = document.getElementById("totalWaiting");
  if (totalWaiting) totalWaiting.textContent = stats.waiting;
  const servedToday = document.getElementById("servedToday");
  if (servedToday) servedToday.textContent = stats.done_today;
  const ticketsToday = document.getElementById("ticketsToday");
  if (ticketsToday) ticketsToday.textContent = stats.created_today;
}

/* ------------------------------------------------- ticket modal */

const modalState = { code: null, name: "" };

function initTicketModal() {
  const modal = document.getElementById("ticketModal");
  if (!modal) return;
  const form = document.getElementById("ticketForm");
  const nameInput = document.getElementById("customerName");
  const idInput = document.getElementById("studentId");
  const reqInput = document.getElementById("requestText");
  const errorEl = document.getElementById("modalError");

  document.querySelectorAll(".get-ticket").forEach((btn) => {
    btn.addEventListener("click", () => {
      modalState.code = btn.dataset.code;
      modalState.name = btn.dataset.name;
      document.getElementById("modalService").textContent = svcName(modalState.code);
      errorEl.hidden = true;
      modal.hidden = false;
      setTimeout(() => nameInput.focus(), 60);
    });
  });

  document.getElementById("modalCancel").addEventListener("click", () => {
    modal.hidden = true;
  });

  modal.addEventListener("click", (event) => {
    if (event.target === modal) modal.hidden = true;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") modal.hidden = true;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.getElementById("modalSubmit");
    errorEl.hidden = true;

    const name = nameInput.value.trim();
    const sid = idInput.value.trim();
    if (!name) {
      errorEl.textContent = t("val_name");
      errorEl.hidden = false;
      nameInput.focus();
      return;
    }
    if (!/^\d{4,15}$/.test(sid)) {
      errorEl.textContent = t("val_id");
      errorEl.hidden = false;
      idInput.focus();
      return;
    }

    submit.disabled = true;
    submit.textContent = t("modal_submitting");
    try {
      const data = await fetchJSON("/api/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_code: modalState.code,
          customer_name: name,
          student_id: sid,
          request_text: reqInput ? reqInput.value.trim() : ""
        })
      });
      window.location.href = "/ticket/" + encodeURIComponent(data.ticket.ticket_number);
    } catch (err) {
      if (err.status === 409 && err.body && err.body.ticket) {
        errorEl.textContent = t("dup_active") + " " + err.body.ticket;
      } else {
        errorEl.textContent = t("modal_error_prefix") + err.message;
      }
      errorEl.hidden = false;
      submit.disabled = false;
      submit.textContent = t("modal_submit");
    }
  });
}

/* ------------------------------------------------- ticket page */

async function refreshTicket(number) {
  const data = await fetchJSON("/api/tickets/" + encodeURIComponent(number));
  const tk = data.ticket;

  const statusEl = document.querySelector('[data-role="status"]');
  if (statusEl) {
    statusEl.dataset.status = tk.status;
    statusEl.className = "status-pill status-" + tk.status.toLowerCase();
    statusEl.textContent = statusLabel(tk.status);
  }
  setBadge(document.querySelector('[data-role="load"]'), tk.load);
  document.querySelector('[data-role="ahead"]').textContent = tk.people_ahead;
  const etaEl = document.querySelector('[data-role="eta"]');
  if (etaEl) {
    etaEl.textContent = tk.status === "WAITING"
      ? t("approx") + " " + minutesLabel(tk.estimated_wait_minutes)
      : "—";
  }
  document.querySelector('[data-role="created"]').textContent = fmtTime(tk.created_at);

  const servingStates = ["SERVING", "DONE"];
  const cancelled = tk.status === "CANCELLED";
  const stepRequested = document.getElementById("stepRequested");
  const stepServing = document.getElementById("stepServing");
  const stepDone = document.getElementById("stepDone");
  if (stepRequested) stepRequested.className = cancelled ? "cancelled" : "done";
  if (stepServing) stepServing.className = servingStates.includes(tk.status) ? "done" : "";
  if (stepDone) stepDone.className = tk.status === "DONE" ? "done" : "";

  const cancelBtn = document.getElementById("cancelBtn");
  if (cancelBtn) {
    cancelBtn.disabled = tk.status !== "WAITING";
    cancelBtn.hidden = tk.status !== "WAITING";
  }

  // chat with staff: button always present, hint reflects the lock state
  const chatHint = document.getElementById("chatLockHint");
  if (chatHint) {
    if (tk.status === "WAITING") {
      chatHint.hidden = false;
      chatHint.textContent = t("chat_lock_hint");
    } else if (tk.status === "SERVING") {
      chatHint.hidden = false;
      chatHint.textContent = t("chat_unlocked");
      chatHint.classList.add("unlocked");
    } else {
      chatHint.hidden = false;
      chatHint.textContent = t("chat_closed");
      chatHint.classList.remove("unlocked");
    }
  }
  const chatBtn = document.getElementById("chatBtn");
  if (chatBtn && tk.messages_count) {
    const label = chatBtn.querySelector("span");
    if (label && !chatBtn.querySelector(".badge-count")) {
      const b = document.createElement("span");
      b.className = "badge-count";
      b.textContent = tk.messages_count;
      chatBtn.appendChild(b);
    } else if (chatBtn.querySelector(".badge-count")) {
      chatBtn.querySelector(".badge-count").textContent = tk.messages_count;
    }
  }
}

function initTicketPage() {
  const page = document.getElementById("ticketPage");
  if (!page) return;
  const number = page.dataset.ticket;
  const poll = () => refreshTicket(number).catch(() => {});
  poll();
  setInterval(poll, POLL_INTERVAL.ticket);

  const cancelBtn = document.getElementById("cancelBtn");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      cancelBtn.disabled = true;
      try {
        await fetchJSON(cancelBtn.dataset.url, { method: "POST" });
        toast(tf("toast_cancelled", { n: number }));
        poll();
      } catch (err) {
        toast(err.message, true);
        poll();
      }
    });
  }
}

/* ------------------------------------------------- queue board */

async function refreshQueueBoard() {
  const grid = document.getElementById("queueGrid");
  if (!grid) return;
  const data = await fetchJSON("/api/services");
  const stats = data.stats || {};
  setBadge(document.getElementById("overallBadge"), stats.overall_load);
  const totalWaiting = document.getElementById("totalWaiting");
  if (totalWaiting) totalWaiting.textContent = stats.waiting;

  (data.services || []).forEach((svc) => {
    const card = grid.querySelector(`.queue-card[data-service="${svc.code}"]`);
    if (!card) return;
    setBadge(card.querySelector('[data-role="load"]'), svc.load);
    card.querySelector('[data-role="serving-count"]').textContent = svc.serving;
    card.querySelector('[data-role="waiting"]').textContent = svc.waiting;
  });

  const detail = await fetchJSON("/api/tickets?status=WAITING&limit=200&waiting_first=1");
  const byService = {};
  (detail.tickets || []).forEach((tk) => {
    (byService[tk.service_code] = byService[tk.service_code] || []).push(tk);
  });
  document.querySelectorAll(".queue-card").forEach((card) => {
    const code = card.dataset.service;
    const rows = (byService[code] || []).slice(0, 12);
    const body = card.querySelector('[data-role="waiting-body"]');
    if (!body) return;
    body.innerHTML = rows.length
      ? rows.map((tk, i) => `<tr>
          <td>${i + 1}</td>
          <td class="mono">${escapeHtml(tk.ticket_number)}</td>
          <td>${escapeHtml(tk.customer_name || "—")}${tk.student_id ? ` <span class="mono muted">(${escapeHtml(tk.student_id)})</span>` : ""}</td>
          <td class="muted">${fmtTime(tk.created_at)}</td>
        </tr>`).join("")
      : `<tr class="empty-row"><td colspan="4">${t("empty_queue")}</td></tr>`;
  });
}

/* ------------------------------------------------- admin panel */

async function refreshAdminCard(code) {
  const data = await fetchJSON("/api/tickets?service_code=" + encodeURIComponent(code) + "&limit=15&waiting_first=1");
  const svcData = await fetchJSON("/api/services");
  const svc = (svcData.services || []).find((s) => s.code === code);
  const card = document.querySelector(`.admin-card[data-service="${code}"]`);
  if (!card || !svc) return;

  setBadge(card.querySelector('[data-role="load"]'), svc.load);
  card.querySelector('[data-role="waiting"]').textContent = svc.waiting;
  card.querySelector('[data-role="serving"]').textContent = svc.serving;
  card.querySelector('[data-role="done"]').textContent = svc.done_today;
  setBadge(document.getElementById("overallBadge"), svcData.stats.overall_load);

  const body = card.querySelector('[data-role="tickets-body"]');
  const tickets = data.tickets || [];
  body.innerHTML = tickets.length
    ? tickets.map((tk) => {
      const chatBtn = `<a class="mini-btn act-chat" href="/chat/${encodeURIComponent(tk.ticket_number)}?staff=1" title="${t("btn_chat")}">💬 ${t("btn_chat")}${tk.messages_count ? ` <span class="badge-count">${tk.messages_count}</span>` : ""}</a>`;
      let actions = '<span class="muted">—</span>';
      if (tk.status === "WAITING") {
        actions = `
          <button class="mini-btn act-serve" data-number="${escapeHtml(tk.ticket_number)}">${t("btn_serve")}</button>
          <button class="mini-btn act-cancel" data-number="${escapeHtml(tk.ticket_number)}">${t("btn_cancel")}</button>`;
      } else if (tk.status === "SERVING") {
        actions = `<button class="mini-btn act-complete" data-number="${escapeHtml(tk.ticket_number)}">${t("btn_complete")}</button>`;
      }
      const st = escapeHtml(tk.status);
      const reqLine = tk.request_text
        ? `<div class="req-line" title="${escapeHtml(tk.request_text)}">📄 ${escapeHtml(tk.request_text.length > 34 ? tk.request_text.slice(0, 34) + "…" : tk.request_text)}</div>`
        : "";
      return `<tr data-number="${escapeHtml(tk.ticket_number)}">
        <td class="mono">${escapeHtml(tk.ticket_number)}</td>
        <td>${escapeHtml(tk.customer_name || "—")}${tk.student_id ? ` <span class="mono muted">(${escapeHtml(tk.student_id)})</span>` : ""}${reqLine}</td>
        <td><span class="status-pill status-${st.toLowerCase()}" data-status="${st}">${statusLabel(tk.status)}</span></td>
        <td class="row-actions">${actions} ${chatBtn}</td>
      </tr>`;
    }).join("")
    : `<tr class="empty-row"><td colspan="4">${t("empty_admin")}</td></tr>`;
}

function initAdmin() {
  const grid = document.getElementById("adminGrid");
  if (!grid) return;

  const codes = [...grid.querySelectorAll(".admin-card")].map((c) => c.dataset.service);
  const refreshAll = () => codes.forEach((code) => refreshAdminCard(code).catch(() => {}));
  refreshAll();
  setInterval(refreshAll, POLL_INTERVAL.admin);

  grid.addEventListener("click", async (event) => {
    const btn = event.target.closest("button");
    if (!btn) return;
    const number = btn.dataset.number;
    try {
      if (btn.classList.contains("call-next")) {
        const data = await fetchJSON("/api/services/" + encodeURIComponent(btn.dataset.code) + "/next", { method: "POST" });
        toast(data.ticket
          ? tf("toast_now_serving", { n: data.ticket.ticket_number })
          : t("toast_queue_empty"));
      } else if (btn.classList.contains("refresh-card")) {
        await refreshAdminCard(btn.dataset.code);
      } else if (btn.classList.contains("act-serve")) {
        await fetchJSON("/api/tickets/" + encodeURIComponent(number) + "/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "SERVING" })
        });
        toast(tf("toast_serving", { n: number }));
      } else if (btn.classList.contains("act-complete")) {
        await fetchJSON("/api/tickets/" + encodeURIComponent(number) + "/status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "DONE" })
        });
        toast(tf("toast_completed", { n: number }));
      } else if (btn.classList.contains("act-cancel")) {
        await fetchJSON("/api/tickets/" + encodeURIComponent(number) + "/cancel", { method: "POST" });
        toast(tf("toast_cancelled", { n: number }));
      }
      if (btn.dataset.code) await refreshAdminCard(btn.dataset.code);
      else refreshAll();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ------------------------------------------------- page refresh registry */

let pageRefresh = null;

/* ------------------------------------------------- boot */

document.addEventListener("DOMContentLoaded", () => {
  initLangToggle();
  initTicketModal();

  if (document.getElementById("servicesGrid")) {
    pageRefresh = refreshServices;
    refreshServices().catch(() => {});
    setInterval(() => refreshServices().catch(() => {}), POLL_INTERVAL.services);
  }

  if (document.getElementById("ticketPage")) {
    pageRefresh = () => refreshTicket(document.getElementById("ticketPage").dataset.ticket).catch(() => {});
    initTicketPage();
  }

  if (document.getElementById("queueGrid")) {
    pageRefresh = refreshQueueBoard;
    refreshQueueBoard().catch(() => {});
    setInterval(() => refreshQueueBoard().catch(() => {}), 5000);
  }

  if (document.getElementById("adminGrid")) initAdmin();
});
