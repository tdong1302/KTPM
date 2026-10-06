import { ApiClient, ApiError } from "./api.js";
import { AuthSession } from "./auth.js";
import {
  dateParts,
  element,
  emptyState,
  formatDate,
  formatNumber,
  initials,
  loadingState,
  notify,
  setFormMessage,
  statusBadge,
  withPending,
} from "./ui.js";

const select = (selector, root = document) => root.querySelector(selector);
const selectAll = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  events: [],
  eventPage: 1,
  eventTotalPages: 1,
  eventSize: 6,
  eventQuery: {},
  bookings: [],
  bookingPage: 1,
  bookingTotalPages: 1,
  organizerEvents: new Map(),
};

let session;
const api = new ApiClient({
  onUnauthorized: () => {
    session?.clear();
    notify("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "error");
    showAuthTab("login");
    showView("auth");
  },
});

session = new AuthSession(api, updateAuthenticationUI);

const eventGrid = select("#event-grid");
const bookingList = select("#booking-list");
const organizerEventList = select("#organizer-event-list");
const eventDialog = select("#event-dialog");
const eventDialogContent = select("#event-dialog-content");
const bookingDialog = select("#booking-dialog");
const bookingDialogContent = select("#booking-dialog-content");

function showView(name) {
  if (name === "bookings" && session.user?.role !== "USER") {
    name = session.user ? "events" : "auth";
  }
  if (name === "organizer" && session.user?.role !== "ORGANIZER") {
    name = session.user ? "events" : "auth";
  }

  selectAll("[data-view-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== name;
  });
  selectAll("[data-view]").forEach((button) => {
    const active = button.dataset.view === name;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });

  if (name === "bookings") loadBookings();
  if (name === "organizer") loadTrackedOrganizerEvents();
  select("#main-content").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateAuthenticationUI(user) {
  const loggedIn = Boolean(user);
  select("#account-summary").hidden = !loggedIn;
  select("#auth-open-button").hidden = loggedIn;
  select("#logout-button").hidden = !loggedIn;
  selectAll("[data-user-only]").forEach((item) => {
    item.hidden = user?.role !== "USER";
  });
  selectAll("[data-organizer-only]").forEach((item) => {
    item.hidden = user?.role !== "ORGANIZER";
  });

  if (user) {
    select("#account-name").textContent = user.full_name;
    select("#account-role").textContent = user.role === "ORGANIZER" ? "Nhà tổ chức" : "Người tham dự";
    select("#account-avatar").textContent = initials(user.full_name);
  } else {
    state.bookings = [];
    state.organizerEvents.clear();
    renderBookings();
    renderOrganizerEvents();
  }
}

function showAuthTab(name) {
  const isLogin = name === "login";
  select("#login-panel").hidden = !isLogin;
  select("#register-panel").hidden = isLogin;
  select("#login-tab").classList.toggle("is-active", isLogin);
  select("#register-tab").classList.toggle("is-active", !isLogin);
  select("#login-tab").setAttribute("aria-selected", String(isLogin));
  select("#register-tab").setAttribute("aria-selected", String(!isLogin));
  window.setTimeout(() => {
    select(isLogin ? "#login-email" : "#register-name").focus();
  }, 0);
}

function eventCard(event) {
  const parts = dateParts(event.start_time);
  const soldOut = event.available_tickets === 0;
  const detailButton = element("button", {
    className: "button button-secondary button-small",
    text: "Xem chi tiết",
    attrs: { type: "button", "aria-label": `Xem chi tiết ${event.title}` },
    dataset: { eventId: event.id },
  });

  return element("article", { className: "event-card" }, [
    element("div", { className: "event-card-accent" }, [
      element("div", { className: "event-date-block" }, [
        element("strong", { text: parts.day }),
        element("small", { text: parts.month }),
      ]),
      statusBadge(event.status, { soldOut }),
    ]),
    element("div", { className: "event-card-body" }, [
      element("p", { className: "event-category", text: event.category }),
      element("h3", { text: event.title }),
      element("p", {
        className: "event-location",
        text: `${event.city} · ${event.location}`,
      }),
      element("div", { className: "event-card-footer" }, [
        element("div", {}, [
          element("span", { className: "price-label", text: "Giá mỗi vé" }),
          element("strong", { className: "price-value", text: formatNumber(event.price) }),
        ]),
        element("div", {}, [
          element("span", { className: "ticket-label", text: "Còn lại" }),
          element("strong", {
            className: "ticket-value",
            text: `${event.available_tickets}/${event.total_tickets} vé`,
          }),
        ]),
        detailButton,
      ]),
    ]),
  ]);
}

function renderEvents() {
  eventGrid.replaceChildren();
  eventGrid.setAttribute("aria-busy", "false");
  if (!state.events.length) {
    eventGrid.append(
      emptyState("Chưa có sự kiện phù hợp", "Hãy thử thay đổi từ khóa hoặc bộ lọc hiện tại."),
    );
  } else {
    eventGrid.append(...state.events.map(eventCard));
  }

  select("#events-summary").textContent = state.events.length
    ? `Hiển thị ${state.events.length} sự kiện trong trang này.`
    : "Không tìm thấy sự kiện đang mở phù hợp.";
  select("#events-page-label").textContent = `Trang ${state.eventPage} / ${state.eventTotalPages}`;
  select("#events-previous").disabled = state.eventPage <= 1;
  select("#events-next").disabled = state.eventPage >= state.eventTotalPages;
}

async function loadEvents() {
  eventGrid.setAttribute("aria-busy", "true");
  eventGrid.replaceChildren(loadingState("Đang tìm sự kiện phù hợp…"));
  try {
    const result = await api.get("/api/events", {
      query: {
        ...state.eventQuery,
        page: state.eventPage,
        size: state.eventSize,
      },
    });
    state.events = result.items;
    state.eventPage = result.page;
    state.eventTotalPages = Math.max(1, result.total_pages);
    renderEvents();
    select("#events-summary").textContent = `${result.total} sự kiện phù hợp · Trang ${result.page}/${Math.max(1, result.total_pages)}`;
  } catch (error) {
    eventGrid.setAttribute("aria-busy", "false");
    eventGrid.replaceChildren(
      emptyState("Không thể tải sự kiện", error.message || "Vui lòng thử lại sau."),
    );
    notify(error.message, "error");
  }
}

function detailItem(label, value) {
  return element("div", { className: "detail-item" }, [
    element("span", { text: label }),
    element("strong", { text: value }),
  ]);
}

function renderEventDetail(event) {
  const soldOut = event.available_tickets === 0;
  const content = element("div", { className: "detail-content" }, [
    statusBadge(event.status, { soldOut }),
    element("h2", { text: event.title }),
    element("p", { className: "event-category", text: event.category }),
    element("p", { className: "detail-description", text: event.description || "Chưa có mô tả." }),
    element("div", { className: "detail-grid" }, [
      detailItem("Thời gian", formatDate(event.start_time)),
      detailItem("Kết thúc", formatDate(event.end_time)),
      detailItem("Địa điểm", `${event.city} · ${event.location}`),
      detailItem("Giá mỗi vé", formatNumber(event.price)),
      detailItem("Vé còn lại", `${event.available_tickets}/${event.total_tickets}`),
      detailItem("Mã sự kiện", `#${event.id}`),
    ]),
  ]);

  if (!session.user) {
    const prompt = element("div", { className: "auth-prompt" }, [
      element("p", { text: "Đăng nhập bằng tài khoản người tham dự để đặt vé." }),
      element("button", {
        className: "button button-primary",
        text: "Đăng nhập để đặt vé",
        attrs: { type: "button" },
      }),
    ]);
    select("button", prompt).addEventListener("click", () => {
      eventDialog.close();
      showAuthTab("login");
      showView("auth");
    });
    content.append(prompt);
  } else if (session.user.role === "USER" && event.status === "PUBLISHED" && !soldOut) {
    const form = element("form", { className: "booking-form" }, [
      element("div", { className: "field" }, [
        element("label", { text: "Số lượng vé", attrs: { for: "booking-quantity" } }),
        element("input", {
          attrs: {
            id: "booking-quantity",
            name: "quantity",
            type: "number",
            min: 1,
            max: Math.min(10, event.available_tickets),
            value: 1,
            required: "",
          },
        }),
      ]),
      element("button", {
        className: "button button-primary",
        text: "Đặt vé",
        attrs: { type: "submit" },
      }),
      element("p", {
        className: "form-message",
        attrs: { "data-form-message": "", "aria-live": "polite" },
      }),
    ]);
    form.addEventListener("submit", (submitEvent) => bookEvent(submitEvent, event));
    content.append(form);
  }

  eventDialogContent.replaceChildren(content);
}

async function openEvent(eventId) {
  eventDialogContent.replaceChildren(loadingState("Đang tải chi tiết sự kiện…"));
  if (!eventDialog.open) eventDialog.showModal();
  try {
    const event = await api.get(`/api/events/${eventId}`, { auth: Boolean(session.user) });
    renderEventDetail(event);
  } catch (error) {
    eventDialogContent.replaceChildren(emptyState("Không thể mở sự kiện", error.message));
  }
}

async function bookEvent(submitEvent, event) {
  submitEvent.preventDefault();
  const form = submitEvent.currentTarget;
  await withPending(form, async () => {
    setFormMessage(form);
    try {
      const quantity = Number(new FormData(form).get("quantity"));
      const booking = await api.post(
        "/api/bookings",
        { event_id: event.id, quantity },
        { auth: true },
      );
      notify(`Đặt ${booking.quantity} vé thành công.`, "success");
      await loadEvents();
      const refreshed = await api.get(`/api/events/${event.id}`, { auth: true });
      renderEventDetail(refreshed);
    } catch (error) {
      setFormMessage(form, error.message);
    }
  });
}

function bookingCard(booking) {
  const actions = element("div", { className: "booking-actions" });
  const detailButton = element("button", {
    className: "button button-ghost button-small",
    text: "Chi tiết",
    attrs: { type: "button" },
    dataset: { bookingDetail: booking.id },
  });
  actions.append(detailButton);
  if (booking.status === "CONFIRMED") {
    actions.append(
      element("button", {
        className: "button button-danger button-small",
        text: "Hủy vé",
        attrs: { type: "button" },
        dataset: { bookingCancel: booking.id, eventId: booking.event_id },
      }),
    );
  }

  return element("article", { className: "booking-card" }, [
    element("div", {}, [
      element("h3", { text: booking.event_title }),
      element("p", { text: `Mã đặt vé #${booking.id} · Sự kiện #${booking.event_id}` }),
    ]),
    element("div", { className: "booking-stat" }, [
      element("span", { text: "Số lượng" }),
      element("strong", { text: `${booking.quantity} vé` }),
    ]),
    element("div", { className: "booking-stat" }, [
      element("span", { text: "Tổng giá" }),
      element("strong", { text: formatNumber(booking.total_price) }),
    ]),
    statusBadge(booking.status),
    actions,
  ]);
}

function renderBookings() {
  bookingList.replaceChildren();
  bookingList.setAttribute("aria-busy", "false");
  if (!state.bookings.length) {
    bookingList.append(
      emptyState("Bạn chưa có vé", "Khám phá một sự kiện đang mở và bắt đầu trải nghiệm."),
    );
  } else {
    bookingList.append(...state.bookings.map(bookingCard));
  }
  select("#bookings-page-label").textContent = `Trang ${state.bookingPage} / ${state.bookingTotalPages}`;
  select("#bookings-previous").disabled = state.bookingPage <= 1;
  select("#bookings-next").disabled = state.bookingPage >= state.bookingTotalPages;
}

async function loadBookings() {
  if (session.user?.role !== "USER") return;
  bookingList.setAttribute("aria-busy", "true");
  bookingList.replaceChildren(loadingState("Đang tải vé của bạn…"));
  try {
    const result = await api.get("/api/bookings/me", {
      auth: true,
      query: { page: state.bookingPage, size: 10 },
    });
    state.bookings = result.items;
    state.bookingPage = result.page;
    state.bookingTotalPages = Math.max(1, result.total_pages);
    select("#bookings-summary").textContent = `${result.total} lượt đặt vé trong tài khoản.`;
    renderBookings();
  } catch (error) {
    bookingList.setAttribute("aria-busy", "false");
    bookingList.replaceChildren(emptyState("Không thể tải danh sách vé", error.message));
    notify(error.message, "error");
  }
}

function renderBookingDetail(booking) {
  bookingDialogContent.replaceChildren(
    element("div", { className: "detail-content" }, [
      statusBadge(booking.status),
      element("h2", { text: booking.event_title }),
      element("div", { className: "detail-grid" }, [
        detailItem("Mã đặt vé", `#${booking.id}`),
        detailItem("Mã sự kiện", `#${booking.event_id}`),
        detailItem("Ngày diễn ra", formatDate(booking.event_start_time)),
        detailItem("Ngày đặt", formatDate(booking.created_at)),
        detailItem("Số lượng", `${booking.quantity} vé`),
        detailItem("Giá mỗi vé", formatNumber(booking.unit_price)),
        detailItem("Tổng giá", formatNumber(booking.total_price)),
        detailItem("Ngày hủy", booking.cancelled_at ? formatDate(booking.cancelled_at) : "—"),
      ]),
    ]),
  );
}

async function openBooking(bookingId) {
  bookingDialogContent.replaceChildren(loadingState("Đang tải chi tiết vé…"));
  if (!bookingDialog.open) bookingDialog.showModal();
  try {
    const booking = await api.get(`/api/bookings/${bookingId}`, { auth: true });
    renderBookingDetail(booking);
  } catch (error) {
    bookingDialogContent.replaceChildren(emptyState("Không thể mở vé", error.message));
  }
}

async function cancelBooking(bookingId, eventId, button) {
  if (!window.confirm("Bạn có chắc muốn hủy lượt đặt vé này? Số vé sẽ được hoàn lại.")) return;
  button.disabled = true;
  try {
    await api.delete(`/api/bookings/${bookingId}`, { auth: true });
    notify("Đã hủy vé và hoàn lại tồn kho.", "success");
    await Promise.all([loadBookings(), loadEvents()]);
    if (eventDialog.open) await openEvent(eventId);
  } catch (error) {
    notify(error.message, "error");
    button.disabled = false;
  }
}

function organizerStorageKey() {
  return session.user ? `eventhub.organizer-events.${session.user.id}` : "";
}

function readOrganizerIds() {
  try {
    const value = JSON.parse(sessionStorage.getItem(organizerStorageKey()) || "[]");
    return Array.isArray(value) ? value.filter(Number.isInteger) : [];
  } catch (_error) {
    return [];
  }
}

function persistOrganizerIds() {
  try {
    sessionStorage.setItem(
      organizerStorageKey(),
      JSON.stringify([...state.organizerEvents.keys()]),
    );
  } catch (_error) {
    // The current in-memory session remains usable.
  }
}

function organizerEventCard(event) {
  const actions = element("div", { className: "organizer-actions" });
  actions.append(
    element("button", {
      className: "button button-ghost button-small",
      text: "Xem",
      attrs: { type: "button" },
      dataset: { organizerAction: "view", eventId: event.id },
    }),
  );
  if (event.status === "DRAFT") {
    actions.append(
      element("button", {
        className: "button button-primary button-small",
        text: "Phát hành",
        attrs: { type: "button" },
        dataset: { organizerAction: "publish", eventId: event.id },
      }),
      element("button", {
        className: "button button-ghost button-small",
        text: "Hủy sự kiện",
        attrs: { type: "button" },
        dataset: { organizerAction: "cancel", eventId: event.id },
      }),
      element("button", {
        className: "button button-danger button-small",
        text: "Xóa bản nháp",
        attrs: { type: "button" },
        dataset: { organizerAction: "delete", eventId: event.id },
      }),
    );
  } else if (event.status === "PUBLISHED") {
    actions.append(
      element("button", {
        className: "button button-danger button-small",
        text: "Hủy sự kiện",
        attrs: { type: "button" },
        dataset: { organizerAction: "cancel", eventId: event.id },
      }),
    );
  }

  return element("article", { className: "organizer-event-card" }, [
    element("header", {}, [
      element("div", {}, [
        element("h3", { text: event.title }),
        element("p", { text: `#${event.id} · ${formatDate(event.start_time)}` }),
      ]),
      statusBadge(event.status),
    ]),
    actions,
  ]);
}

function renderOrganizerEvents() {
  organizerEventList.replaceChildren();
  const events = [...state.organizerEvents.values()].sort((a, b) => b.id - a.id);
  if (!events.length) {
    organizerEventList.append(
      emptyState("Chưa có sự kiện trong phiên", "Tạo bản nháp mới hoặc tải sự kiện bằng ID."),
    );
  } else {
    organizerEventList.append(...events.map(organizerEventCard));
  }
}

async function loadOrganizerEvent(eventId, { quiet = false } = {}) {
  const event = await api.get(`/api/events/${eventId}`, { auth: true });
  if (event.organizer_id !== session.user?.id) {
    throw new ApiError("Sự kiện này không thuộc tài khoản nhà tổ chức hiện tại.", { status: 403 });
  }
  state.organizerEvents.set(event.id, event);
  persistOrganizerIds();
  renderOrganizerEvents();
  if (!quiet) notify(`Đã tải sự kiện #${event.id}.`, "success");
  return event;
}

async function loadTrackedOrganizerEvents() {
  if (session.user?.role !== "ORGANIZER") return;
  const ids = readOrganizerIds();
  if (!ids.length) {
    renderOrganizerEvents();
    return;
  }
  const results = await Promise.allSettled(ids.map((id) => loadOrganizerEvent(id, { quiet: true })));
  const missingIds = ids.filter((_, index) => results[index].status === "rejected");
  missingIds.forEach((id) => state.organizerEvents.delete(id));
  persistOrganizerIds();
  renderOrganizerEvents();
}

async function createEvent(submitEvent) {
  submitEvent.preventDefault();
  const form = submitEvent.currentTarget;
  await withPending(form, async () => {
    setFormMessage(form);
    const values = new FormData(form);
    try {
      const payload = {
        title: values.get("title").trim(),
        description: values.get("description").trim(),
        category: values.get("category").trim(),
        city: values.get("city").trim(),
        location: values.get("location").trim(),
        start_time: new Date(values.get("start_time")).toISOString(),
        end_time: new Date(values.get("end_time")).toISOString(),
        total_tickets: Number(values.get("total_tickets")),
        price: values.get("price"),
      };
      const event = await api.post("/api/events", payload, { auth: true });
      state.organizerEvents.set(event.id, event);
      persistOrganizerIds();
      renderOrganizerEvents();
      form.reset();
      setDefaultEventDates();
      setFormMessage(form, `Đã tạo bản nháp #${event.id}.`, "success");
      notify("Bản nháp đã được tạo. Kiểm tra trước khi phát hành.", "success");
    } catch (error) {
      setFormMessage(form, error.message);
    }
  });
}

async function organizerAction(action, eventId, button) {
  if (action === "view") {
    await openEvent(eventId);
    return;
  }
  if (action === "delete" && !window.confirm("Xóa vĩnh viễn bản nháp này?")) return;
  if (action === "cancel" && !window.confirm("Hủy sự kiện này? Trạng thái này không thể hoàn tác.")) return;

  button.disabled = true;
  try {
    if (action === "delete") {
      await api.delete(`/api/events/${eventId}`, { auth: true });
      state.organizerEvents.delete(eventId);
      notify("Đã xóa bản nháp.", "success");
    } else {
      const event = await api.patch(`/api/events/${eventId}/${action}`, undefined, { auth: true });
      state.organizerEvents.set(event.id, event);
      notify(action === "publish" ? "Sự kiện đã được phát hành." : "Sự kiện đã được hủy.", "success");
    }
    persistOrganizerIds();
    renderOrganizerEvents();
    await loadEvents();
  } catch (error) {
    notify(error.message, "error");
    button.disabled = false;
  }
}

function localDateTimeValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function setDefaultEventDates() {
  const start = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  start.setHours(19, 0, 0, 0);
  const end = new Date(start.getTime() + 3 * 60 * 60 * 1000);
  select("#event-start").value = localDateTimeValue(start);
  select("#event-end").value = localDateTimeValue(end);
}

function bindNavigation() {
  selectAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  select("#auth-open-button").addEventListener("click", () => {
    showAuthTab("login");
    showView("auth");
  });
  select("#hero-auth-button").addEventListener("click", () => {
    if (session.user) {
      showView(session.user.role === "ORGANIZER" ? "organizer" : "bookings");
    } else {
      showAuthTab("register");
      showView("auth");
    }
  });
  select("#explore-button").addEventListener("click", () => {
    select("#event-catalogue").scrollIntoView({ behavior: "smooth" });
  });
  select("#logout-button").addEventListener("click", () => {
    session.clear();
    notify("Bạn đã đăng xuất. Dữ liệu phiên được xóa khỏi giao diện.", "success");
    showView("events");
  });
}

function bindAuthentication() {
  select("#login-tab").addEventListener("click", () => showAuthTab("login"));
  select("#register-tab").addEventListener("click", () => showAuthTab("register"));

  select("#login-form").addEventListener("submit", async (submitEvent) => {
    submitEvent.preventDefault();
    const form = submitEvent.currentTarget;
    await withPending(form, async () => {
      setFormMessage(form);
      const values = new FormData(form);
      try {
        const user = await session.login(values.get("email"), values.get("password"));
        form.reset();
        notify(`Chào mừng ${user.full_name} quay lại.`, "success");
        showView(user.role === "ORGANIZER" ? "organizer" : "events");
      } catch (error) {
        setFormMessage(form, error.message);
      }
    });
  });

  select("#register-form").addEventListener("submit", async (submitEvent) => {
    submitEvent.preventDefault();
    const form = submitEvent.currentTarget;
    await withPending(form, async () => {
      setFormMessage(form);
      const values = new FormData(form);
      try {
        const user = await session.register({
          full_name: values.get("full_name").trim(),
          email: values.get("email").trim(),
          password: values.get("password"),
          role: values.get("role"),
        });
        form.reset();
        notify("Tạo tài khoản và đăng nhập thành công.", "success");
        showView(user.role === "ORGANIZER" ? "organizer" : "events");
      } catch (error) {
        setFormMessage(form, error.message);
      }
    });
  });
}

function bindEventDiscovery() {
  select("#event-filters").addEventListener("submit", (submitEvent) => {
    submitEvent.preventDefault();
    const values = new FormData(submitEvent.currentTarget);
    const [sortBy, sortDir] = values.get("sort").split(":");
    state.eventQuery = {
      q: values.get("q").trim(),
      city: values.get("city").trim(),
      category: values.get("category").trim(),
      sort_by: sortBy,
      sort_dir: sortDir,
    };
    state.eventPage = 1;
    loadEvents();
  });
  select("#event-filters").addEventListener("reset", () => {
    window.setTimeout(() => {
      state.eventQuery = {};
      state.eventPage = 1;
      loadEvents();
    }, 0);
  });
  select("#refresh-events").addEventListener("click", loadEvents);
  select("#events-previous").addEventListener("click", () => {
    state.eventPage = Math.max(1, state.eventPage - 1);
    loadEvents();
  });
  select("#events-next").addEventListener("click", () => {
    state.eventPage += 1;
    loadEvents();
  });
  eventGrid.addEventListener("click", (clickEvent) => {
    const button = clickEvent.target.closest("[data-event-id]");
    if (button) openEvent(Number(button.dataset.eventId));
  });
}

function bindBookings() {
  select("#refresh-bookings").addEventListener("click", loadBookings);
  select("#bookings-previous").addEventListener("click", () => {
    state.bookingPage = Math.max(1, state.bookingPage - 1);
    loadBookings();
  });
  select("#bookings-next").addEventListener("click", () => {
    state.bookingPage += 1;
    loadBookings();
  });
  bookingList.addEventListener("click", (clickEvent) => {
    const detail = clickEvent.target.closest("[data-booking-detail]");
    if (detail) openBooking(Number(detail.dataset.bookingDetail));
    const cancel = clickEvent.target.closest("[data-booking-cancel]");
    if (cancel) {
      cancelBooking(
        Number(cancel.dataset.bookingCancel),
        Number(cancel.dataset.eventId),
        cancel,
      );
    }
  });
}

function bindOrganizer() {
  select("#event-create-form").addEventListener("submit", createEvent);
  select("#organizer-load-form").addEventListener("submit", async (submitEvent) => {
    submitEvent.preventDefault();
    const form = submitEvent.currentTarget;
    const message = select("#organizer-message");
    message.textContent = "";
    await withPending(form, async () => {
      try {
        await loadOrganizerEvent(Number(new FormData(form).get("event_id")));
        form.reset();
      } catch (error) {
        message.textContent = error.message;
      }
    });
  });
  organizerEventList.addEventListener("click", (clickEvent) => {
    const button = clickEvent.target.closest("[data-organizer-action]");
    if (button) {
      organizerAction(button.dataset.organizerAction, Number(button.dataset.eventId), button);
    }
  });
}

function bindDialogs() {
  selectAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => select(`#${button.dataset.closeDialog}`).close());
  });
  [eventDialog, bookingDialog].forEach((dialog) => {
    dialog.addEventListener("click", (clickEvent) => {
      if (clickEvent.target === dialog) dialog.close();
    });
  });
}

async function initialize() {
  bindNavigation();
  bindAuthentication();
  bindEventDiscovery();
  bindBookings();
  bindOrganizer();
  bindDialogs();
  setDefaultEventDates();
  renderBookings();
  renderOrganizerEvents();
  await session.restore();
  await loadEvents();
}

initialize();
