const CDP = "http://127.0.0.1:9222";

const TARGET_ID = process.argv[2] || "";

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
  await rt.call("Page.navigate", { url: `https://dian.ysbang.cn/?deleteById=${Date.now()}#/cart` }).catch(() => null);
  await sleep(7500);
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

async function deleteById(targetId) {
  const ws = new WebSocket(await pageWs());
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  const rt = new Runtime(ws);
  await rt.call("Runtime.enable");
  await rt.call("Page.enable").catch(() => null);
  await navigateCart(rt);

  const scan = await rt.eval(scanCode, 90000);
  if (!scan?.loggedIn) {
    ws.close();
    return { success: false, error: "登录状态异常" };
  }

  const items = scan.items || [];
  const target = items.find(item => Number(item.id) === Number(targetId));
  
  if (!target) {
    ws.close();
    return { 
      success: false, 
      error: "购物车中未找到该ID的商品",
      targetId,
      cartItems: items.map(i => ({ id: i.id, name: i.name, spec: i.spec, provider: i.provider }))
    };
  }

  console.log(`删除 ${target.id} ${target.name} x${target.amount} (${target.provider})`);
  const deleteResult = await deleteOne(rt, target.id);
  await sleep(2500);
  await navigateCart(rt);
  const after = await rt.eval(scanCode, 90000);
  const stillThere = (after.items || []).some(x => Number(x.id) === Number(targetId));
  const ok = deleteResult?.code === "40001" && !stillThere;

  ws.close();
  return { 
    success: ok, 
    target: { id: target.id, name: target.name, spec: target.spec, provider: target.provider },
    response: deleteResult,
    verified: !stillThere
  };
}

(async () => {
  try {
    if (!TARGET_ID) {
      console.log(JSON.stringify({ success: false, error: "请提供商品ID参数" }));
      return;
    }
    const result = await deleteById(TARGET_ID);
    console.log(JSON.stringify(result));
  } catch (error) {
    const errorMsg = error?.message || (typeof error === 'object' ? JSON.stringify(error) : String(error));
    console.log(JSON.stringify({ success: false, error: errorMsg }));
  }
})();