const STATUS_LABELS = {
  DRAFT: "Bản nháp",
  PUBLISHED: "Đang mở bán",
  CANCELLED: "Đã hủy",
  COMPLETED: "Đã kết thúc",
  CONFIRMED: "Đã xác nhận",
};

export function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([name, value]) => {
      if (value !== undefined && value !== null) node.setAttribute(name, String(value));
    });
  }
  if (options.dataset) {
    Object.entries(options.dataset).forEach(([name, value]) => {
      node.dataset[name] = String(value);
    });
  }
  const items = Array.isArray(children) ? children : [children];
  items.filter(Boolean).forEach((child) => node.append(child));
  return node;
}

export function formatDate(value, options = {}) {
  if (!value) return "Chưa xác định";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Chưa xác định";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: options.dateOnly ? "medium" : "long",
    ...(options.dateOnly ? {} : { timeStyle: "short" }),
  }).format(date);
}

export function dateParts(value) {
  const date = new Date(value);
  return {
    day: new Intl.DateTimeFormat("vi-VN", { day: "2-digit" }).format(date),
    month: new Intl.DateTimeFormat("vi-VN", { month: "short" }).format(date),
  };
}

export function formatNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(numeric);
}

export function statusBadge(status, { soldOut = false } = {}) {
  const normalized = soldOut ? "SOLD_OUT" : status;
  const labels = { ...STATUS_LABELS, SOLD_OUT: "Hết vé" };
  return element("span", {
    className: `status-badge status-${normalized.toLowerCase().replaceAll("_", "-")}`,
    text: labels[normalized] || normalized,
  });
}

export function emptyState(title, message) {
  return element("div", { className: "empty-state" }, [
    element("strong", { text: title }),
    element("span", { className: "muted", text: message }),
  ]);
}

export function loadingState(message = "Đang tải dữ liệu…") {
  return element("div", { className: "loading-state" }, [
    element("strong", { text: message }),
    element("span", { className: "muted", text: "Vui lòng chờ trong giây lát." }),
  ]);
}

export function setFormMessage(formOrElement, message = "", kind = "error") {
  const target = formOrElement.matches?.(".form-message")
    ? formOrElement
    : formOrElement.querySelector("[data-form-message]");
  if (!target) return;
  target.textContent = message;
  target.classList.toggle("is-success", kind === "success");
}

export async function withPending(form, action) {
  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton?.disabled) return;
  if (submitButton) submitButton.disabled = true;
  form.setAttribute("aria-busy", "true");
  try {
    await action();
  } finally {
    if (submitButton) submitButton.disabled = false;
    form.removeAttribute("aria-busy");
  }
}

export function notify(message, kind = "info") {
  const region = document.querySelector("#toast-region");
  const toast = element("div", {
    className: `toast${kind === "info" ? "" : ` is-${kind}`}`,
    text: message,
    attrs: { role: kind === "error" ? "alert" : "status" },
  });
  region.append(toast);
  window.setTimeout(() => toast.remove(), 5000);
}

export function initials(name = "") {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length ? words.slice(-2).map((word) => word[0]).join("") : "EH").toUpperCase();
}
