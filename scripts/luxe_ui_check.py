"""Full button-by-button functional test of the CrowdCloud Luxe UI.

Drives a real browser against a RUNNING server (default http://127.0.0.1:5000,
overridable as the first CLI argument or via CROWDCLOUD_URL) and clicks
EVERY button in both languages, asserting the effect each time.

Requires: pip install playwright && playwright install chromium
"""

import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "CROWDCLOUD_URL", "http://127.0.0.1:5000")
SHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(SHOTS_DIR, exist_ok=True)
RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({extra})" if extra else ""))


def api(path, payload=None):
    if payload is None:
        req = urllib.request.Request(BASE + path)
    else:
        req = urllib.request.Request(
            BASE + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def run():
    api("/api/demo/reset", {})
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1360, "height": 940})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        failed_resources = []
        def on_response(r):
            if r.status >= 400 and r.request.resource_type != "document":
                # 409 on POST /api/tickets is the intentional duplicate-ID
                # rejection tested below - not a failure.
                if r.status == 409 and "/api/tickets" in r.url and r.request.method == "POST":
                    return
                failed_resources.append(f"{r.status} {r.url}")
        page.on("response", on_response)

        # ---------- 1. home page: Arabic default, RTL ----------
        page.goto(BASE + "/", wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(600)
        check("home: html lang=ar", page.eval_on_selector("html", "e => e.lang") == "ar")
        check("home: dir=rtl", page.eval_on_selector("html", "e => e.dir") == "rtl")
        check("home: brand arabic", page.text_content(".brand-text strong").strip() == "كراود كلاود")
        check("home: 4 service cards", page.locator(".service-card").count() == 4)
        check("home: arabic service name", "الإرشاد الأكاديمي" in page.text_content(".service-card[data-service=academic_advising] .card-head h2"))
        check("home: badge localized عادي", page.text_content("#overallBadge").strip() in ("عادي", "مزدحم", "حمل مرتفع"))
        check("home: fonts loaded (Amiri bold)", page.evaluate("document.fonts.check('bold 16px Amiri', 'ب')"))
        check("home: fonts loaded (Tajawal)", page.evaluate("document.fonts.check('16px Tajawal', 'ب')"))

        # ---------- 2. language toggle → EN ----------
        page.click("#langToggle")
        page.wait_for_timeout(400)
        check("toggle→EN: dir=ltr", page.eval_on_selector("html", "e => e.dir") == "ltr")
        check("toggle→EN: lang=en", page.eval_on_selector("html", "e => e.lang") == "en")
        check("toggle→EN: nav english", page.text_content('.site-nav .nav-link >> nth=0').strip() == "Services")
        check("toggle→EN: service name english", page.text_content('.service-card[data-service=academic_advising] .card-head h2').strip() == "Academic Advising")
        check("toggle→EN: CTA english", "Get a Ticket" in page.text_content(".get-ticket >> nth=0"))

        # ---------- 3. back to AR ----------
        page.click("#langToggle")
        page.wait_for_timeout(400)
        check("toggle→AR: dir=rtl again", page.eval_on_selector("html", "e => e.dir") == "rtl")
        check("toggle→AR: arabic again", page.text_content(".brand-text strong").strip() == "كراود كلاود")

        # ---------- 4. modal open / cancel ----------
        page.click('.service-card[data-service=it_support] .get-ticket')
        page.wait_for_timeout(200)
        check("modal: opens", page.eval_on_selector("#ticketModal", "e => !e.hidden"))
        check("modal: service name arabic", page.text_content("#modalService").strip() == "الدعم التقني")
        page.click("#modalCancel")
        page.wait_for_timeout(150)
        check("modal: cancel closes", page.eval_on_selector("#ticketModal", "e => e.hidden"))

        # ---------- 5. modal open + backdrop close ----------
        page.click('.service-card[data-service=it_support] .get-ticket')
        page.wait_for_timeout(150)
        page.mouse.click(10, 500)  # backdrop
        page.wait_for_timeout(150)
        check("modal: backdrop click closes", page.eval_on_selector("#ticketModal", "e => e.hidden"))

        # ---------- 6. issue a ticket (full flow) ----------
        page.click('.service-card[data-service=it_support] .get-ticket')
        # name-only submit is blocked → validation message
        page.fill("#customerName", "عبدالله")
        page.click("#modalSubmit")
        page.wait_for_timeout(300)
        check("modal: missing student id → arabic validation", "رقمًا جامعيًا" in (page.text_content("#modalError") or ""))
        page.fill("#studentId", "441002357")
        page.click("#modalSubmit")
        page.wait_for_url(re.compile(r"/ticket/IT-\d+"), timeout=8000)
        ticket_no = page.url.rsplit("/", 1)[-1]
        check("ticket: redirected to ticket page", ticket_no.startswith("IT-"))
        check("ticket: big number shown", page.text_content('[data-role="number"]').strip() == ticket_no)
        check("ticket: student id shown", page.text_content('[data-role="student-id"]').strip() == "441002357")
        check("ticket: customer name shown", page.text_content('[data-role="customer"]').strip() == "عبدالله")
        check("ticket: status arabic", page.text_content('[data-role="status"]').strip() == "بانتظار دورك")
        check("ticket: service arabic", page.text_content('[data-role="service-name"]').strip() == "الدعم التقني")
        check("ticket: step1 done", "done" in (page.get_attribute("#stepRequested", "class") or ""))
        check("ticket: eta arabic", "نحو" in page.text_content('[data-role="eta"]'))
        page.screenshot(path=os.path.join(SHOTS_DIR, "ar_ticket.png"), full_page=True)

        # ---------- 6b. duplicate student id → friendly 409 ----------
        page.goto(BASE + "/")
        page.click('.service-card[data-service=it_support] .get-ticket')
        page.fill("#customerName", "عبدالله")
        page.fill("#studentId", "441002357")
        page.click("#modalSubmit")
        page.wait_for_timeout(1600)
        err = page.text_content("#modalError") or ""
        check("modal: duplicate id → arabic 409 message", ticket_no in err and "نشطة" in err)
        page.click("#modalCancel")

        # ---------- 7. language toggle ON ticket page ----------
        page.goto(BASE + "/ticket/" + ticket_no)
        page.click("#langToggle")
        page.wait_for_timeout(500)
        check("ticket: EN status", page.text_content('[data-role="status"]').strip() == "WAITING")
        check("ticket: EN service", page.text_content('[data-role="service-name"]').strip() == "IT Support")
        check("ticket: EN eta (~min)", "~" in page.text_content('[data-role="eta"]'))
        page.click("#langToggle")
        page.wait_for_timeout(500)

        # ---------- 8. queue board link from ticket ----------
        page.click('.ticket-actions .btn-ghost')
        page.wait_for_url("**/queue", timeout=8000)
        check("ticket→queue: nav works", "/queue" in page.url)
        check("queue: title arabic", page.text_content(".page-head h1").strip() == "لوحة الطابور")
        check("queue: our ticket listed", page.locator(f'.queue-card[data-service=it_support] tbody .mono:has-text("{ticket_no}")').count() >= 1)
        check("queue: now-serving shows 0", page.text_content('.queue-card[data-service=it_support] [data-role="serving-count"]').strip() == "0")

        # ---------- 9. staff panel: serve our ticket ----------
        page.click('.site-nav a[href="/admin"]')  # لوحة الموظف
        page.wait_for_url("**/admin", timeout=8000)
        check("admin: title arabic", page.text_content(".page-head h1").strip() == "لوحة الموظف")
        row = page.locator(f'.admin-card[data-service=it_support] tr[data-number="{ticket_no}"]')
        check("admin: our row present", row.count() == 1)
        row.locator(".act-serve").click()
        page.wait_for_timeout(900)
        tk = api(f"/api/tickets/{ticket_no}")["ticket"]
        check("admin: serve button → SERVING in DB", tk["status"] == "SERVING", tk["status"])

        # ---------- 10. complete ----------
        row = page.locator(f'.admin-card[data-service=it_support] tr[data-number="{ticket_no}"]')
        row.locator(".act-complete").click()
        page.wait_for_timeout(900)
        tk = api(f"/api/tickets/{ticket_no}")["ticket"]
        check("admin: complete button → DONE in DB", tk["status"] == "DONE", tk["status"])

        # ---------- 11. call next on empty queue → toast ----------
        page.click('.admin-card[data-service=academic_advising] .call-next')
        page.wait_for_timeout(700)
        body_text = page.text_content("body")
        check("admin: call-next empty → arabic toast", "الطابور فارغ" in body_text)

        # ---------- 12. refresh button ----------
        page.click('.admin-card[data-service=it_support] .refresh-card')
        page.wait_for_timeout(600)
        check("admin: refresh button no error", not errors)

        # ---------- 13. new ticket → call next → now serving ----------
        data = api("/api/tickets", {"service_code": "registration_support", "customer_name": "سارة"})
        t2 = data["ticket"]["ticket_number"]
        check("api: ticket issued", t2.startswith("RS-"), t2)
        page.click('.admin-card[data-service=registration_support] .call-next')
        page.wait_for_timeout(900)
        tk2 = api(f"/api/tickets/{t2}")["ticket"]
        check("admin: call-next → SERVING + toast", tk2["status"] == "SERVING", tk2["status"])
        body_text = page.text_content("body")
        check("admin: now-serving toast arabic", f"قيد النداء الآن: {t2}" in body_text)

        # ---------- 14. cancel from admin ----------
        data = api("/api/tickets", {"service_code": "student_services", "customer_name": "محمد"})
        t3 = data["ticket"]["ticket_number"]
        page.click('.admin-card[data-service=student_services] .refresh-card')  # force re-render
        page.wait_for_timeout(1000)
        page.wait_for_selector(f'.admin-card[data-service=student_services] tr[data-number="{t3}"]', timeout=8000)
        row3 = page.locator(f'.admin-card[data-service=student_services] tr[data-number="{t3}"]')
        check("admin: new ticket row rendered", row3.count() == 1)
        row3.locator(".act-cancel").click()
        page.wait_for_timeout(900)
        tk3 = api(f"/api/tickets/{t3}")["ticket"]
        check("admin: cancel button → CANCELLED in DB", tk3["status"] == "CANCELLED", tk3["status"])

        # ---------- 15. cancel from ticket page ----------
        data = api("/api/tickets", {"service_code": "academic_advising", "customer_name": "ليلى"})
        t4 = data["ticket"]["ticket_number"]
        page.goto(f"{BASE}/ticket/{t4}", wait_until="networkidle")
        check("ticket4: status WAITING", page.text_content('[data-role="status"]').strip() == "بانتظار دورك")
        page.click("#cancelBtn")
        page.wait_for_timeout(900)
        tk4 = api(f"/api/tickets/{t4}")["ticket"]
        check("ticket page: cancel button → CANCELLED", tk4["status"] == "CANCELLED", tk4["status"])
        check("ticket page: cancel hides button", page.eval_on_selector("#cancelBtn", "e => e.hidden"))
        check("ticket page: status updated live", page.text_content('[data-role="status"]').strip() == "أُلغيت التذكرة")

        # ---------- 16. nav home + 404 + back ----------
        page.click('.back-link')
        page.wait_for_url(BASE + "/", timeout=8000)
        check("ticket→home: back link works", page.url.rstrip("/") == BASE)
        page.goto(BASE + "/ticket/NOPE-999", wait_until="networkidle")
        check("404: arabic not-found page", page.text_content(".page-head h1").strip() == "التذكرة غير موجودة")
        page.click('.page-head .btn-primary')
        page.wait_for_url(BASE + "/", timeout=8000)
        check("404: back-to-services works", page.url.rstrip("/") == BASE)

        # ---------- 17. full EN pass over all pages ----------
        page.click("#langToggle")
        page.wait_for_timeout(300)
        check("EN: home title", "Campus services" in page.text_content(".hero-text h1"))
        page.goto(BASE + "/queue", wait_until="networkidle")
        page.wait_for_timeout(300)
        check("EN: queue board ltr", page.eval_on_selector("html", "e => e.dir") == "ltr")
        check("EN: queue persists (localStorage)", page.text_content(".page-head h1").strip() == "Queue Board")
        page.goto(BASE + "/admin", wait_until="networkidle")
        page.wait_for_timeout(300)
        check("EN: admin persists", page.text_content(".page-head h1").strip() == "Staff Panel")
        check("EN: call next label", page.text_content('.admin-card[data-service=it_support] .call-next').strip().endswith("Call Next"))

        # ---------- 18. page errors ----------
        check("zero JS page errors", not errors, "; ".join(errors[:3]))
        real_console = [e for e in console_errors
                        if "favicon" not in e.lower()
                        and "not found" not in e.lower()
                        and "409" not in e.lower()]  # 404 nav + intentional 409 dup are expected (case-insensitive)
        check("zero console errors", not real_console, "; ".join(real_console[:3]))
        check("zero failed sub-resources", not failed_resources, "; ".join(failed_resources[:3]))

        browser.close()

    api("/api/demo/reset", {})  # leave a clean state for the user
    fails = [r for r in RESULTS if not r[1]]
    print(f"\n===== {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS =====")
    if fails:
        print("FAILED:")
        for name, _, extra in fails:
            print(f"  - {name} ({extra})")
        sys.exit(1)


if __name__ == "__main__":
    run()
