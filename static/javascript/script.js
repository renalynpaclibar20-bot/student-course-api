const API_BASE = window.API_BASE || ""; // set to your deployed Flask URL if the frontend is hosted elsewhere
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opt = {}) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    method: opt.method || "GET",
    body: opt.body ? JSON.stringify(opt.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed.");
  return data;
}

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (error ? " error" : "");
  setTimeout(() => (t.className = ""), 2600);
}

const NAV = [["index", "/", "Dashboard"], ["students", "/students", "Students"], ["courses", "/courses", "Courses"],
  ["enrollments", "/enrollment", "Enrollments"], ["announcements", "/announcements", "Announcements"]];

function shell(page) {
  $("#sidebar").innerHTML = `
    <div class="brand"><b>Campus Connect</b><span>STUDENT INFORMATION</span></div>
    <nav class="nav">${NAV.map(([k, h, l]) => `<a href="${h}" class="${k === page ? "active" : ""}">${l}</a>`).join("")}</nav>
    <div class="backend"><small>BACKEND</small><i id="dot"></i><span id="status">Checking API…</span></div>`;
}

const PAGES = {
  students: { ep: "/students", noun: "student", cols: [["name", "Name"], ["email", "Email"], ["program", "Program"]],
    fields: [["name", "Full name"], ["email", "Email", "email"], ["program", "Program", "select", ["BSIT", "BSCS", "BSIS"]]] },
  courses: { ep: "/courses", noun: "course", cols: [["code", "Code"], ["title", "Title"], ["department", "Department"], ["enrolled", "Enrolled"], ["capacity", "Capacity"]],
    fields: [["code", "Course code"], ["title", "Title"], ["department", "Department"], ["capacity", "Capacity", "number"]] },
  enrollments: { ep: "/enrollments", noun: "enrollment", cols: [["student", "Student"], ["course", "Course"], ["semester", "Semester"]],
    fields: [["student_id", "Student", "select", "/students"], ["course_id", "Course", "select", "/courses"],
      ["semester", "Semester", "select", ["First Semester", "Second Semester", "Summer"]]] },
  announcements: { ep: "/announcements", noun: "announcement", cols: [["title", "Title"], ["body", "Message"], ["created_at", "Posted"]],
    fields: [["title", "Title"], ["body", "Message", "textarea"]] },
};

async function fieldHTML([name, label, type = "text", opts]) {
  let input;
  if (type === "select") {
    const list = typeof opts === "string" ? await api(opts) : opts;
    input = `<select name="${name}" required>${list.map((o) =>
      typeof o === "string" ? `<option>${esc(o)}</option>`
        : `<option value="${o.id}">${esc(o.name || `${o.code} - ${o.title}`)}</option>`).join("")}</select>`;
  } else if (type === "textarea") input = `<textarea name="${name}" required></textarea>`;
  else input = `<input name="${name}" type="${type}" ${name === "capacity" ? 'value="35" min="1"' : "required"}>`;
  return `<label>${label}${input}</label>`;
}

async function renderCrud(page) {
  const cfg = PAGES[page];
  const box = $("#content");
  box.innerHTML = `<div class="skeleton"></div>`;
  const fields = (await Promise.all(cfg.fields.map(fieldHTML))).join("");
  box.innerHTML = `
    <form class="card" id="form">${fields}<button class="btn" type="submit">Add ${cfg.noun}</button></form>
    <div class="tools"><input id="q" placeholder="Search ${cfg.noun}s" aria-label="Search"></div>
    <div class="table-wrap"><table><thead><tr>${cfg.cols.map(([, l]) => `<th>${l}</th>`).join("")}<th></th></tr></thead>
    <tbody id="rows"></tbody></table></div>`;
  let data = [];
  const draw = () => {
    const q = $("#q").value.toLowerCase();
    const list = data.filter((r) => JSON.stringify(r).toLowerCase().includes(q));
    $("#rows").innerHTML = list.length
      ? list.map((r) => `<tr>${cfg.cols.map(([k]) => `<td>${esc(r[k])}</td>`).join("")}
          <td><button class="btn ghost" data-id="${r.id}">Delete</button></td></tr>`).join("")
      : `<tr><td class="empty" colspan="${cfg.cols.length + 1}">No ${cfg.noun}s yet. Add one above.</td></tr>`;
  };
  const load = async () => { data = await api(cfg.ep); draw(); };
  $("#q").oninput = draw;
  $("#rows").onclick = async (e) => {
    const id = e.target.dataset.id;
    if (!id || !confirm(`Delete this ${cfg.noun}?`)) return;
    try { await api(`${cfg.ep}/${id}`, { method: "DELETE" }); toast("Deleted"); load(); } catch (err) { toast(err.message, true); }
  };
  $("#form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api(cfg.ep, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
      toast(`${cfg.noun[0].toUpperCase() + cfg.noun.slice(1)} added`);
      e.target.reset(); load();
    } catch (err) { toast(err.message, true); }
  };
  await load();
}

async function renderDashboard() {
  const box = $("#content");
  box.innerHTML = `<div class="stats"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>`;
  const [s, enr, ann] = await Promise.all([api("/stats"), api("/enrollments"), api("/announcements")]);
  const card = (t, n, a, al, b, bl) => `<div class="stat"><h3>${t}</h3><span class="dots"></span>
    <div class="row"><span class="num">${n}</span><div class="meta"><div>${al}<b>${a}</b></div><div>${bl}<b>${b}</b></div></div></div></div>`;
  box.innerHTML = `
    <div class="stats">
      ${card("Total students", s.students, s.programs, "Programs", "Active", "Records")}
      ${card("Total courses", s.courses, s.departments, "Departments", s.capacity + " each", "Capacity")}
      ${card("Total enrollments", s.enrollments, "Live", "Status", "Current", "Term")}
      ${card("Available courses", s.available, s.courses - s.available, "Full", s.courses, "Offered")}
    </div>
    <div class="grid2">
      <div class="card"><h3>Enrollment activity</h3><ul class="list">${enr.slice(0, 5).map((e) =>
        `<li>${esc(e.student)}<small>${esc(e.course)} · ${esc(e.semester)}</small></li>`).join("") || "<li>No enrollments yet.</li>"}</ul></div>
      <div class="card"><h3>Announcements</h3><ul class="list">${ann.slice(0, 4).map((a) =>
        `<li>${esc(a.title)}<small>${esc(a.body)}</small></li>`).join("") || "<li>No announcements yet.</li>"}</ul></div>
    </div>
    <div class="shortcuts"><a href="/students">Add student</a><a href="/courses">Add course</a>
      <a href="/enrollment">New enrollment</a><a href="/announcements">Post announcement</a></div>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.dataset.page;
  shell(page);
  try {
    await api("/stats");
    $("#dot").classList.add("on");
    $("#status").textContent = "API connected";
    page === "index" ? await renderDashboard() : await renderCrud(page);
  } catch (err) {
    $("#status").textContent = "API offline";
    $("#content").innerHTML = `<div class="notice error">Can't reach the Flask API. Check that the server is running${API_BASE ? ` at ${esc(API_BASE)}` : ""}.</div>`;
  }
});
