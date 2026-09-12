const API_BASE_URL =
  (typeof import.meta !== "undefined" &&
    import.meta.env &&
    import.meta.env.VITE_API_BASE_URL) ||
  "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  constructor(message, status, code = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
    });
  } catch (networkErr) {
    throw new ApiError(
      `Network error calling ${options.method || "GET"} ${path}: ${networkErr.message}`,
      0
    );
  }

  if (!response.ok) {
    let message = `${options.method || "GET"} ${path} failed with status ${response.status}`;
    let code = null;
    try {
      const body = await response.json();
      if (body?.error?.message) {
        message = body.error.message;
      }
      if (body?.error?.code) {
        code = body.error.code;
      }
    } catch {
      // ignore parse errors, fall back to status message
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function getNetworkStatus() {
  return request("/network-status");
}