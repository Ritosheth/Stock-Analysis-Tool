const state = {
  reports: [],
  report: null,
  rows: [],
  filteredRows: [],
  headers: [],
  sortKey: "",
  sortDir: 1,
};

const priorityHeaders = [
  "代码",
  "名称",
  "类型",
  "涨停板数",
  "收盘价",
  "涨幅",
  "成交额(亿元)",
  "换手率",
  "量比",
  "所属行业",
  "核心题材",
  "市场阶段",
  "市场情绪",
  "题材层级",
  "个股地位",
  "角色分",
  "角色依据",
  "阶段",
  "次日计划",
  "上涨逻辑",
  "驱动类型",
  "上涨原因",
  "原因来源",
  "证据时间",
  "验证结论",
  "一句话复盘",
];

const filterFields = ["类型", "核心题材", "市场阶段", "题材层级", "个股地位", "次日计划", "验证结论"];

const elements = {
  healthText: document.querySelector("#healthText"),
  refreshReports: document.querySelector("#refreshReports"),
  dailyDate: document.querySelector("#dailyDate"),
  turnoverLimit: document.querySelector("#turnoverLimit"),
  evidenceSource: document.querySelector("#evidenceSource"),
  futuHost: document.querySelector("#futuHost"),
  futuPort: document.querySelector("#futuPort"),
  runDaily: document.querySelector("#runDaily"),
  validationReport: document.querySelector("#validationReport"),
  nextDate: document.querySelector("#nextDate"),
  runValidation: document.querySelector("#runValidation"),
  reportList: document.querySelector("#reportList"),
  status: document.querySelector("#status"),
  tableTitle: document.querySelector("#tableTitle"),
  rowCount: document.querySelector("#rowCount"),
  searchInput: document.querySelector("#searchInput"),
  fieldFilter: document.querySelector("#fieldFilter"),
  valueFilter: document.querySelector("#valueFilter"),
  clearFilters: document.querySelector("#clearFilters"),
  downloadCsv: document.querySelector("#downloadCsv"),
  table: document.querySelector("#dataTable"),
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function setStatus(message, type = "idle") {
  elements.status.textContent = message;
  elements.status.className = `status ${type}`;
}

function setBusy(isBusy) {
  elements.runDaily.disabled = isBusy;
  elements.runValidation.disabled = isBusy;
  elements.refreshReports.disabled = isBusy;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

async function checkHealth() {
  try {
    const payload = await api("/api/health");
    elements.healthText.textContent = payload.message;
  } catch (error) {
    elements.healthText.textContent = "本地服务异常";
  }
}

async function loadReports() {
  const payload = await api("/api/reports");
  state.reports = payload.reports;
  renderReportList();
  renderValidationOptions();
}

function renderReportList() {
  elements.reportList.innerHTML = "";
  if (!state.reports.length) {
    elements.reportList.innerHTML = '<div class="empty">暂无历史报表</div>';
    return;
  }

  state.reports.forEach((report) => {
    const button = document.createElement("button");
    button.className = "report-item";
    button.type = "button";
    button.addEventListener("click", () => loadReport(report.path, report.type));

    const name = document.createElement("span");
    name.className = "report-name";
    name.textContent = report.name;

    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = report.type === "daily" ? "复盘" : report.type === "html" ? "报告" : "验证";

    button.append(name, tag);
    elements.reportList.appendChild(button);
  });
}

function renderValidationOptions() {
  const dailyReports = state.reports.filter((report) => report.type === "daily");
  elements.validationReport.innerHTML = "";
  if (!dailyReports.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无日报";
    elements.validationReport.appendChild(option);
    return;
  }

  dailyReports.forEach((report) => {
    const option = document.createElement("option");
    option.value = report.path;
    option.textContent = report.name;
    elements.validationReport.appendChild(option);
  });
}

async function loadReport(path, type = "daily") {
  if (type === "html") {
    window.open(`/download?path=${encodeURIComponent(path)}`, "_blank");
    setStatus("HTML 报告已打开", "success");
    return;
  }
  setStatus("正在加载报表", "running");
  try {
    const payload = await api(`/api/report?path=${encodeURIComponent(path)}`);
    applyReport(payload.report);
    setStatus("报表已加载", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

function applyReport(report) {
  state.report = report;
  state.headers = orderHeaders(report.headers);
  state.rows = report.rows;
  state.sortKey = "";
  state.sortDir = 1;
  elements.tableTitle.textContent = report.name;
  elements.downloadCsv.disabled = !report.path;
  renderFilterFields();
  applyFilters();
}

function orderHeaders(headers) {
  const seen = new Set();
  const ordered = [];
  priorityHeaders.forEach((header) => {
    if (headers.includes(header)) {
      ordered.push(header);
      seen.add(header);
    }
  });
  headers.forEach((header) => {
    if (!seen.has(header)) {
      ordered.push(header);
    }
  });
  return ordered;
}

function renderFilterFields() {
  const available = filterFields.filter((field) => state.headers.includes(field));
  elements.fieldFilter.innerHTML = '<option value="">筛选字段</option>';
  available.forEach((field) => {
    const option = document.createElement("option");
    option.value = field;
    option.textContent = field;
    elements.fieldFilter.appendChild(option);
  });
  renderFilterValues();
}

function renderFilterValues() {
  const field = elements.fieldFilter.value;
  elements.valueFilter.innerHTML = '<option value="">全部</option>';
  if (!field) {
    return;
  }
  const values = Array.from(new Set(state.rows.map((row) => row[field]).filter(Boolean))).sort();
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    elements.valueFilter.appendChild(option);
  });
}

function applyFilters() {
  const keyword = elements.searchInput.value.trim().toLowerCase();
  const filterField = elements.fieldFilter.value;
  const filterValue = elements.valueFilter.value;

  state.filteredRows = state.rows.filter((row) => {
    if (filterField && filterValue && row[filterField] !== filterValue) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return state.headers.some((header) => String(row[header] || "").toLowerCase().includes(keyword));
  });

  if (state.sortKey) {
    sortRows(false);
  }
  renderTable();
}

function sortRows(toggle = true) {
  if (toggle) {
    state.sortDir *= -1;
  }
  const key = state.sortKey;
  state.filteredRows.sort((a, b) => compareValues(a[key], b[key]) * state.sortDir);
}

function compareValues(a, b) {
  const left = parseNumber(a);
  const right = parseNumber(b);
  if (left !== null && right !== null) {
    return left - right;
  }
  return String(a || "").localeCompare(String(b || ""), "zh-CN");
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function renderTable() {
  const thead = elements.table.querySelector("thead");
  const tbody = elements.table.querySelector("tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  elements.rowCount.textContent = `${state.filteredRows.length} / ${state.rows.length} 行`;

  if (!state.headers.length) {
    tbody.innerHTML = '<tr><td class="empty">请选择或生成一份报表</td></tr>';
    return;
  }

  const headRow = document.createElement("tr");
  state.headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header === state.sortKey ? `${header} ${state.sortDir > 0 ? "↑" : "↓"}` : header;
    th.addEventListener("click", () => {
      if (state.sortKey === header) {
        state.sortDir *= -1;
      } else {
        state.sortKey = header;
        state.sortDir = 1;
      }
      sortRows(false);
      renderTable();
    });
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  if (!state.filteredRows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "empty";
    cell.colSpan = state.headers.length;
    cell.textContent = "没有匹配数据";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  state.filteredRows.forEach((dataRow) => {
    const row = document.createElement("tr");
    state.headers.forEach((header) => {
      const cell = document.createElement("td");
      const value = dataRow[header] || "";
      cell.textContent = value;
      if (["上涨逻辑", "上涨原因", "一句话复盘", "所属概念", "所属行业"].includes(header)) {
        cell.classList.add("long");
      }
      if (parseNumber(value) !== null) {
        cell.classList.add("number");
      }
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
}

async function runDaily() {
  setBusy(true);
  setStatus("正在生成复盘，历史 K 线较多时会稍慢", "running");
  try {
    const payload = await api("/api/run-daily", {
      method: "POST",
      body: JSON.stringify({
        date: elements.dailyDate.value,
        turnover_limit: elements.turnoverLimit.value,
        evidence_source: elements.evidenceSource.value,
        host: elements.futuHost.value,
        port: elements.futuPort.value,
      }),
    });
    state.reports = payload.reports;
    renderReportList();
    renderValidationOptions();
    applyReport(payload.report);
    setStatus(payload.message, "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function runValidation() {
  setBusy(true);
  setStatus("正在生成次日验证", "running");
  try {
    const payload = await api("/api/validate", {
      method: "POST",
      body: JSON.stringify({
        report: elements.validationReport.value,
        next_date: elements.nextDate.value,
      }),
    });
    state.reports = payload.reports;
    renderReportList();
    renderValidationOptions();
    applyReport(payload.report);
    setStatus(payload.message, "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function bindEvents() {
  elements.refreshReports.addEventListener("click", async () => {
    try {
      await loadReports();
      setStatus("报表列表已刷新", "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
  elements.runDaily.addEventListener("click", runDaily);
  elements.runValidation.addEventListener("click", runValidation);
  elements.searchInput.addEventListener("input", applyFilters);
  elements.fieldFilter.addEventListener("change", () => {
    renderFilterValues();
    applyFilters();
  });
  elements.valueFilter.addEventListener("change", applyFilters);
  elements.clearFilters.addEventListener("click", () => {
    elements.searchInput.value = "";
    elements.fieldFilter.value = "";
    renderFilterValues();
    applyFilters();
  });
  elements.downloadCsv.addEventListener("click", () => {
    if (!state.report || !state.report.path) {
      return;
    }
    window.location.href = `/download?path=${encodeURIComponent(state.report.path)}`;
  });
}

async function init() {
  elements.dailyDate.value = todayIso();
  elements.nextDate.value = todayIso();
  bindEvents();
  await checkHealth();
  try {
    await loadReports();
    const previewReport = state.reports.find((report) => report.type !== "html");
    if (previewReport) {
      await loadReport(previewReport.path, previewReport.type);
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
}

init();
