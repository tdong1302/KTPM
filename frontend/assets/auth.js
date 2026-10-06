const TOKEN_KEY = "eventhub.session-token";

function readSessionToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch (_error) {
    return "";
  }
}

function writeSessionToken(token) {
  try {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  } catch (_error) {
    // Memory state still supports the current page when storage is unavailable.
  }
}

export class AuthSession {
  constructor(api, onChange) {
    this.api = api;
    this.onChange = onChange;
    this.user = null;
    this.token = readSessionToken();
    this.api.setToken(this.token);
  }

  async restore() {
    if (!this.token) {
      this.onChange(this.user);
      return null;
    }
    try {
      this.user = await this.api.get("/api/auth/me", { auth: true });
      this.onChange(this.user);
      return this.user;
    } catch (_error) {
      this.clear();
      return null;
    }
  }

  async login(email, password) {
    const result = await this.api.post("/api/auth/login", { email, password });
    this.token = result.access_token;
    this.user = result.user;
    writeSessionToken(this.token);
    this.api.setToken(this.token);
    this.onChange(this.user);
    return this.user;
  }

  async register(payload) {
    await this.api.post("/api/auth/register", payload);
    return this.login(payload.email, payload.password);
  }

  clear() {
    this.token = "";
    this.user = null;
    writeSessionToken("");
    this.api.setToken("");
    this.onChange(this.user);
  }
}
