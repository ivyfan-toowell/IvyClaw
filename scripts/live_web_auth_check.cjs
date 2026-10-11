/** Verify the account UI against a running local service using Playwright. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("playwright");

async function main() {
  const service = process.argv[2] || "http://localhost:18700";
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext({ viewport: { width: 1100, height: 850 } });
  const page = await context.newPage();
  const errors = [];
  const authRequests = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (new URL(request.url()).pathname.startsWith("/auth/")) authRequests.push(request.url());
  });
  const checks = [];
  const username = "web_probe_" + Date.now();
  const password = "Abc123";
  const visible = selector => page.locator(selector).waitFor({ state: "visible" });
  const expectText = (selector, text) => page.waitForFunction(
    ([id, expected]) => document.querySelector(id).textContent.includes(expected), [selector, text]);
  try {
    await page.goto(pathToFileURL(path.resolve("web/index.html")).href);
    await visible("#localServiceForm");
    assert.equal(await page.locator("#authForm").isVisible(), false);
    assert.equal(authRequests.length, 0, "file pages must not submit credentials");
    await page.locator("#localServiceUrl").fill(service);
    await page.locator("#localServiceForm button").click();
    await page.waitForURL(service + "/");
    await visible("#authForm");
    await page.waitForFunction(() => document.querySelector("#authUsername") === document.activeElement);
    checks.push("local-file service entry and separate login view");

    await page.locator("#registerBtn").click();
    await visible("#registerForm");
    assert.equal(await page.locator("#authForm").isVisible(), false);
    await page.locator("#registerUsername").fill(username);
    await page.locator("#registerPassword").fill("12345");
    await page.locator("#registerConfirm").fill("12345");
    const before = authRequests.length;
    await page.locator("#registerSubmit").click();
    assert.equal(await page.locator("#registerPassword").evaluate(e => e.validity.tooShort), true);
    assert.equal(authRequests.length, before);
    await page.locator("#registerPassword").fill(password);
    await page.locator("#registerConfirm").fill("Different");
    await page.locator("#registerSubmit").click();
    assert.equal(await page.locator("#registerConfirm").evaluate(e => e.validity.customError), true);
    assert.equal(authRequests.length, before);
    checks.push("five-character and confirmation-mismatch validation");

    await page.locator("#registerConfirm").fill(password);
    await page.locator("#registerSubmit").click();
    await expectText("#authNotice", "注册成功");
    assert.equal(await page.locator("#authUsername").inputValue(), username);
    assert.equal(await page.locator("#authPassword").inputValue(), "");
    assert.equal((await context.request.get(service + "/auth/me")).status(), 401);
    checks.push("six-character registration returns to login and revokes temporary session");

    await page.locator("#registerBtn").click();
    await page.locator("#registerPassword").fill(password);
    await page.locator("#registerConfirm").fill(password);
    await page.locator("#registerSubmit").click();
    await expectText("#registerError", "用户名不可用");
    await page.locator("#backToLoginBtn").click();
    await page.locator("#authPassword").fill("Wrong1");
    await page.locator("#loginSubmit").click();
    await expectText("#authError", "用户名或密码错误");
    checks.push("duplicate registration and incorrect-login feedback");

    await page.locator("#authPassword").fill(password);
    await page.locator("#loginSubmit").click();
    await page.locator("#authModal").waitFor({ state: "hidden" });
    await expectText("#logoutBtn", username);
    const account = await (await context.request.get(service + "/auth/me")).json();
    assert.equal(account.username, username);
    await page.reload();
    await page.locator("#authModal").waitFor({ state: "hidden" });
    const restored = await (await context.request.get(service + "/auth/me")).json();
    assert.equal(restored.userId, account.userId);
    checks.push("six-character login and refresh preserve account identity");

    fs.mkdirSync("logs", { recursive: true });
    await page.locator("#logoutBtn").click();
    await visible("#authForm");
    assert.equal((await context.request.get(service + "/auth/me")).status(), 401);
    await page.screenshot({ path: "logs/web_login.png" });
    await page.locator("#registerBtn").click();
    await page.screenshot({ path: "logs/web_register.png" });
    await page.locator("#backToLoginBtn").click();
    checks.push("logout revokes session and returns to login");

    // A saved custom endpoint can be unavailable; users can recover from the auth view.
    await page.evaluate(() => {
      localStorage.setItem("ivyclaw_backend_mode_v1", "custom");
      localStorage.setItem("devmate_backend_url", "http://127.0.0.1:1");
    });
    await page.reload();
    await expectText("#authError", "无法连接服务");
    await page.locator("#authForm .auth-backend-settings").click();
    await visible("#backendModal");
    await page.locator("#autoBackendBtn").click();
    await page.locator("#backendCloseBtn").click();
    await page.locator("#authUsername").fill(username);
    await page.locator("#authPassword").fill(password);
    await page.locator("#loginSubmit").click();
    await page.locator("#authModal").waitFor({ state: "hidden" });
    await expectText("#logoutBtn", username);
    await page.locator("#logoutBtn").click();
    await visible("#authForm");
    checks.push("unreachable-backend feedback and same-origin connection recovery");
    assert.deepEqual(errors, []);
    const report = { service, username, checks, pageErrors: errors };
    fs.writeFileSync("logs/live_web_auth_check.json", JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    console.error(JSON.stringify({ checks, pageErrors: errors, url: page.url(),
      loginError: await page.locator("#authError").textContent(),
      username: await page.locator("#authUsername").inputValue() }, null, 2));
    throw error;
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
