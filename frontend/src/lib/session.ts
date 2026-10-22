// Keep browser credentials and the middleware cookie in the same session.
export const SESSION_EXPIRED_EVENT = "campus:session-expired";
let notified = false;

export function isCurrentAccessToken(token: string, now = Date.now()) {
  try {
    const segment = token.split(".")[1];
    const payload = JSON.parse(atob(segment.replace(/-/g, "+").replace(/_/g, "/")));
    return payload.type === "access" && typeof payload.sub === "string" &&
      typeof payload.exp === "number" && payload.exp * 1000 > now;
  } catch {
    return false;
  }
}

export function clearSession(rejectedToken?: string) {
  // A late request from an old session must not sign out a newer login.
  if (rejectedToken && localStorage.getItem("access_token") !== rejectedToken) return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  document.cookie = "cs_token=; path=/; Max-Age=0; SameSite=Strict";
  if (!notified) {
    notified = true;
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
}

export function getAccessToken() {
  const token = localStorage.getItem("access_token");
  if (!token || !isCurrentAccessToken(token)) {
    clearSession(token || undefined);
    return null;
  }
  return token;
}

export function saveSession(token: string) {
  localStorage.setItem("access_token", token);
  document.cookie = `cs_token=${token}; path=/; SameSite=Strict`;
  notified = false;
}
