let authMode = "signin"; // "signin" or "signup"

async function authRequest(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = null;
  try {
    const text = await response.text();
    data = text && text.trim().startsWith("{") ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data && data.error ? data.error : "Authentication failed";
    throw new Error(message);
  }

  return data || {};
}

function logEvent(tag, data = {}) {
  try {
    const body = JSON.stringify({ tag, data });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon("/api/log-event", blob);
    } else {
      fetch("/api/log-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      });
    }
  } catch {
    // best effort
  }
}

function setMessage(message, isError = false) {
  const node = document.getElementById("auth-message");
  if (!node) return;
  node.textContent = message;
  node.className = isError ? "auth-message error" : "auth-message success";
}

function setFormLoading(isLoading) {
  const btn = document.getElementById("submit-auth-btn");
  const spinner = document.getElementById("submit-spinner");
  const text = document.getElementById("submit-btn-text");
  if (!btn) return;
  btn.disabled = isLoading;
  spinner?.classList.toggle("hidden", !isLoading);
  if (isLoading) {
    text.textContent = authMode === "signin" ? "Verifying Credentials..." : "Creating Account...";
  } else {
    text.textContent = authMode === "signin" ? "Sign In to Dashboard" : "Register Clinician Account";
  }
}

function setAuthMode(mode) {
  authMode = mode;
  document.getElementById("tab-signin")?.classList.toggle("active", mode === "signin");
  document.getElementById("tab-signup")?.classList.toggle("active", mode === "signup");
  const text = document.getElementById("submit-btn-text");
  if (text) {
    text.textContent = mode === "signin" ? "Sign In to Dashboard" : "Register Clinician Account";
  }
  setMessage("");
}

document.getElementById("tab-signin")?.addEventListener("click", () => setAuthMode("signin"));
document.getElementById("tab-signup")?.addEventListener("click", () => setAuthMode("signup"));

// Password visibility toggle
document.getElementById("toggle-pwd-btn")?.addEventListener("click", () => {
  const pwdInput = document.getElementById("password");
  if (!pwdInput) return;
  const isPwd = pwdInput.type === "password";
  pwdInput.type = isPwd ? "text" : "password";
  document.getElementById("toggle-pwd-btn").textContent = isPwd ? "🔒" : "👁️";
});

// Quick 1-Click Demo Login
document.getElementById("demo-login-btn")?.addEventListener("click", async () => {
  document.getElementById("username").value = "demo_doctor";
  document.getElementById("password").value = "Password123!";
  setAuthMode("signin");
  logEvent("demo_login_click", { page: "signin" });
  await submitAuth();
});

async function submitAuth() {
  const username = String(document.getElementById("username")?.value || "").trim();
  const password = String(document.getElementById("password")?.value || "").trim();

  if (!username || !password) {
    setMessage("Please enter both username and password.", true);
    return;
  }

  setFormLoading(true);
  try {
    const endpoint = authMode === "signin" ? "/api/auth/signin" : "/api/auth/signup";
    logEvent(`${authMode}_submit`, { page: "signin", username });
    await authRequest(endpoint, { username, password });
    setMessage(authMode === "signin" ? "Signed in successfully! Launching dashboard..." : "Account created! Launching...", false);
    window.location.href = "/loading";
  } catch (error) {
    setFormLoading(false);
    setMessage(error.message, true);
  }
}

document.getElementById("auth-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitAuth();
});

// Check if already authenticated on initial load
fetch("/api/auth/status")
  .then((r) => r.json())
  .then((data) => {
    if (data.authenticated) {
      window.location.href = "/dashboard";
    }
  })
  .catch(() => {});
