const STATUS_MESSAGES = {
  400: "Dữ liệu chưa đáp ứng quy tắc nghiệp vụ.",
  401: "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
  403: "Bạn không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy dữ liệu được yêu cầu.",
  409: "Thao tác xung đột với trạng thái hiện tại.",
  422: "Thông tin gửi lên chưa hợp lệ.",
};

const CODE_MESSAGES = {
  INVALID_CREDENTIALS: "Email hoặc mật khẩu không chính xác.",
  TOKEN_EXPIRED: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  TOKEN_INVALID: "Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.",
  UNAUTHENTICATED: "Vui lòng đăng nhập để tiếp tục.",
  FORBIDDEN: "Tài khoản của bạn không có quyền thực hiện thao tác này.",
  NOT_FOUND: "Không tìm thấy dữ liệu hoặc dữ liệu không hiển thị với tài khoản này.",
  CONFLICT: "Thao tác không thể hoàn tất ở trạng thái hiện tại.",
  REQUEST_VALIDATION_ERROR: "Vui lòng kiểm tra lại các trường thông tin.",
  VALIDATION_ERROR: "Thông tin chưa đáp ứng quy tắc nghiệp vụ.",
};

export class ApiError extends Error {
  constructor(message, { status = 0, code = "NETWORK_ERROR", detail = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function readableMessage(status, code, detail) {
  const base = CODE_MESSAGES[code] || STATUS_MESSAGES[status] || "Đã có lỗi không mong đợi.";
  if (!detail || detail.toLowerCase() === base.toLowerCase()) {
    return base;
  }
  return `${base} Chi tiết: ${detail}`;
}

export class ApiClient {
  constructor({ onUnauthorized } = {}) {
    this.token = "";
    this.onUnauthorized = onUnauthorized;
  }

  setToken(token) {
    this.token = token || "";
  }

  async request(path, { method = "GET", query, body, auth = false } = {}) {
    const url = new URL(path, window.location.origin);
    if (query) {
      Object.entries(query).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          url.searchParams.set(key, String(value));
        }
      });
    }

    const headers = { Accept: "application/json" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (auth && this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (_error) {
      throw new ApiError("Không thể kết nối đến EventHub. Hãy kiểm tra máy chủ và thử lại.");
    }

    const contentType = response.headers.get("content-type") || "";
    let payload = null;
    if (response.status !== 204) {
      if (contentType.includes("application/json")) {
        payload = await response.json().catch(() => null);
      } else {
        payload = await response.text().catch(() => "");
      }
    }

    if (!response.ok) {
      const code = payload && typeof payload === "object" ? payload.code : `HTTP_${response.status}`;
      const detail = payload && typeof payload === "object" ? payload.message || "" : "";
      if (response.status === 401 && auth && this.token && this.onUnauthorized) {
        this.onUnauthorized({ code, detail });
      }
      throw new ApiError(readableMessage(response.status, code, detail), {
        status: response.status,
        code,
        detail,
      });
    }

    return payload;
  }

  get(path, options = {}) {
    return this.request(path, { ...options, method: "GET" });
  }

  post(path, body, options = {}) {
    return this.request(path, { ...options, method: "POST", body });
  }

  patch(path, body, options = {}) {
    return this.request(path, { ...options, method: "PATCH", body });
  }

  delete(path, options = {}) {
    return this.request(path, { ...options, method: "DELETE" });
  }
}
