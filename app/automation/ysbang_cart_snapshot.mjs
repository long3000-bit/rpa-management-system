import fs from "node:fs/promises";

const [, , outputPath] = process.argv;
const CDP_URL = process.env.YSBANG_CDP_URL || "http://127.0.0.1:9222";

if (!outputPath) {
  throw new Error("Usage: node ysbang_cart_snapshot.mjs <output.json>");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function findYsbangPage() {
  const pages = await getJson(`${CDP_URL}/json/list`);
  return pages.find((page) => String(page.url || "").includes("dian.ysbang.cn"));
}

class CdpClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.seq = 0;
    this.pending = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
        else resolve(message.result);
      }
    });
  }

  async send(method, params = {}) {
    await this.ready;
    const id = ++this.seq;
    const promise = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    this.ws.send(JSON.stringify({ id, method, params }));
    return promise;
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout: 120000,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
    }
    return result.result?.result?.value ?? result.result?.value;
  }

  close() {
    try {
      this.ws.close();
    } catch {}
  }
}

async function main() {
  const page = await findYsbangPage();
  if (!page?.webSocketDebuggerUrl) {
    throw new Error("YSBang page not found");
  }
  const client = new CdpClient(page.webSocketDebuggerUrl);
  try {
    await client.send("Runtime.enable");
    await client.send("Page.enable").catch(() => null);
    await client.send("Page.navigate", { url: `https://dian.ysbang.cn/?rpaCartSnapshot=${Date.now()}#/cart` }).catch(() => null);
    await sleep(5000);
    const payload = await client.evaluate(`(() => {
      const seenObjects = new WeakSet();
      const rows = [];
      const getVal = (obj, keys) => {
        for (const key of keys) {
          try {
            const value = key.split('.').reduce((current, part) => current?.[part], obj);
            if (value !== undefined && value !== null && String(value) !== '') return value;
          } catch {}
        }
        return '';
      };
      const num = (value) => {
        const n = Number(String(value ?? '').replace(/,/g, '').trim());
        return Number.isFinite(n) ? n : 0;
      };
      const push = (obj) => {
        const id = getVal(obj, [
          'wholesaleId', 'wholesaleid', 'wholeSaleId', 'goodsId', 'drugId',
          'props.wholesaleId', 'props.wholesaleid', 'props.wholeSaleId', 'props.goodsId'
        ]);
        const name = getVal(obj, [
          'drugName', 'drugname', 'name', 'wholesaleDrugName', 'goodsName',
          'props.drugName', 'props.drugname', 'props.name', 'props.wholesaleDrugName'
        ]);
        if (!id || !name || Array.isArray(id) || Array.isArray(name)) return;
        rows.push({
          wholesaleId: String(id),
          name: String(name),
          spec: String(getVal(obj, [
            'specification', 'drugSpecification', 'spec', 'goodsSpec', 'drugSpec',
            'props.specification', 'props.drugSpecification', 'props.spec'
          ]) || ''),
          manufacturer: String(getVal(obj, [
            'manufacturer', 'factory', 'productFactory', 'factoryName', 'drugFactoryName',
            'props.manufacturer', 'props.factory', 'props.productFactory', 'props.factoryName'
          ]) || ''),
          supplier: String(getVal(obj, [
            'providerName', 'provider_name', 'abbreviation', 'sellerName', 'shopName',
            'props.providerName', 'props.provider_name', 'props.abbreviation', 'props.sellerName', 'props.shopName'
          ]) || ''),
          amount: num(getVal(obj, [
            'amount', 'drugAmount', 'count', 'cnt', 'num', 'quantity', 'buyNum', 'goodsNum',
            'props.amount', 'props.drugAmount', 'props.count', 'props.num', 'props.quantity'
          ])),
          price: num(getVal(obj, [
            'price', 'chainPrice', 'showPrice', 'realPrice', 'salePrice', 'unitPrice',
            'props.price', 'props.chainPrice', 'props.showPrice', 'props.realPrice', 'props.salePrice'
          ])),
          validDate: String(getVal(obj, [
            'validDate', 'valid_date', 'validityDate', 'expireDate', 'expiryDate',
            'drugInfo.validDate', '_data.drugInfo.validDate',
            'props.validDate', 'props.drugInfo.validDate'
          ]) || ''),
        });
      };
      const visit = (obj, depth = 0) => {
        if (!obj || typeof obj !== 'object' || depth > 9 || rows.length >= 800) return;
        if (seenObjects.has(obj)) return;
        seenObjects.add(obj);
        try { push(obj); } catch {}
        if (Array.isArray(obj)) {
          for (const value of obj.slice(0, 300)) visit(value, depth + 1);
          return;
        }
        for (const key of Object.keys(obj).slice(0, 160)) {
          try {
            const value = obj[key];
            if (value && typeof value === 'object') visit(value, depth + 1);
          } catch {}
        }
      };
      for (const el of Array.from(document.querySelectorAll('*')).slice(0, 4000)) {
        for (const key of Object.keys(el)) {
          if (key.startsWith('__vue')) visit(el[key], 0);
        }
      }
      const unique = new Map();
      for (const row of rows) {
        if (!row.wholesaleId || !row.name) continue;
        const key = [row.wholesaleId, row.name, row.spec, row.manufacturer, row.supplier, row.amount, row.price].join('|');
        unique.set(key, row);
      }
      const items = Array.from(unique.values())
        .filter((row) => row.amount > 0 || row.price > 0)
        .sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-Hans-CN'));
      return {
        loggedIn: document.documentElement.innerText.includes('退出'),
        url: location.href,
        totalRowsRead: rows.length,
        uniqueItems: items.length,
        items,
      };
    })()`);
    await fs.writeFile(outputPath, JSON.stringify(payload || { items: [] }, null, 2), "utf8");
  } finally {
    client.close();
  }
}

await main();
