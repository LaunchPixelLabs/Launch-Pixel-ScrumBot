import { ACTIVE_COLUMNS, COLUMNS } from "./board";

export function renderBoardHtml(): string {
  const activeColumns = JSON.stringify(ACTIVE_COLUMNS);
  const allColumns = JSON.stringify(COLUMNS);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LaunchPixel DevOps Board</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f2f1;
      --surface: #ffffff;
      --surface-strong: #fbfbfb;
      --line: #d2d0ce;
      --line-strong: #a19f9d;
      --text: #201f1e;
      --muted: #605e5c;
      --faint: #8a8886;
      --blue: #0078d4;
      --blue-strong: #106ebe;
      --green: #107c10;
      --teal: #008575;
      --orange: #ca5010;
      --red: #d13438;
      --purple: #5c2d91;
      --shadow: 0 10px 28px rgba(0, 0, 0, 0.13);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      height: 100%;
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }

    body {
      overflow: hidden;
    }

    button,
    input,
    select,
    textarea {
      font: inherit;
    }

    button {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 4px;
      min-height: 34px;
      padding: 0 12px;
      cursor: pointer;
    }

    button:hover {
      border-color: var(--line-strong);
      background: #f8f8f8;
    }

    button.primary {
      border-color: var(--blue);
      background: var(--blue);
      color: #fff;
      font-weight: 600;
    }

    button.primary:hover {
      background: var(--blue-strong);
    }

    button.ghost {
      border-color: transparent;
      background: transparent;
    }

    button.danger {
      border-color: var(--red);
      color: var(--red);
      background: #fff5f5;
    }

    .app {
      display: grid;
      grid-template-rows: auto auto 1fr;
      height: 100%;
      min-width: 320px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 56px;
      padding: 10px 18px;
      background: #242424;
      color: #fff;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .brand-mark {
      display: grid;
      place-items: center;
      width: 32px;
      height: 32px;
      border-radius: 4px;
      background: var(--blue);
      font-weight: 800;
      letter-spacing: 0;
    }

    .brand-copy {
      min-width: 0;
    }

    .brand-title {
      margin: 0;
      font-size: 16px;
      line-height: 20px;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .brand-subtitle {
      margin: 0;
      color: #c8c6c4;
      font-size: 12px;
      line-height: 16px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .top-actions button {
      min-width: 40px;
    }

    .top-actions .secondary {
      background: #323130;
      color: #fff;
      border-color: #484644;
    }

    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1.3fr) repeat(3, minmax(140px, 0.6fr)) auto;
      gap: 10px;
      align-items: center;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .field {
      display: grid;
      gap: 4px;
      min-width: 0;
    }

    .field span {
      font-size: 11px;
      line-height: 14px;
      color: var(--muted);
      font-weight: 600;
    }

    .field input,
    .field select,
    .field textarea {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #fff;
      color: var(--text);
      padding: 7px 9px;
      outline: none;
    }

    .field input:focus,
    .field select:focus,
    .field textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 1px var(--blue);
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(112px, 1fr));
      gap: 8px;
      padding: 12px 18px 0;
    }

    .metric {
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: 4px;
      padding: 10px 12px;
      min-width: 0;
    }

    .metric strong {
      display: block;
      font-size: 22px;
      line-height: 26px;
      font-weight: 700;
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      margin-top: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .board-shell {
      min-height: 0;
      padding: 12px 18px 18px;
      overflow: auto;
    }

    .board {
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(286px, 1fr);
      gap: 12px;
      align-items: stretch;
      min-height: 100%;
      min-width: 1120px;
    }

    .lane {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #edebe9;
      overflow: hidden;
    }

    .lane.drop-target {
      border-color: var(--blue);
      box-shadow: inset 0 0 0 2px var(--blue);
    }

    .lane.over-limit .lane-header {
      background: #fff4ce;
    }

    .lane-header {
      display: grid;
      gap: 8px;
      padding: 10px 10px 9px;
      border-bottom: 1px solid var(--line);
      background: var(--surface-strong);
    }

    .lane-topline {
      height: 3px;
      border-radius: 999px;
      background: var(--line-strong);
    }

    .lane[data-status="New"] .lane-topline { background: var(--faint); }
    .lane[data-status="Planned"] .lane-topline { background: var(--blue); }
    .lane[data-status="Refining"] .lane-topline { background: var(--orange); }
    .lane[data-status="Active"] .lane-topline { background: var(--green); }
    .lane[data-status="Reviewing"] .lane-topline { background: var(--teal); }
    .lane[data-status="Blocked"] .lane-topline { background: var(--red); }

    .lane-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-width: 0;
    }

    .lane-title h2 {
      margin: 0;
      font-size: 14px;
      line-height: 18px;
      font-weight: 700;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .lane-count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 34px;
      height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      background: #e1dfdd;
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .lane-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      min-height: 16px;
    }

    .cards {
      min-height: 120px;
      overflow: auto;
      padding: 8px;
    }

    .card {
      position: relative;
      display: grid;
      gap: 8px;
      width: 100%;
      margin: 0 0 8px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--line-strong);
      border-radius: 4px;
      background: var(--surface);
      padding: 10px;
      box-shadow: 0 1px 1px rgba(0, 0, 0, 0.04);
      cursor: grab;
    }

    .card:hover {
      border-color: var(--line-strong);
      box-shadow: 0 3px 10px rgba(0, 0, 0, 0.09);
    }

    .card.dragging {
      opacity: 0.5;
    }

    .card.priority-critical { border-left-color: var(--red); }
    .card.priority-high { border-left-color: var(--orange); }
    .card.priority-medium { border-left-color: var(--blue); }
    .card.priority-low { border-left-color: var(--green); }

    .card-kicker {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      min-width: 0;
    }

    .card-id {
      font-weight: 700;
      color: var(--blue-strong);
      white-space: nowrap;
    }

    .card-title {
      margin: 0;
      font-size: 14px;
      line-height: 18px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }

    .card-description {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 0;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      min-height: 22px;
      border: 1px solid #e1dfdd;
      border-radius: 999px;
      background: #faf9f8;
      color: var(--muted);
      font-size: 11px;
      line-height: 14px;
      padding: 3px 7px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .badge.red {
      border-color: #f3b0b3;
      background: #fff5f5;
      color: var(--red);
    }

    .card-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
    }

    .thread-link {
      color: var(--blue-strong);
      text-decoration: none;
      font-weight: 600;
      white-space: nowrap;
    }

    .thread-link:hover {
      text-decoration: underline;
    }

    .empty {
      display: grid;
      place-items: center;
      min-height: 120px;
      border: 1px dashed var(--line-strong);
      border-radius: 4px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
      padding: 16px;
      background: rgba(255, 255, 255, 0.45);
    }

    .scrim {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.28);
      opacity: 0;
      pointer-events: none;
      transition: opacity 160ms ease;
      z-index: 20;
    }

    .scrim.open {
      opacity: 1;
      pointer-events: auto;
    }

    .drawer {
      position: fixed;
      top: 0;
      right: 0;
      z-index: 30;
      display: grid;
      grid-template-rows: auto 1fr auto;
      width: min(480px, 100vw);
      height: 100%;
      background: var(--surface);
      box-shadow: var(--shadow);
      transform: translateX(102%);
      transition: transform 180ms ease;
    }

    .drawer.open {
      transform: translateX(0);
    }

    .drawer-header,
    .drawer-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .drawer-footer {
      justify-content: flex-end;
      border-top: 1px solid var(--line);
      border-bottom: 0;
    }

    .drawer-title {
      min-width: 0;
    }

    .drawer-title h2 {
      margin: 0;
      font-size: 18px;
      line-height: 22px;
    }

    .drawer-title p {
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 16px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .drawer-body {
      min-height: 0;
      overflow: auto;
      padding: 16px;
    }

    .form-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .form-grid .wide {
      grid-column: 1 / -1;
    }

    textarea {
      min-height: 128px;
      resize: vertical;
    }

    .notice {
      position: fixed;
      left: 50%;
      bottom: 18px;
      z-index: 40;
      max-width: min(560px, calc(100vw - 24px));
      transform: translateX(-50%) translateY(16px);
      opacity: 0;
      pointer-events: none;
      border-radius: 4px;
      background: #323130;
      color: #fff;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 18px;
      box-shadow: var(--shadow);
      transition: opacity 160ms ease, transform 160ms ease;
    }

    .notice.open {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }

    .sync-state {
      color: #c8c6c4;
      font-size: 12px;
      line-height: 16px;
      white-space: nowrap;
    }

    @media (max-width: 980px) {
      body {
        overflow: auto;
      }

      .app {
        min-height: 100%;
        height: auto;
      }

      .toolbar {
        grid-template-columns: 1fr 1fr;
      }

      .toolbar .primary {
        grid-column: 1 / -1;
      }

      .metrics {
        grid-template-columns: 1fr 1fr;
      }

      .board-shell {
        min-height: 620px;
      }

      .board {
        grid-auto-columns: minmax(280px, 84vw);
        min-width: 0;
      }
    }

    @media (max-width: 620px) {
      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }

      .top-actions {
        width: 100%;
        justify-content: flex-start;
      }

      .toolbar,
      .metrics,
      .form-grid {
        grid-template-columns: 1fr;
      }

      .drawer {
        width: 100vw;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">LP</div>
        <div class="brand-copy">
          <h1 class="brand-title">LaunchPixel DevOps Board</h1>
          <p class="brand-subtitle">Discord-connected sprint execution</p>
        </div>
      </div>
      <div class="top-actions">
        <span id="syncState" class="sync-state">Loading board</span>
        <button id="refreshBtn" class="secondary" type="button" title="Refresh board">Refresh</button>
        <button id="newBtn" class="primary" type="button" title="Create work item">+ New item</button>
      </div>
    </header>

    <section class="toolbar" aria-label="Board filters">
      <label class="field">
        <span>Search</span>
        <input id="searchInput" type="search" placeholder="Search id, title, owner, labels" autocomplete="off" />
      </label>
      <label class="field">
        <span>Status</span>
        <select id="statusFilter">
          <option value="all">All active lanes</option>
        </select>
      </label>
      <label class="field">
        <span>Owner</span>
        <select id="ownerFilter">
          <option value="all">All owners</option>
        </select>
      </label>
      <label class="field">
        <span>Priority</span>
        <select id="priorityFilter">
          <option value="all">All priorities</option>
          <option value="Critical">Critical</option>
          <option value="High">High</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
        </select>
      </label>
      <button id="clearBtn" type="button">Clear filters</button>
    </section>

    <main class="board-shell">
      <section id="metrics" class="metrics" aria-label="Board metrics"></section>
      <section id="board" class="board" aria-label="Kanban lanes"></section>
    </main>
  </div>

  <div id="scrim" class="scrim"></div>
  <aside id="drawer" class="drawer" aria-hidden="true">
    <div class="drawer-header">
      <div class="drawer-title">
        <h2 id="drawerTitle">Work item</h2>
        <p id="drawerSubtitle">Create or update LaunchPixel execution work</p>
      </div>
      <button id="closeDrawerBtn" class="ghost" type="button" title="Close panel">Close</button>
    </div>
    <form id="ticketForm">
      <div class="drawer-body">
        <input id="ticketId" name="id" type="hidden" />
        <div class="form-grid">
          <label class="field wide">
            <span>Title</span>
            <input id="titleInput" name="title" required maxlength="180" placeholder="Ship onboarding fixes" />
          </label>
          <label class="field wide">
            <span>Description</span>
            <textarea id="descriptionInput" name="description" maxlength="2800" placeholder="Scope, acceptance criteria, notes"></textarea>
          </label>
          <label class="field">
            <span>Status</span>
            <select id="statusInput" name="status"></select>
          </label>
          <label class="field">
            <span>Priority</span>
            <select id="priorityInput" name="priority">
              <option>Low</option>
              <option selected>Medium</option>
              <option>High</option>
              <option>Critical</option>
            </select>
          </label>
          <label class="field">
            <span>Owner</span>
            <input id="ownerInput" name="assignee_name" maxlength="80" placeholder="Owner name" />
          </label>
          <label class="field">
            <span>Story points</span>
            <input id="pointsInput" name="story_points" type="number" min="0" max="99" step="1" value="1" />
          </label>
          <label class="field">
            <span>Due date</span>
            <input id="dueInput" name="end_date" type="date" />
          </label>
          <label class="field">
            <span>Labels</span>
            <input id="labelsInput" name="labels" maxlength="240" placeholder="frontend, urgent" />
          </label>
          <div class="field wide">
            <span>Discord thread</span>
            <a id="threadLink" class="thread-link" href="#" target="_blank" rel="noreferrer">No Discord thread yet</a>
          </div>
        </div>
      </div>
      <div class="drawer-footer">
        <button id="closeTicketBtn" class="danger" type="button">Close work item</button>
        <button type="button" id="cancelBtn">Cancel</button>
        <button class="primary" type="submit">Save item</button>
      </div>
    </form>
  </aside>
  <div id="notice" class="notice"></div>

  <script>
    (function () {
      var ACTIVE_COLUMNS = ${activeColumns};
      var ALL_COLUMNS = ${allColumns};
      var PRIORITIES = ["Critical", "High", "Medium", "Low"];
      var state = {
        tickets: [],
        wipLimits: {},
        guildId: "",
        query: "",
        status: "all",
        owner: "all",
        priority: "all",
        draggingId: "",
        saving: false
      };
      var els = {};
      var noticeTimer = 0;

      document.addEventListener("DOMContentLoaded", init);

      function init() {
        els.board = document.getElementById("board");
        els.metrics = document.getElementById("metrics");
        els.syncState = document.getElementById("syncState");
        els.search = document.getElementById("searchInput");
        els.statusFilter = document.getElementById("statusFilter");
        els.ownerFilter = document.getElementById("ownerFilter");
        els.priorityFilter = document.getElementById("priorityFilter");
        els.clear = document.getElementById("clearBtn");
        els.refresh = document.getElementById("refreshBtn");
        els.newBtn = document.getElementById("newBtn");
        els.drawer = document.getElementById("drawer");
        els.scrim = document.getElementById("scrim");
        els.closeDrawer = document.getElementById("closeDrawerBtn");
        els.cancel = document.getElementById("cancelBtn");
        els.form = document.getElementById("ticketForm");
        els.ticketId = document.getElementById("ticketId");
        els.drawerTitle = document.getElementById("drawerTitle");
        els.drawerSubtitle = document.getElementById("drawerSubtitle");
        els.title = document.getElementById("titleInput");
        els.description = document.getElementById("descriptionInput");
        els.statusInput = document.getElementById("statusInput");
        els.priorityInput = document.getElementById("priorityInput");
        els.ownerInput = document.getElementById("ownerInput");
        els.pointsInput = document.getElementById("pointsInput");
        els.dueInput = document.getElementById("dueInput");
        els.labelsInput = document.getElementById("labelsInput");
        els.threadLink = document.getElementById("threadLink");
        els.closeTicket = document.getElementById("closeTicketBtn");
        els.notice = document.getElementById("notice");

        hydrateToken();
        fillStatusControls();
        bindEvents();
        loadBoard();
      }

      function hydrateToken() {
        var token = new URLSearchParams(window.location.search).get("token");
        if (token) localStorage.setItem("lp_board_token", token);
      }

      function bindEvents() {
        els.search.addEventListener("input", function () {
          state.query = els.search.value.trim().toLowerCase();
          render();
        });
        els.statusFilter.addEventListener("change", function () {
          state.status = els.statusFilter.value;
          render();
        });
        els.ownerFilter.addEventListener("change", function () {
          state.owner = els.ownerFilter.value;
          render();
        });
        els.priorityFilter.addEventListener("change", function () {
          state.priority = els.priorityFilter.value;
          render();
        });
        els.clear.addEventListener("click", function () {
          state.query = "";
          state.status = "all";
          state.owner = "all";
          state.priority = "all";
          els.search.value = "";
          els.statusFilter.value = "all";
          els.ownerFilter.value = "all";
          els.priorityFilter.value = "all";
          render();
        });
        els.refresh.addEventListener("click", loadBoard);
        els.newBtn.addEventListener("click", openNewTicket);
        els.scrim.addEventListener("click", closeDrawer);
        els.closeDrawer.addEventListener("click", closeDrawer);
        els.cancel.addEventListener("click", closeDrawer);
        els.form.addEventListener("submit", saveTicket);
        els.closeTicket.addEventListener("click", closeSelectedTicket);
        document.addEventListener("keydown", function (event) {
          if (event.key === "Escape") closeDrawer();
        });
      }

      function fillStatusControls() {
        ACTIVE_COLUMNS.forEach(function (column) {
          els.statusFilter.appendChild(option(column, column));
        });
        ALL_COLUMNS.forEach(function (column) {
          els.statusInput.appendChild(option(column, column));
        });
      }

      function option(value, label) {
        var opt = document.createElement("option");
        opt.value = value;
        opt.textContent = label;
        return opt;
      }

      async function loadBoard() {
        setSync("Loading board");
        try {
          var data = await api("/api/board");
          state.tickets = Array.isArray(data.tickets) ? data.tickets : [];
          state.wipLimits = data.wipLimits || {};
          state.guildId = data.discord && data.discord.guildId ? String(data.discord.guildId) : "";
          setSync("Synced " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
          render();
        } catch (err) {
          setSync("Sync failed");
          showNotice(err.message || "Could not load board");
        }
      }

      async function api(path, options) {
        var headers = { "Accept": "application/json" };
        var token = localStorage.getItem("lp_board_token") || "";
        if (token) headers["X-Board-Token"] = token;
        if (options && options.body) headers["Content-Type"] = "application/json";
        var res = await fetch(path, Object.assign({}, options || {}, { headers: Object.assign(headers, (options && options.headers) || {}) }));
        if (!res.ok) {
          var text = await res.text();
          var parsed = null;
          try { parsed = JSON.parse(text); } catch (_) {}
          throw new Error((parsed && (parsed.error || parsed.message)) || text || ("HTTP " + res.status));
        }
        if (res.status === 204) return {};
        return res.json();
      }

      function setSync(text) {
        els.syncState.textContent = text;
      }

      function render() {
        updateOwnerOptions();
        renderMetrics();
        renderBoard();
      }

      function updateOwnerOptions() {
        var previous = els.ownerFilter.value || state.owner;
        var owners = state.tickets
          .map(function (ticket) { return String(ticket.assignee_name || "").trim(); })
          .filter(Boolean)
          .sort(function (a, b) { return a.localeCompare(b); });
        owners = owners.filter(function (owner, index) { return owners.indexOf(owner) === index; });
        els.ownerFilter.textContent = "";
        els.ownerFilter.appendChild(option("all", "All owners"));
        owners.forEach(function (owner) { els.ownerFilter.appendChild(option(owner, owner)); });
        els.ownerFilter.value = owners.indexOf(previous) >= 0 ? previous : "all";
        state.owner = els.ownerFilter.value;
      }

      function renderMetrics() {
        var visible = filteredTickets();
        var blocked = state.tickets.filter(function (t) { return t.status === "Blocked"; }).length;
        var points = state.tickets.reduce(function (sum, t) { return sum + (Number(t.story_points) || 0); }, 0);
        var overdue = state.tickets.filter(isOverdue).length;
        els.metrics.textContent = "";
        [
          ["Active items", visible.length, "visible on current filters"],
          ["Story points", points, "open delivery load"],
          ["Blocked", blocked, "needs owner attention"],
          ["Overdue", overdue, "past due date"]
        ].forEach(function (item) {
          var metric = el("article", "metric");
          metric.appendChild(el("strong", "", String(item[1])));
          metric.appendChild(el("span", "", item[2]));
          els.metrics.appendChild(metric);
        });
      }

      function renderBoard() {
        els.board.textContent = "";
        var visible = filteredTickets();
        var columns = state.status === "all" ? ACTIVE_COLUMNS : [state.status];
        columns.forEach(function (column) {
          var laneTickets = visible.filter(function (ticket) { return ticket.status === column; });
          var limit = Number(state.wipLimits[column] || 0);
          var lane = el("section", "lane");
          lane.dataset.status = column;
          if (limit && laneTickets.length > limit) lane.classList.add("over-limit");
          lane.addEventListener("dragover", function (event) {
            event.preventDefault();
            lane.classList.add("drop-target");
          });
          lane.addEventListener("dragleave", function () {
            lane.classList.remove("drop-target");
          });
          lane.addEventListener("drop", function (event) {
            event.preventDefault();
            lane.classList.remove("drop-target");
            if (state.draggingId) moveTicket(state.draggingId, column);
          });

          var header = el("header", "lane-header");
          header.appendChild(el("div", "lane-topline"));
          var titleRow = el("div", "lane-title");
          titleRow.appendChild(el("h2", "", column));
          titleRow.appendChild(el("span", "lane-count", laneTickets.length + (limit ? "/" + limit : "")));
          header.appendChild(titleRow);
          var meta = el("div", "lane-meta");
          meta.appendChild(el("span", "", laneTickets.reduce(function (sum, t) { return sum + (Number(t.story_points) || 0); }, 0) + " SP"));
          meta.appendChild(el("span", "", limit && laneTickets.length > limit ? "Over WIP" : "WIP OK"));
          header.appendChild(meta);

          var cards = el("div", "cards");
          if (!laneTickets.length) {
            cards.appendChild(el("div", "empty", column === "Blocked" ? "No blockers" : "Drop work here"));
          } else {
            laneTickets.forEach(function (ticket) {
              cards.appendChild(renderCard(ticket));
            });
          }
          lane.appendChild(header);
          lane.appendChild(cards);
          els.board.appendChild(lane);
        });
      }

      function filteredTickets() {
        return state.tickets.filter(function (ticket) {
          if (state.status !== "all" && ticket.status !== state.status) return false;
          if (state.owner !== "all" && String(ticket.assignee_name || "") !== state.owner) return false;
          if (state.priority !== "all" && String(ticket.priority || "Medium") !== state.priority) return false;
          if (!state.query) return true;
          var haystack = [
            ticket.id,
            ticket.title,
            ticket.description,
            ticket.assignee_name,
            ticket.priority,
            ticket.labels
          ].join(" ").toLowerCase();
          return haystack.indexOf(state.query) >= 0;
        });
      }

      function renderCard(ticket) {
        var card = el("article", "card priority-" + String(ticket.priority || "Medium").toLowerCase());
        card.draggable = true;
        card.dataset.id = ticket.id;
        card.addEventListener("dragstart", function () {
          state.draggingId = ticket.id;
          card.classList.add("dragging");
        });
        card.addEventListener("dragend", function () {
          state.draggingId = "";
          card.classList.remove("dragging");
        });
        card.addEventListener("click", function () {
          openExistingTicket(ticket.id);
        });

        var kicker = el("div", "card-kicker");
        kicker.appendChild(el("span", "card-id", ticket.id || ""));
        kicker.appendChild(el("span", "", String(ticket.priority || "Medium")));
        card.appendChild(kicker);
        card.appendChild(el("h3", "card-title", ticket.title || "Untitled"));
        if (ticket.description) card.appendChild(el("p", "card-description", ticket.description));

        var badges = el("div", "badges");
        badges.appendChild(el("span", "badge", ownerText(ticket)));
        badges.appendChild(el("span", "badge", (Number(ticket.story_points) || 1) + " SP"));
        if (ticket.end_date) badges.appendChild(el("span", isOverdue(ticket) ? "badge red" : "badge", "Due " + shortDate(ticket.end_date)));
        labelList(ticket.labels).forEach(function (label) {
          badges.appendChild(el("span", "badge", label));
        });
        card.appendChild(badges);

        var footer = el("footer", "card-footer");
        footer.appendChild(el("span", "", shortDate(ticket.updated_at || ticket.created_at || "")));
        var link = threadUrl(ticket);
        if (link) {
          var a = el("a", "thread-link", "Thread");
          a.href = link;
          a.target = "_blank";
          a.rel = "noreferrer";
          a.addEventListener("click", function (event) { event.stopPropagation(); });
          footer.appendChild(a);
        } else {
          footer.appendChild(el("span", "", "No thread"));
        }
        card.appendChild(footer);
        return card;
      }

      function ownerText(ticket) {
        return ticket.assignee_name ? String(ticket.assignee_name) : "Unassigned";
      }

      function labelList(labels) {
        return String(labels || "")
          .split(",")
          .map(function (label) { return label.trim(); })
          .filter(Boolean)
          .slice(0, 6);
      }

      function openNewTicket() {
        els.form.reset();
        els.ticketId.value = "";
        els.drawerTitle.textContent = "New work item";
        els.drawerSubtitle.textContent = "Create a synced Discord board card";
        els.statusInput.value = "New";
        els.priorityInput.value = "Medium";
        els.pointsInput.value = "1";
        els.threadLink.textContent = "No Discord thread yet";
        els.threadLink.removeAttribute("href");
        els.closeTicket.style.display = "none";
        openDrawer();
      }

      function openExistingTicket(id) {
        var ticket = state.tickets.find(function (item) { return item.id === id; });
        if (!ticket) return;
        els.form.reset();
        els.ticketId.value = ticket.id || "";
        els.drawerTitle.textContent = ticket.id || "Work item";
        els.drawerSubtitle.textContent = ticket.title || "Edit work item";
        els.title.value = ticket.title || "";
        els.description.value = ticket.description || "";
        els.statusInput.value = ticket.status || "New";
        els.priorityInput.value = ticket.priority || "Medium";
        els.ownerInput.value = ticket.assignee_name || "";
        els.pointsInput.value = String(Number(ticket.story_points) || 1);
        els.dueInput.value = ticket.end_date ? shortDate(ticket.end_date) : "";
        els.labelsInput.value = ticket.labels || "";
        var link = threadUrl(ticket);
        if (link) {
          els.threadLink.href = link;
          els.threadLink.textContent = "Open Discord thread";
        } else {
          els.threadLink.textContent = "No Discord thread yet";
          els.threadLink.removeAttribute("href");
        }
        els.closeTicket.style.display = "";
        openDrawer();
      }

      function openDrawer() {
        els.drawer.classList.add("open");
        els.scrim.classList.add("open");
        els.drawer.setAttribute("aria-hidden", "false");
        setTimeout(function () { els.title.focus(); }, 0);
      }

      function closeDrawer() {
        els.drawer.classList.remove("open");
        els.scrim.classList.remove("open");
        els.drawer.setAttribute("aria-hidden", "true");
      }

      async function saveTicket(event) {
        event.preventDefault();
        if (state.saving) return;
        var id = els.ticketId.value.trim();
        var payload = readForm();
        if (!payload.title) {
          showNotice("Title is required");
          return;
        }
        state.saving = true;
        setSync("Saving");
        try {
          var result;
          if (id) {
            result = await api("/api/tickets/" + encodeURIComponent(id), { method: "PATCH", body: JSON.stringify(payload) });
          } else {
            result = await api("/api/tickets", { method: "POST", body: JSON.stringify(payload) });
          }
          upsertLocalTicket(result.ticket);
          closeDrawer();
          render();
          setSync("Saved " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
          showNotice(id ? "Work item updated" : "Work item created");
        } catch (err) {
          setSync("Save failed");
          showNotice(err.message || "Could not save item");
        } finally {
          state.saving = false;
        }
      }

      async function closeSelectedTicket() {
        var id = els.ticketId.value.trim();
        if (!id || state.saving) return;
        els.statusInput.value = "Closed";
        await saveTicket({ preventDefault: function () {} });
      }

      function readForm() {
        return {
          title: els.title.value.trim(),
          description: els.description.value.trim(),
          status: els.statusInput.value,
          priority: els.priorityInput.value,
          assignee_name: els.ownerInput.value.trim(),
          story_points: Number(els.pointsInput.value || 1),
          end_date: els.dueInput.value,
          labels: els.labelsInput.value.trim()
        };
      }

      async function moveTicket(id, status) {
        var ticket = state.tickets.find(function (item) { return item.id === id; });
        if (!ticket || ticket.status === status) return;
        var previous = ticket.status;
        ticket.status = status;
        render();
        setSync("Moving " + id);
        try {
          var result = await api("/api/tickets/" + encodeURIComponent(id), {
            method: "PATCH",
            body: JSON.stringify({ status: status })
          });
          upsertLocalTicket(result.ticket);
          setSync("Moved " + id);
          render();
        } catch (err) {
          ticket.status = previous;
          render();
          setSync("Move failed");
          showNotice(err.message || "Could not move item");
        }
      }

      function upsertLocalTicket(ticket) {
        if (!ticket || !ticket.id) return;
        if (ticket.status === "Closed") {
          state.tickets = state.tickets.filter(function (item) { return item.id !== ticket.id; });
          return;
        }
        var index = state.tickets.findIndex(function (item) { return item.id === ticket.id; });
        if (index >= 0) state.tickets[index] = ticket;
        else state.tickets.unshift(ticket);
      }

      function threadUrl(ticket) {
        var threadId = String(ticket.thread_id || "").replace(/[^0-9]/g, "");
        if (!threadId) return "";
        var guildId = String(state.guildId || "").replace(/[^0-9]/g, "");
        return guildId ? "https://discord.com/channels/" + guildId + "/" + threadId : "https://discord.com/channels/@me/" + threadId;
      }

      function shortDate(value) {
        if (!value) return "";
        return String(value).slice(0, 10);
      }

      function isOverdue(ticket) {
        if (!ticket.end_date) return false;
        var due = new Date(shortDate(ticket.end_date) + "T23:59:59");
        return !Number.isNaN(due.getTime()) && due.getTime() < Date.now();
      }

      function showNotice(message) {
        window.clearTimeout(noticeTimer);
        els.notice.textContent = message;
        els.notice.classList.add("open");
        noticeTimer = window.setTimeout(function () {
          els.notice.classList.remove("open");
        }, 3600);
      }

      function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
      }
    })();
  </script>
</body>
</html>`;
}
