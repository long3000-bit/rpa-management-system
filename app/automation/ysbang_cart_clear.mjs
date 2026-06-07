const CDP = "http://127.0.0.1:9222";

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function pageWs() {
  const pages = await fetch(`${CDP}/json/list`).then(r => r.json());
  const page = pages.find(p => (p.url || "").includes("dian.ysbang.cn"));
  if (!page) throw new Error("未找到药师帮页面，请确保浏览器已打开并登录 dian.ysbang.cn");
  return page.webSocketDebuggerUrl;
}

class Runtime {
  constructor(ws) {
    this.ws = ws;
    this.seq = 0;
    this.pending = new Map();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
      }
    };
  }
  call(method, params = {}) {
    const id = ++this.seq;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  async eval(expression, timeout = 90000) {
    const result = await this.call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, timeout });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || JSON.stringify(result.exceptionDetails));
    return result.result?.value;
  }
}

async function navigateCart(rt) {
  await rt.call("Page.navigate", { url: `https://dian.ysbang.cn/?clearCart=${Date.now()}#/cart` }).catch(() => null);
  await sleep(4000);
}

const scanCode = `
(async () => {
  if (!document.body.innerText.includes("退出")) {
    return { loggedIn: false, items: [], text: document.body.innerText.slice(0, 300) };
  }
  const seen = new Set(), rows = [];
  const visit = (o, d) => {
    if (!o || typeof o !== "object" || d > 8 || seen.has(o)) return;
    seen.add(o);
    try {
      const id = o.wholesaleId || o.wholesaleid || o.wholeSaleId || o.id;
      const name = o.drugName || o.drugname || o.name || o.wholesaleDrugName;
      if (id && name && !Array.isArray(id) && !Array.isArray(name)) {
        rows.push({
          id: Number(id),
          name: String(name),
          amount: Number(o.amount || o.drugAmount || o.count || o.cnt || 0),
          provider: String(o.providerName || o.provider_name || o.providerTitle || ""),
          spec: String(o.specification || o.spec || ""),
          manufacturer: String(o.manufacturer || o.factory || o.drugFactoryName || "")
        });
      }
    } catch {}
    if (Array.isArray(o)) for (const x of o) visit(x, d + 1);
    else for (const k of Object.keys(o).slice(0, 100)) { try { visit(o[k], d + 1); } catch {} }
  };
  document.querySelectorAll("*").forEach(el => { if (el.__vue__) visit(el.__vue__, 0); });
  const unique = new Map();
  for (const row of rows) unique.set(row.id, row);
  return { loggedIn: true, items: Array.from(unique.values()).filter(x => x.id).slice(0, 100) };
})()
`;

async function deleteOne(rt, id) {
  return rt.eval(`
(async () => {
  if (!document.body.innerText.includes("退出")) return { code: "STOP", message: "登录状态异常" };
  const token = (document.cookie.match(/(?:^|; )Token=([^;]+)/) || [])[1] || "";
  return fetch('/shopping-cart/cart/deleteDrug/v4190', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      platform: 'pc',
      version: '6.1.5',
      ua: 'Chrome148',
      trafficType: 1,
      ex1: Math.random().toString(36).slice(2),
      wholesaleIds: [${Number(id)}],
      invalidWholesaleIds: [],
      token
    })
  }).then(r => r.json()).catch(e => ({ code: "ERROR", message: String(e) }));
})()
`, 90000);
}

async function clearCart() {
  console.log(`[开始] 正在连接浏览器...`);
  const ws = new WebSocket(await pageWs());
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  console.log(`[开始] 浏览器已连接`);
  const rt = new Runtime(ws);
  await rt.call("Runtime.enable");
  await rt.call("Page.enable").catch(() => null);
  console.log(`[开始] 正在导航到购物车页面...`);
  await navigateCart(rt);
  console.log(`[开始] 购物车页面已加载，开始清空...`);

  const results = [];
  let deletedCount = 0;

  for (let step = 1; step <= 80; step++) {
    console.log(`[步骤${step}] 正在扫描购物车...`);
    const scan = await rt.eval(scanCode, 90000);
    if (!scan?.loggedIn) {
      console.log(`[停止] 登录状态异常`);
      results.push({ step, status: "stopped", reason: "登录状态异常，停止清理", text: scan?.text || "" });
      break;
    }
    const items = scan.items || [];
    if (!items.length) {
      console.log(`[完成] 购物车已清空`);
      results.push({ step, status: "done", reason: "购物车已清空" });
      break;
    }
    console.log(`[步骤${step}] 购物车剩余 ${items.length} 个商品`);
    const target = items[0];
    console.log(`[步骤${step}] 删除: ${target.name} (${target.provider})`);
    const deleteResult = await deleteOne(rt, target.id);
    await sleep(1500);
    console.log(`[步骤${step}] 正在刷新购物车...`);
    await navigateCart(rt);
    const after = await rt.eval(scanCode, 90000);
    const stillThere = (after.items || []).some(x => Number(x.id) === Number(target.id));
    const ok = deleteResult?.code === "40001" && !stillThere;
    if (ok) {
      console.log(`[步骤${step}] 删除成功，剩余 ${after.items?.length ?? 0} 个`);
    } else {
      console.log(`[步骤${step}] 删除失败: ${deleteResult?.message || "验证失败"}`);
    }
    results.push({
      step,
      status: ok ? "deleted" : "failed",
      target,
      response: deleteResult,
      remaining: after.items?.length ?? null,
    });
    if (ok) deletedCount++;
    if (!ok) break;
    await sleep(2000);
  }

  ws.close();
  return { success: true, deletedCount, results };
}

(async () => {
  try {
    const result = await clearCart();
    console.log(JSON.stringify({ success: true, deletedCount: result.deletedCount }));
  } catch (error) {
    const errorMsg = error?.message || (typeof error === 'object' ? JSON.stringify(error) : String(error));
    console.log(JSON.stringify({ success: false, error: errorMsg }));
  }
})();