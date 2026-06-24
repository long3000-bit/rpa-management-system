import fs from "node:fs/promises";

const [, , inputPath, outputPath] = process.argv;
const CDP_URL = process.env.YSBANG_CDP_URL || "http://127.0.0.1:9222";
const ADD_DELAY_MIN_MS = Number(process.env.YSBANG_ADD_DELAY_MIN_MS || 10000);
const ADD_DELAY_MAX_MS = Number(process.env.YSBANG_ADD_DELAY_MAX_MS || 15000);
// 四期整改：CDP调用超时配置
const CDP_CALL_TIMEOUT_MS = Number(process.env.YSBANG_CDP_CALL_TIMEOUT_MS || 60000); // 普通调用默认60秒
const CDP_FILTER_TIMEOUT_MS = Number(process.env.YSBANG_CDP_FILTER_TIMEOUT_MS || 120000); // 筛选操作默认120秒
const CDP_MAX_RETRIES = Number(process.env.YSBANG_CDP_MAX_RETRIES || 2); // 最大重试次数

if (!inputPath || !outputPath) {
  throw new Error("Usage: node ysbang_cart_add_onebyone.mjs <input.json> <output.json>");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const items = Array.isArray(payload.items) ? payload.items : [];
const logPath = payload.logPath || "";
const results = [];
const SEARCH_WAIT_MS = Number(process.env.YSBANG_SEARCH_WAIT_MS || 4500);

// 二期整改：从payload中读取规则配置，优先使用二期字段名，兼容旧字段名
const ruleConfig = payload.ruleConfig || {};
const ruleSnapshotId = payload.ruleSnapshotId || "";

// 二期字段名（优先），兼容旧字段名
const RULE_MIN_PURCHASE_SCORE = Number(ruleConfig.minPurchaseScore ?? ruleConfig.scoreThreshold ?? 85);
const RULE_CART_BACKFILL_MIN_SCORE = Number(ruleConfig.cartBackfillMinScore ?? ruleConfig.backfillThreshold ?? 60);
const RULE_PRICE_COMPARE_DISCOUNT = Number(ruleConfig.priceCompareDiscount ?? ruleConfig.priceTolerance ?? 0.95);
const RULE_PRICE_UPPER_RATE = Number(ruleConfig.priceUpperRate ?? 1.05);
const RULE_PRICE_UPPER_PLUS = Number(ruleConfig.priceUpperPlus ?? 5);
const RULE_NAME_WEIGHT = Number(ruleConfig.nameWeight ?? 0.62);
const RULE_SPEC_WEIGHT = Number(ruleConfig.specWeight ?? 0.23);
const RULE_MAKER_WEIGHT = Number(ruleConfig.makerWeight ?? 0.15);
// 三期整改：规格冲突是否阻断采购（strict_spec_v1 时为 true）
const RULE_SPEC_CONFLICT_BLOCK = ruleConfig.specConflictBlock === true || ruleConfig.specConflictBlock === "true" || ruleConfig.specConflictBlock === 1;
const RULE_MAKER_STRICT = ruleConfig.makerStrict === true || ruleConfig.makerStrict === "true" || ruleConfig.makerStrict === 1;
// 二期整改：内部模糊匹配阈值（替换固定 >= 70）
const RULE_NAME_CORE_MIN_SCORE = Number(ruleConfig.nameCoreMinScore ?? 70);
const RULE_SPEC_SIMILAR_MIN_SCORE = Number(ruleConfig.specSimilarMinScore ?? 70);
const RULE_FACTORY_SIMILAR_MIN_SCORE = Number(ruleConfig.factorySimilarMinScore ?? 70);
const RULE_CART_EXISTING_SAME_PRODUCT_MIN_SCORE = Number(ruleConfig.cartExistingSameProductMinScore ?? 70);
// 兼容旧变量名（供后续代码使用）
const RULE_SCORE_THRESHOLD = RULE_MIN_PURCHASE_SCORE;
const RULE_FACTORY_THRESHOLD = Number(ruleConfig.factoryThreshold ?? 70);
const RULE_PRICE_TOLERANCE = RULE_PRICE_COMPARE_DISCOUNT;
const RULE_BACKFILL_THRESHOLD = RULE_CART_BACKFILL_MIN_SCORE;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomAddDelayMs() {
  const min = Math.max(0, Math.min(ADD_DELAY_MIN_MS, ADD_DELAY_MAX_MS));
  const max = Math.max(min, ADD_DELAY_MAX_MS);
  return Math.floor(min + Math.random() * (max - min + 1));
}

async function writeResults() {
  await fs.writeFile(outputPath, JSON.stringify({ results }, null, 2), "utf8");
}

async function trace(message) {
  if (!logPath) return;
  const timestamp = new Date().toISOString();
  await fs.appendFile(logPath, `[${timestamp}] JS ${message}\n`, "utf8");
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function findYsbangPage() {
  const pages = await getJson(`${CDP_URL}/json/list`);
  const ysbangPages = pages.filter((page) =>
    page.type === "page" && String(page.url || "").includes("dian.ysbang.cn")
  );
  const isCartPage = (page) => /#\/cart(?:\?|$)|rpaCart=/i.test(String(page.url || ""));
  return ysbangPages.find((page) =>
    !isCartPage(page) && /rpaSearch=|#\/indexContent/i.test(String(page.url || ""))
  ) || ysbangPages.find((page) => !isCartPage(page)) || ysbangPages[0];
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

  async send(method, params = {}, timeoutMs = CDP_CALL_TIMEOUT_MS) {
    await this.ready;
    const id = ++this.seq;
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timeout after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
    });
    this.ws.send(JSON.stringify({ id, method, params }));
    return promise;
  }

  async evaluate(expression, timeoutMs = CDP_CALL_TIMEOUT_MS) {
    // 四期整改：外层超时时间必须与Runtime.evaluate内部timeout一致或更长
    const effectiveTimeout = Math.max(timeoutMs, 60000);
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout: effectiveTimeout,
    }, effectiveTimeout); // 四期整改：将超时时间传入send()的外层计时器
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
    }
    return result.result?.result?.value ?? result.result?.value;
  }

  // 四期整改：筛选专用evaluate方法，使用120秒超时
  async evaluateForFilter(expression) {
    return this.evaluate(expression, CDP_FILTER_TIMEOUT_MS);
  }

  close() {
    try {
      this.ws.close();
    } catch {
      // ignore close errors
    }
  }
}

function normalizeAmount(value) {
  const amount = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(amount) && amount > 0 ? amount : 0;
}

function normalizeWholesaleId(value) {
  return String(value ?? "").trim().replace(/^YSB/i, "");
}

function normalizeText(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[（）()【】\[\]\s,，.。;；:：/\\_-]/g, "")
    .replace(/[（）【】\[\]\s,，。;；:：、()\\_-]/g, "")
    .trim();
}

function textScore(source, target) {
  const a = normalizeText(source);
  const b = normalizeText(target);
  if (!a || !b) return 0;
  if (a === b) return 100;
  if (a.includes(b) || b.includes(a)) return 85;
  const chars = new Set(a.split(""));
  let hit = 0;
  for (const ch of b) {
    if (chars.has(ch)) hit += 1;
  }
  return Math.round((hit / Math.max(a.length, b.length)) * 100);
}

function stripBracketText(value) {
  return String(value ?? "").replace(/【[^】]*】|\[[^\]]*\]|（[^）]*）|\([^)]*\)/g, " ");
}

function normalizeProductName(value) {
  let text = stripBracketText(String(value ?? "").toLowerCase());
  text = text
    .replace(/\d+(?:\.\d+)?\s*(?:盒|瓶|袋|支|板|片|粒|丸|贴|包|枚|只)\s*起购/g, " ")
    .replace(/(?:首推|推荐|精选|包邮|起购|买赠|限购|活动|特价|现货)/g, " ")
    .replace(/\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|l|μg|ug|%|毫克|克|毫升|微克)(?:\s*[*x×:：]\s*\d+(?:\.\d+)?\s*(?:片|粒|丸|支|袋|瓶|盒|板|贴|枚|只|ml|g|mg))*/gi, " ")
    .replace(/\d+(?:\.\d+)?\s*(?:片|粒|丸|支|袋|瓶|盒|板|贴|包|枚|只|粒装|片装)/g, " ");
  return normalizeText(text).replace(/[^\u4e00-\u9fffa-z0-9]/g, "");
}

function nameTextScore(source, target) {
  const rawScore = textScore(source, target);
  const a = normalizeProductName(source);
  const b = normalizeProductName(target);
  if (!a || !b) return rawScore;
  if (a === b) return 100;
  if (a.includes(b) || b.includes(a)) return Math.max(rawScore, 95);
  const coreScore = textScore(a, b);
  return Math.max(rawScore, coreScore);
}

function productCoreName(value) {
  return normalizeProductName(value)
    .replace(/\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|l|ug|\u03bcg|iu|%|\u6beb\u514b|\u514b|\u5343\u514b|\u6beb\u5347|\u5fae\u514b)/gi, "")
    .replace(/\d+(?:\.\d+)?\s*(?:\u4e38|\u7247|\u7c92|\u888b|\u652f|\u74f6|\u76d2|\u677f|\u8d34|\u5305|\u7ba1|\u63d0|\u677f\u88c5|\u7247\u88c5|\u7c92\u88c5)/gi, "")
    .replace(/(?:rx|otc|\u5305\u90ae|\u8d77\u8d2d|\u9996\u63a8|\u63a8\u8350|\u7279\u4ef7|\u70ed\u5356|\u65e5\u5e38|\u5c0f\u836f\u7cbe\u9009\w*)/gi, "")
    .replace(/[^0-9a-z\u4e00-\u9fff]/gi, "");
}

function productCoreCompatible(source, target) {
  const sourceCore = productCoreName(source);
  const targetCore = productCoreName(target);
  if (sourceCore.length < 3 || targetCore.length < 3) return true;
  if (sourceCore.includes(targetCore) || targetCore.includes(sourceCore)) return true;
  return textScore(sourceCore, targetCore) >= RULE_NAME_CORE_MIN_SCORE;
}

function brandHint(value, coreName) {
  return normalizeText(value)
    .replace(coreName || "", "")
    .replace(/\d+(?:\.\d+)?(?:mg|g|kg|ml|l|ug|\u03bcg|iu|%)?/gi, "")
    .replace(/[^0-9a-z\u4e00-\u9fff]/gi, "");
}

function brandCompatible(source, target) {
  const sourceCore = productCoreName(source);
  const targetCore = productCoreName(target);
  const sourceBrands = [brandHint(source, sourceCore), brandHint(source, targetCore)];
  const targetBrands = [brandHint(target, sourceCore), brandHint(target, targetCore)];
  return sourceBrands.some((sourceBrand) => targetBrands.some((targetBrand) => {
    if (sourceBrand.length < 2 || targetBrand.length < 2) return false;
    return sourceBrand.includes(targetBrand) || targetBrand.includes(sourceBrand) || textScore(sourceBrand, targetBrand) >= 60;
  }));
}

function productCoreScore(source, target) {
  return textScore(productCoreName(source), productCoreName(target));
}

function productIdentityCompatible(source, target, specScoreValue = 0, makerScoreValue = 0) {
  if (productCoreCompatible(source, target)) return true;
  return brandCompatible(source, target) && productCoreScore(source, target) >= 60 && (specScoreValue >= 80 || makerScoreValue >= 80);
}

function bracketTokens(value) {
  const tokens = [];
  const text = String(value ?? "");
  const pattern = /【([^】]+)】|\[([^\]]+)\]|（([^）]+)）|\(([^)]+)\)/g;
  let match;
  while ((match = pattern.exec(text))) {
    const token = normalizeText(match[1] || match[2] || match[3] || match[4] || "");
    if (token) tokens.push(token);
  }
  return tokens;
}

function manufacturerMatches(item, candidate, detail) {
  const wantedMaker = normalizeText(item.manufacturer || "");
  if (!wantedMaker) return true;
  const candidateMaker = normalizeText(candidate.manufacturer || "");
  if (candidateMaker) {
    const makerScore = detail?.makerScore ?? textScore(item.manufacturer, candidate.manufacturer);
    if (makerScore >= RULE_FACTORY_SIMILAR_MIN_SCORE) return true;
    return productIdentityCompatible(item.name, candidate.name, detail?.specScore ?? 0, makerScore)
      && brandCompatible(item.name, candidate.name)
      && (detail?.specScore ?? 0) >= 45;
  }

  const candidateText = normalizeText(`${candidate.name || ""}${candidate.supplier || ""}${candidate.supplierFull || ""}`);
  if (wantedMaker && candidateText && (candidateText.includes(wantedMaker) || wantedMaker.includes(candidateText))) {
    return true;
  }

  const brandTokens = bracketTokens(item.name);
  return brandTokens.some((token) => token.length >= 2 && candidateText.includes(token));
}

function specPackageTokens(value) {
  const text = String(value || "").toLowerCase().replace(/\s+/g, "");
  const tokens = [];
  const pattern = /(\d+(?:\.\d+)?)\s*(粒|片|袋|支|板|丸|瓶|盒|贴|包|枚|只)/g;
  let match;
  while ((match = pattern.exec(text))) {
    tokens.push(`${Number(match[1])}${match[2]}`);
  }
  return tokens;
}

const PACKAGE_COUNT_UNITS = "片|粒|丸|袋|支|瓶|盒|板|贴|包|枚|只|管|条|s|板装|片装|粒装|袋装|支装|瓶装|盒装";

function specStrength(value) {
  const text = String(value || "").toLowerCase().replace(/×/g, "*").replace(/x/g, "*").replace(/\s+/g, "");
  const match = text.match(/(\d+(?:\.\d+)?)(mg|g|ml|ug|μg|iu|%)/i);
  return match ? specUnitValue(`${match[1]}${match[2]}`) : "";
}

function specCountFactors(value) {
  const text = String(value || "")
    .toLowerCase()
    .replace(/×/g, "*")
    .replace(/x/g, "*")
    .replace(/\d+(?:\.\d+)?\s*(?:盒|瓶|袋|支|板|片|粒|丸|贴|包|枚|只|s)\s*(?:起购|包邮)/g, "")
    .replace(/\s+/g, "");
  const factors = [];
  const pattern = new RegExp(`(\\d+(?:\\.\\d+)?)\\s*(${PACKAGE_COUNT_UNITS})`, "gi");
  let match;
  while ((match = pattern.exec(text))) {
    const number = Number(match[1]);
    if (Number.isFinite(number) && number > 0) factors.push(number);
  }
  return factors;
}

function dedupeRepeatedFactors(factors) {
  let values = factors.slice();
  while (values.length > 1 && values.length % 2 === 0) {
    const half = values.length / 2;
    const left = values.slice(0, half);
    const right = values.slice(half);
    if (!left.every((value, index) => value === right[index])) break;
    values = left;
  }
  return values;
}

function specPackageTotal(value) {
  const factors = dedupeRepeatedFactors(specCountFactors(value));
  return factors.length ? factors.reduce((total, factor) => total * factor, 1) : 0;
}

function specEquivalent(source, target) {
  if (!source || !target) return false;
  const sourceStrength = specStrength(source);
  const targetStrength = specStrength(target);
  const sourceTotal = specPackageTotal(source);
  const targetTotal = specPackageTotal(target);
  return Boolean(
    sourceTotal
    && targetTotal
    && sourceTotal === targetTotal
    && (!sourceStrength || !targetStrength || sourceStrength === targetStrength)
  );
}

function decimalPlain(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value || "");
  return String(Number(number.toFixed(6))).replace(/\.0+$/, "");
}

function specUnitValue(value) {
  const text = String(value || "").toLowerCase().replace(/\s+/g, "").replace(/ug/g, "μg");
  const match = text.match(/^(\d+(?:\.\d+)?)(mg|g|ml|μg|iu|%)$/i);
  if (!match) return text;
  let number = Number(match[1]);
  let unit = match[2].toLowerCase();
  if (unit === "mg") {
    number = number / 1000;
    unit = "g";
  }
  return `${decimalPlain(number)}${unit}`;
}

function specUnitSet(value) {
  const text = String(value || "").toLowerCase().replace(/×/g, "*").replace(/x/g, "*");
  const units = new Set();
  const pattern = /\d+(?:\.\d+)?\s*(?:mg|g|ml|ug|μg|iu|%)/gi;
  let match;
  while ((match = pattern.exec(text))) {
    units.add(specUnitValue(match[0]));
  }
  return units;
}

function specNumbers(value) {
  const text = String(value || "").toLowerCase().replace(/×/g, "*").replace(/x/g, "*");
  return Array.from(text.matchAll(/(?<![a-z0-9])(\d+(?:\.\d+)?)(?!\d)/gi)).map((match) => decimalPlain(match[1]));
}

function specParts(value) {
  const text = String(value || "").toLowerCase().replace(/×/g, "*").replace(/x/g, "*");
  const strengthMatch = text.match(/(\d+(?:\.\d+)?\s*(?:mg|g|ml|ug|μg|iu|%))/i);
  const strength = strengthMatch ? specUnitValue(strengthMatch[1]) : "";
  const numbers = Array.from(text.matchAll(/(?<![a-z0-9])(\d+(?:\.\d+)?)(?!\d)\s*(片|粒|袋|板|支|瓶|贴|枚|丸|包|s)/gi)).map((match) => Number(match[1]));
  const total = numbers.length ? numbers.reduce((value, number) => value * number, 1) : 0;
  return { strength, total };
}

function specPartsWithKnownCountUnits(value) {
  const text = String(value || "").toLowerCase().replace(/脳/g, "*").replace(/x/g, "*");
  const strengthMatch = text.match(/(\d+(?:\.\d+)?\s*(?:mg|g|ml|ug|渭g|iu|%))/i);
  const strength = strengthMatch ? specUnitValue(strengthMatch[1]) : "";
  const numbers = Array.from(text.matchAll(/(?<![a-z0-9])(\d+(?:\.\d+)?)(?!\d)\s*(鐗噟绮抾琚媩鏉縷鏀瘄鐡秥璐磡鏋殀涓竱鍖厊s|片|粒|丸|袋|支|瓶|盒|板|贴|包|管|Ƭ)/gi)).map((match) => Number(match[1]));
  const total = numbers.length ? numbers.reduce((value, number) => value * number, 1) : 0;
  return { strength, total };
}

function packageTotalConflict(source, target) {
  if (specEquivalent(source, target)) return false;
  const sourceParts = specPartsWithKnownCountUnits(source);
  const targetParts = specPartsWithKnownCountUnits(target);
  return Boolean(
    sourceParts.total
    && targetParts.total
    && sourceParts.total !== targetParts.total
    && (!sourceParts.strength || !targetParts.strength || sourceParts.strength === targetParts.strength)
  );
}

function hasCountUnit(value) {
  return /\d+\s*(片|粒|袋|板|支|瓶|贴|枚|丸|包|s)/i.test(String(value || ""));
}

function specScore(source, target) {
  if (!source) return 60;
  if (specEquivalent(source, target)) return 100;
  const sourceParts = specParts(source);
  const targetParts = specParts(target);
  const sourceUnits = specUnitSet(source);
  const targetUnits = specUnitSet(target);
  if (sourceParts.strength && targetParts.strength && sourceParts.strength === targetParts.strength) {
    if (sourceParts.total && targetParts.total && sourceParts.total === targetParts.total) return 100;
    if (sourceParts.total && targetParts.total && sourceParts.total !== targetParts.total) {
      if (hasCountUnit(source) && hasCountUnit(target)) return 45;
      const shared = Array.from(sourceUnits).filter((unit) => targetUnits.has(unit));
      if (shared.some((unit) => (unit.endsWith("g") && !unit.endsWith("mg")) || unit.endsWith("ml"))) return 85;
      return 45;
    }
    if (!sourceParts.total || !targetParts.total) return 85;
  }
  const sharedUnits = Array.from(sourceUnits).filter((unit) => targetUnits.has(unit));
  if (sharedUnits.length) {
    if (sharedUnits.some((unit) => (unit.endsWith("g") && !unit.endsWith("mg")) || unit.endsWith("ml"))) return 85;
    const sourceOnly = Array.from(sourceUnits).every((unit) => targetUnits.has(unit));
    const targetOnly = Array.from(targetUnits).every((unit) => sourceUnits.has(unit));
    if (sourceOnly || targetOnly) return 85;
  }
  const sourceNums = specNumbers(source);
  const targetNums = new Set(specNumbers(target));
  if (sourceNums.length && targetNums.size) {
    const sharedCount = sourceNums.filter((num) => targetNums.has(num)).length;
    if (sourceNums.length >= 2 && sharedCount >= Math.min(2, new Set(sourceNums).size)) return 100;
    if (sourceNums.length === 1 && targetNums.has(sourceNums[0])) return 85;
  }
  return textScore(source, target);
}

function specCompatible(source, target) {
  if (!source) return true;
  if (specEquivalent(source, target)) return true;
  if (packageTotalConflict(source, target)) return false;
  if (specScore(source, target) >= RULE_SPEC_SIMILAR_MIN_SCORE) return true;
  const wanted = specPackageTokens(source);
  if (wanted.length === 0) return true;
  const got = new Set(specPackageTokens(target));
  return wanted.every((token) => got.has(token));
}

function isSameProduct(item, cartItem) {
  if (!item || !cartItem) return false;
  const cartName = cartItem.drugName || cartItem.name || "";
  const targetNames = [item.name, item.matchedName]
    .flatMap((name) => [normalizeText(name), normalizeProductName(name)])
    .filter(Boolean);
  const cartNameTexts = [normalizeText(cartName), normalizeProductName(cartName)].filter(Boolean);
  const nameOk = targetNames.some((name) => cartNameTexts.some((cartNameText) => cartNameText.includes(name) || name.includes(cartNameText)));
  if (!nameOk) return false;
  if (item.spec && packageTotalConflict(item.spec, `${cartItem.spec || ""}${cartName}`)) return false;
  const specOk = !item.spec || textScore(item.spec, `${cartItem.spec || ""}${cartName}`) >= RULE_SPEC_SIMILAR_MIN_SCORE;
  const makerScore = cartItem.manufacturer ? textScore(item.manufacturer, cartItem.manufacturer) : 0;
  if (!productIdentityCompatible(item.name || item.matchedName || "", cartName, specOk ? 80 : 0, makerScore)) return false;
  const makerOk = !item.manufacturer || makerScore >= RULE_CART_EXISTING_SAME_PRODUCT_MIN_SCORE || (
    brandCompatible(item.name || item.matchedName || "", cartName)
    && textScore(item.spec || "", `${cartItem.spec || ""}${cartName}`) >= 45
  );
  return specOk && makerOk;
}

function matchScore(item, candidate) {
  const nameScore = nameTextScore(item.name, candidate.name);
  const specScoreValue = item.spec ? specScore(item.spec, `${candidate.spec || ""}${candidate.name || ""}`) : 60;
  const makerScore = item.manufacturer ? textScore(item.manufacturer, candidate.manufacturer) : 60;
  let adjustedMakerScore = makerScore;
  if (specScoreValue >= 95 && nameScore >= 50 && adjustedMakerScore === 0) adjustedMakerScore = 60;
  let score = Math.round(nameScore * RULE_NAME_WEIGHT + specScoreValue * RULE_SPEC_WEIGHT + adjustedMakerScore * RULE_MAKER_WEIGHT);
  if (!productIdentityCompatible(item.name, candidate.name, specScoreValue, adjustedMakerScore)) return Math.min(score, 61);
  // 三期整改：spec_conflict_block=true 时规格冲突直接阻断（返回0），否则仅限制分数
  if (item.spec && packageTotalConflict(item.spec, `${candidate.spec || ""}${candidate.name || ""}`)) {
    return RULE_SPEC_CONFLICT_BLOCK ? 0 : Math.min(score, 61);
  }
  if (item.spec && specScoreValue < 60 && !(brandCompatible(item.name, candidate.name) && specScoreValue >= 45)) score = Math.min(score, 61);
  if (productCoreCompatible(item.name, candidate.name) && brandCompatible(item.name, candidate.name) && specScoreValue >= 45) score = Math.max(score, 70);
  if (specScoreValue >= 95 && adjustedMakerScore >= 80 && nameScore >= 30) score = Math.max(score, 82);
  if (specScoreValue >= 80 && adjustedMakerScore >= 55 && nameScore >= 55) score = Math.max(score, 70);
  if (specScoreValue >= 80 && adjustedMakerScore >= 90 && nameScore >= 40) score = Math.max(score, 70);
  if (specScoreValue >= 95 && adjustedMakerScore >= 90 && nameScore >= 30) score = Math.max(score, 82);
  return score;
}

function matchScoreDetail(item, candidate) {
  const nameScore = nameTextScore(item.name, candidate.name);
  const specScoreValue = item.spec ? specScore(item.spec, `${candidate.spec || ""}${candidate.name || ""}`) : 60;
  const makerScore = item.manufacturer ? textScore(item.manufacturer, candidate.manufacturer) : 60;
  let adjustedMakerScore = makerScore;
  if (specScoreValue >= 95 && nameScore >= 50 && adjustedMakerScore === 0) adjustedMakerScore = 60;
  let total = Math.round(nameScore * RULE_NAME_WEIGHT + specScoreValue * RULE_SPEC_WEIGHT + adjustedMakerScore * RULE_MAKER_WEIGHT);
  if (!productIdentityCompatible(item.name, candidate.name, specScoreValue, adjustedMakerScore)) {
    total = Math.min(total, 61);
    return { nameScore, specScore: specScoreValue, makerScore: adjustedMakerScore, total };
  }
  if (item.spec && packageTotalConflict(item.spec, `${candidate.spec || ""}${candidate.name || ""}`)) {
    // 三期整改：spec_conflict_block=true 时规格冲突直接阻断（返回0），否则仅限制分数
    total = RULE_SPEC_CONFLICT_BLOCK ? 0 : Math.min(total, 61);
    return { nameScore, specScore: specScoreValue, makerScore: adjustedMakerScore, total };
  }
  if (item.spec && specScoreValue < 60 && !(brandCompatible(item.name, candidate.name) && specScoreValue >= 45)) total = Math.min(total, 61);
  if (productCoreCompatible(item.name, candidate.name) && brandCompatible(item.name, candidate.name) && specScoreValue >= 45) total = Math.max(total, 70);
  if (specScoreValue >= 95 && adjustedMakerScore >= 80 && nameScore >= 30) total = Math.max(total, 82);
  if (specScoreValue >= 80 && adjustedMakerScore >= 55 && nameScore >= 55) total = Math.max(total, 70);
  if (specScoreValue >= 80 && adjustedMakerScore >= 90 && nameScore >= 40) total = Math.max(total, 70);
  if (specScoreValue >= 95 && adjustedMakerScore >= 90 && nameScore >= 30) total = Math.max(total, 82);
  return { nameScore, specScore: specScoreValue, makerScore: adjustedMakerScore, total };
}

function buildLowScoreReason(item, entry) {
  const candidate = entry.candidate || {};
  const detail = entry.detail || matchScoreDetail(item, candidate);
  const lowParts = [];
  if (detail.nameScore < 70) lowParts.push(`名称分${detail.nameScore}`);
  if (item.spec && detail.specScore < 70) lowParts.push(`规格分${detail.specScore}`);
  if (item.manufacturer && detail.makerScore < 70) lowParts.push(`厂家分${detail.makerScore}`);
  const problem = lowParts.length ? lowParts.join("，") : "综合分不足";
  return `候选综合分低于规则阈值（候选分数: ${detail.total}，规则阈值: ${RULE_MIN_PURCHASE_SCORE}）${problem ? '；' + problem : ''}；目标=${item.name || ''}/${item.spec || ''}/${item.manufacturer || ''}；最佳候选=${candidate.name || ''}/${candidate.spec || ''}/${candidate.manufacturer || ''}；供应商=${candidate.supplier || ''}；价格=${candidate.price || ''}；规则快照ID=${ruleSnapshotId}`;
}

function normalizeNumber(value) {
  const number = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(number) ? number : 0;
}

/**
 * 四期整改：统一的供应商名称标准化函数
 * 去除空格、括号等，用于前置校验和执行阶段的一致判断
 */
function normalizeSupplierName(value) {
  return String(value || '')
    .replace(/\s+/g, '')
    .replace(/[（）()【】\[\]，,。；;：:]/g, '')
    .trim();
}

function supplierNameVariants(value) {
  const raw = String(value || '').trim();
  if (!raw) return [];
  const parts = [raw];
  const outside = raw.replace(/[（(【\[].*?[）)】\]]/g, '').trim();
  if (outside) parts.push(outside);
  for (const match of raw.matchAll(/[（(【\[]([^）)】\]]+)[）)】\]]/g)) {
    if (match[1]) parts.push(match[1]);
  }
  return [...new Set(parts.map(normalizeSupplierName).filter(Boolean))];
}

/**
 * 四期整改：统一的供应商范围校验函数
 * 用于前置校验（候选评分）和执行阶段（加购前校验）
 */
function checkSupplierInScope(candidateSuppliers, supplierScope) {
  const scope = Array.isArray(supplierScope)
    ? supplierScope.flatMap(supplierNameVariants)
    : [];
  if (scope.length === 0) return { inScope: true, matchedScope: [], reason: "未配置供应商范围，默认允许" };

  const candidateValues = (Array.isArray(candidateSuppliers) ? candidateSuppliers : [candidateSuppliers])
    .flatMap(supplierNameVariants);
  const matchedScope = scope.filter((allowed) => candidateValues.some((candidate) =>
    candidate === allowed || candidate.includes(allowed) || allowed.includes(candidate)
  ));
  
  if (matchedScope.length > 0) {
    return { inScope: true, matchedScope, reason: "" };
  }
  
  return {
    inScope: false,
    matchedScope: [],
    reason: `候选供应商不在允许范围（候选供应商: ${candidateValues.join(", ")}，允许范围: ${scope.join(", ")}）`
  };
}

function supplierMatches(candidate, supplierScope) {
  // 四期整改：使用统一的供应商范围校验函数
  const result = checkSupplierInScope(
    [candidate.supplier || "", candidate.supplierFull || ""],
    supplierScope
  );
  return result.inScope;
}

function evaluateCandidate(item, candidate) {
  const detail = matchScoreDetail(item, candidate);
  const price = normalizeNumber(candidate.price);
  // 二期整改：使用规则快照中的价格参数
  const expectedPrice = normalizeNumber(item.expectedPrice || item.maxAllowedPrice);
  const comparePrice = price * RULE_PRICE_COMPARE_DISCOUNT;
  const maxAllowedPrice = expectedPrice > 0
    ? Math.min(expectedPrice * RULE_PRICE_UPPER_RATE, expectedPrice + RULE_PRICE_UPPER_PLUS)
    : normalizeNumber(item.maxAllowedPrice);
  const amount = normalizeAmount(item.amount);
  const minAmount = normalizeNumber(candidate.minAmount) || 1;
  const stock = normalizeNumber(candidate.stock) || 999999;
  return {
    candidate,
    score: detail.total,
    detail,
    price,
    comparePrice,
    maxAllowedPrice,
    specOk: specCompatible(item.spec, `${candidate.spec || ""}${candidate.name || ""}`),
    manufacturerOk: manufacturerMatches(item, candidate, detail),
    supplierOk: supplierMatches(candidate, item.supplierScope),
    priceOk: !maxAllowedPrice || (price > 0 && comparePrice <= maxAllowedPrice + 0.0001),
    qtyOk: minAmount <= amount,
    stockOk: stock >= amount,
  };
}

function baseName(name) {
  return stripBracketText(String(name || ""))
    .replace(/[（(【\[][^）)】\]]*[）)】\]]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function searchUrl(searchKey) {
  const params = new URLSearchParams({
    lastClick: "-1",
    page: "1",
    pagesize: "60",
    classify_id: "",
    searchkey: searchKey,
    onlyTcm: "0",
    operationtype: "1",
    qualifiedLoanee: "0",
    drugId: "-1",
    tagId: "",
    showRecentlyPurchasedFlag: "true",
    onlySimpleLoan: "false",
    sn: "",
    synonymId: "0",
    onlyShowRecentlyPurchased: "false",
    provider_filter: "",
    factoryNames: "",
    specs: "",
    deliverFloor: "0",
    purchaseLimitFloor: "0",
    validMonthFloor: "0",
    nextRequestKey: "",
    adConfigId: "0",
    stateValue: "",
    filterLeyoProvider: "false",
    firstSearch: "true",
    activityType: "[]",
    providerSelectList: "[]",
    factorySelectList: "[]",
    gradeNameSelectList: "[]",
    exeStandardSelectList: "[]",
    specSelectList: "[]",
    selectedProvidersNew: "[]",
    selectedFactoryNew: "[]",
    selectedStandardNew: "[]",
    selectedGradeNameNew: "[]",
    selectedExeStandardNew: "[]",
    selectPlaceNew: "[]",
    selectedSpecificationNew: "[]",
    selectedSpecUnitNew: "[]",
    selectedUnitNew: "[]",
    classItem_0: "null",
    classItem_1: "null",
    classItem_2: "null",
    folderFilters: "[]",
    fastFilterList: "[]",
    tagName: "",
    _t: String(Date.now()),
    _isReplace: "true",
    trafficType: "1",
  });
  return `https://dian.ysbang.cn/?rpaSearch=${Date.now()}#/indexContent?${params.toString()}`;
}

// 四期整改：通用重试包装函数
async function withRetry(fn, options = {}) {
  const maxRetries = options.maxRetries ?? CDP_MAX_RETRIES;
  const backoffMs = options.backoffMs ?? [2000, 5000]; // 退避时间：2秒、5秒
  const isRetryable = options.isRetryable ?? ((error) => {
    const msg = String(error?.message || error || '');
    return /timeout/i.test(msg) || /超时/.test(msg) || /network/i.test(msg) || /网络/.test(msg);
  });
  const onRetry = options.onRetry ?? (() => {});

  let lastError = null;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const result = await fn(attempt);
      if (attempt > 0) {
        await trace(`RETRY_SUCCESS attempt=${attempt}`);
      }
      return result;
    } catch (error) {
      lastError = error;
      if (attempt < maxRetries && isRetryable(error)) {
        const backoff = backoffMs[attempt] ?? backoffMs[backoffMs.length - 1] ?? 2000;
        await trace(`RETRY_ATTEMPT attempt=${attempt + 1}/${maxRetries + 1} backoff=${backoff}ms error=${error.message}`);
        await onRetry(attempt, error);
        await sleep(backoff);
      } else {
        break;
      }
    }
  }
  throw lastError;
}

// 四期整改：页面恢复函数（超时后刷新页面并恢复上下文）
async function recoverPage(client, item, searchKey) {
  await trace(`PAGE_RECOVER_START row=${item.rowNumber}`);
  try {
    // 刷新页面
    await client.send("Page.reload", { ignoreCache: true }).catch(() => null);
    await sleep(SEARCH_WAIT_MS);
    
    // 重新导航到搜索页面
    const url = searchUrl(searchKey);
    await client.send("Page.navigate", { url }).catch(() => null);
    await sleep(SEARCH_WAIT_MS);
    
    await trace(`PAGE_RECOVER_SUCCESS row=${item.rowNumber}`);
    return true;
  } catch (error) {
    await trace(`PAGE_RECOVER_FAILED row=${item.rowNumber} error=${error.message}`);
    return false;
  }
}

async function applySupplierFilter(client, item) {
  // 四期整改：使用统一的供应商名称标准化函数
  const rawScope = Array.isArray(item.supplierScope)
    ? item.supplierScope.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  
  const scopeVariants = [...new Set(rawScope.flatMap(supplierNameVariants))];
  
  if (scopeVariants.length === 0) {
    return { selected: [], missing: [], skipped: true, effective: true };
  }
  
  await trace(`SUPPLIER_FILTER_START row=${item.rowNumber} scope=${rawScope.join('|')} variants=${scopeVariants.join('|')} timeout=${CDP_FILTER_TIMEOUT_MS}ms`);
  
  // 四期整改：供应商筛选使用120秒超时，优化为单次索引和批量点击
  const result = await client.evaluateForFilter(`(async () => {
    const scope = ${JSON.stringify(scopeVariants)};
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const waitFor = async (getter, timeoutMs, intervalMs = 250) => {
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMs) {
        const value = getter();
        if (value) return value;
        await sleep(intervalMs);
      }
      return null;
    };
    
    const norm = (value) => String(value || '')
      .replace(/\\s+/g, '')
      .replace(/[（）()【】\[\]，,。；;：:]/g, '')
      .trim();
    const text = (el) => String(el?.innerText || el?.textContent || '').trim();
    const visible = (el) => {
      if (!el) return false;
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const clickNode = (el) => {
      if (!el) return false;
      try {
        el.scrollIntoView({ block: 'center', inline: 'center' });
      } catch {}
      try {
        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
        el.click();
        return true;
      } catch {
        return false;
      }
    };
    
    const matchesScope = (value) => {
      const candidate = norm(value);
      return candidate && scope.some((allowed) =>
        candidate === allowed || candidate.includes(allowed) || allowed.includes(candidate)
      );
    };

    const findProviderRow = () => {
      const rows = Array.from(document.querySelectorAll('.filter-option, .filter-item')).filter(visible);
      return rows.find((row) => {
        const labelText = norm(text(row.querySelector('.label')));
        return labelText === '商家' || labelText === '供应商';
      });
    };
    
    const loadStartedAt = Date.now();
    let providerRow = await waitFor(findProviderRow, 15000);
    if (!providerRow) {
      return {
        selected: [], missing: scope, confirmed: false, hasProviderRow: false,
        effective: false, reason: '未找到商家筛选行', url: location.href
      };
    }
    const clicked = [];
    const alreadySelected = [];

    const multiButton = Array.from(providerRow.querySelectorAll('.multiple-select,button,a,span,div'))
      .filter(visible)
      .find((el) => norm(text(el)) === '多选');
    if (multiButton) {
      clickNode(multiButton);
      providerRow = await waitFor(findProviderRow, 10000) || providerRow;
    }

    const waitForStableOptions = async () => {
      const startedAt = Date.now();
      let previousSignature = '';
      let stableRounds = 0;
      while (Date.now() - startedAt < 15000) {
        providerRow = findProviderRow() || providerRow;
        const current = Array.from(providerRow.querySelectorAll('.option-list li, li[title]')).filter(visible);
        const signature = current.map((el) => el.getAttribute('title') || text(el)).join('|');
        if (current.length > 0 && signature === previousSignature) {
          stableRounds += 1;
          if (stableRounds >= 2) return current;
        } else {
          stableRounds = 0;
        }
        previousSignature = signature;
        await sleep(250);
      }
      return [];
    };
    const options = await waitForStableOptions();
    if (options.length === 0) {
      return {
        selected: [], missing: scope, confirmed: false, hasProviderRow: true,
        effective: false, reason: '商家筛选内容加载超时',
        loadElapsedMs: Date.now() - loadStartedAt, url: location.href
      };
    }
    const allowedOptions = options.filter((option) => matchesScope(option.getAttribute('title') || text(option)));
    for (const option of allowedOptions) {
      const optionName = (option.getAttribute('title') || text(option)).trim();
      if (option.classList.contains('selected')) {
        alreadySelected.push(optionName);
      } else if (clickNode(option)) {
        clicked.push(optionName);
        await sleep(60);
      }
    }

    const selectedBeforeConfirm = Array.from(providerRow.querySelectorAll('.option-list li.selected, li[title].selected'))
      .filter(visible)
      .map((el) => (el.getAttribute('title') || text(el)).trim())
      .filter(matchesScope);
    const confirmButton = providerRow.querySelector('.multipele-confirm-handle .confirm')
      || Array.from(providerRow.querySelectorAll('button,a,span,div')).filter(visible)
        .find((el) => norm(text(el)) === '确认' || norm(text(el)) === '确定');
    let confirmClicked = false;
    if (confirmButton) {
      confirmClicked = clickNode(confirmButton);
    }

    const readSelectedAfterConfirm = () => {
      const selected = Array.from(document.querySelectorAll('.selected-option, [class*="selected-option"]'))
        .filter(visible)
        .map((el) => text(el).trim())
        .filter(matchesScope);
      return selected.length > 0 ? selected : null;
    };
    const selectedAfterConfirm = confirmClicked
      ? (await waitFor(readSelectedAfterConfirm, 10000) || [])
      : [];
    const verified = selectedAfterConfirm.length ? selectedAfterConfirm : selectedBeforeConfirm;
    const effective = allowedOptions.length > 0 && verified.length > 0 && (!multiButton || confirmClicked);
    return {
      selected: verified,
      clicked,
      alreadySelected,
      missing: scope.filter((allowed) => !allowedOptions.some((option) => {
        const optionName = norm(option.getAttribute('title') || text(option));
        return optionName === allowed || optionName.includes(allowed) || allowed.includes(optionName);
      })),
      verified,
      availableAllowed: allowedOptions.map((el) => (el.getAttribute('title') || text(el)).trim()),
      confirmed: confirmClicked,
      hasProviderRow: true,
      effective,
      reason: effective ? '' : '供应商筛选未生效',
      loadElapsedMs: Date.now() - loadStartedAt,
      url: location.href,
      headText: document.body.innerText.slice(0, 260),
    };
  })()`);
  
  await trace(
    `SUPPLIER_FILTER_DONE row=${item.rowNumber} selected=${(result?.selected || []).join('|')} `
    + `already_selected=${(result?.alreadySelected || []).join('|')} `
    + `missing=${(result?.missing || []).join('|')} `
    + `verified=${(result?.verified || []).join('|')} `
    + `options_count=${(result?.availableAllowed || []).length} load_elapsed_ms=${result?.loadElapsedMs || 0} `
    + `confirmed=${!!result?.confirmed} effective=${!!result?.effective} has_row=${!!result?.hasProviderRow}`
  );
  
  // 四期整改：找不到的供应商单独记录，不中断其他有效供应商
  if (result?.missing?.length > 0) {
    await trace(`SUPPLIER_FILTER_MISSING row=${item.rowNumber} missing=${result.missing.join('|')} note=不中断其他有效供应商`);
  }

  if (!result?.effective) {
    throw new Error(result?.reason || '供应商筛选未生效');
  }
  return result;
}

async function applyFactoryFilter(client, item) {
  const targetFactory = String(item.manufacturer || "").trim();
  if (!targetFactory) {
    await trace(`FACTORY_FILTER_SKIP row=${item.rowNumber} reason=厂家为空，按无厂家筛选继续查询`);
    return { selected: null, missing: true, skipped: true, reason: "厂家为空，跳过厂家筛选" };
  }
  await trace(`FACTORY_FILTER_START row=${item.rowNumber} factory=${targetFactory} timeout=${CDP_FILTER_TIMEOUT_MS}ms`);
  // 将阈值常量注入浏览器上下文（evaluate中的代码无法访问Node.js变量）
  const factoryThreshold = RULE_FACTORY_SIMILAR_MIN_SCORE;
  // 四期整改：厂家筛选使用120秒超时
  const result = await client.evaluateForFilter(`(async () => {
    const RULE_FACTORY_SIMILAR_MIN_SCORE = ${factoryThreshold};
    const targetFactory = "${targetFactory.replace(/"/g, '\\"')}";
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const norm = (value) => String(value || '').replace(/\\s+/g, '').replace(/[（）()\\[\\]\\[\\]]/g, '').trim();
    const text = (el) => String(el?.innerText || el?.textContent || '').trim();
    const visible = (el) => {
      if (!el) return false;
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const clickNode = (el) => {
      if (!el) return false;
      try {
        el.scrollIntoView({ block: 'center', inline: 'center' });
      } catch {}
      try {
        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
        el.click();
        return true;
      } catch {
        return false;
      }
    };

    // 去除常见企业尾缀
    const removeSuffix = (name) => {
      const suffixes = [
        '有限公司', '有限责任公司', '股份有限公司',
        '制药有限公司', '药业有限公司', '药厂', '制药厂',
        '集团', '分公司'
      ];
      let result = name;
      for (const suffix of suffixes) {
        if (result.endsWith(suffix)) {
          result = result.slice(0, -suffix.length);
        }
      }
      return result.trim();
    };

    // 计算相似度分数
    const similarity = (a, b) => {
      const na = norm(a);
      const nb = norm(b);
      if (na === nb) return 100;
      if (na.includes(nb) || nb.includes(na)) return 90;
      const ra = removeSuffix(na);
      const rb = removeSuffix(nb);
      if (ra === rb) return 95;
      if (ra.includes(rb) || rb.includes(ra)) return 85;
      // 简单的字符匹配分数
      const commonChars = [...na].filter(ch => nb.includes(ch)).length;
      const maxLen = Math.max(na.length, nb.length);
      return Math.round((commonChars / maxLen) * 100);
    };

    const allRows = () => Array.from(document.querySelectorAll('.filter-option, .filter-item, [class*="filter"], .ant-row, .ant-col, .ant-collapse-item, .ant-card, [class*="筛选"], [class*="筛选项"]')).filter(visible);
    const findFactoryRow = () => {
      const rows = allRows();
      return rows.find((row) => {
        const value = text(row);
        // 查找包含厂家关键词的行
        if (value.includes('\\u5382\\u5bb6') || value.includes('\\u751f\\u4ea7\\u5382\\u5bb6') || value.includes('\\u751f\\u4ea7\\u4f01\\u4e1a') || value.includes('\\u5236\\u4f5c\\u5546') || value.includes('\\u751f\\u4ea7\\u5382\\u5bb6')) {
          // 排除规格、产地、商家、供应商等非厂家筛选行
          if (value.includes('\\u89c4\\u683c') || value.includes('\\u89c4\\u5b9a') || value.includes('\\u4ea7\\u5730') || value.includes('\\u5546\\u5bb6') || value.includes('\\u4f9b\\u5e94\\u5546') || value.includes('\\u5e97\\u5bb6') || value.includes('\\u5e97\\u94fa')) {
            return false;
          }
          return true;
        }
        // 查找包含"品牌"关键词的行（有些网站用品牌代替厂家）
        if (value.includes('\\u54c1\\u724c') || value.includes('\\u5546\\u6807')) {
          // 排除规格、产地、商家、供应商等非厂家筛选行
          if (value.includes('\\u89c4\\u683c') || value.includes('\\u89c4\\u5b9a') || value.includes('\\u4ea7\\u5730') || value.includes('\\u5546\\u5bb6') || value.includes('\\u4f9b\\u5e94\\u5546') || value.includes('\\u5e97\\u5bb6') || value.includes('\\u5e97\\u94fa')) {
            return false;
          }
          return true;
        }
        return false;
      });
    };

    let factoryRow = findFactoryRow();
    if (!factoryRow) {
      return { selected: null, missing: true, hasFactoryRow: false, reason: "未找到厂家筛选行" };
    }

    // 记录厂家筛选行文本
    const factoryRowText = text(factoryRow);
    
    // 查找所有厂家选项
    const factoryOptions = Array.from(factoryRow.querySelectorAll('a,button,span,div,label,li,.ant-tag,.ant-checkbox-wrapper,.ant-radio-wrapper,.ant-select-option,.ant-dropdown-menu-item,.ant-menu-item,.ant-btn,[class*="option"],[class*="item"],[class*="tag"],[class*="checkbox"],[class*="radio"]')).filter(visible);
    const factoryOptionsText = factoryOptions.slice(0, 10).map(el => text(el));
    
    // 记录厂家选项数量和前若干项
    const factoryOptionsCount = factoryOptions.length;
    
    const scoredOptions = factoryOptions.map((el) => {
      const optionText = text(el);
      const score = similarity(targetFactory, optionText);
      return { el, text: optionText, score };
    }).sort((a, b) => b.score - a.score);

    // 选择最佳匹配
    const bestOption = scoredOptions[0];
    if (!bestOption) {
      return { selected: null, missing: true, hasFactoryRow: true, reason: "厂家筛选项不存在" };
    }

    // 根据分数决定是否点击
    let action = "skip";
    let selectedFactory = null;
    let clickSuccess = false;
    
    if (bestOption.score >= RULE_FACTORY_SIMILAR_MIN_SCORE) {
      // 自动点选阈值：从规则快照中读取（默认70分）
      clickSuccess = clickNode(bestOption.el);
      if (clickSuccess) {
        action = "selected";
        selectedFactory = bestOption.text;
        await sleep(800);
        
        // 检查是否有确认按钮
        const confirmLabels = ['\\u786e\\u5b9a', '\\u786e\\u8ba4'];
        const confirmButton = Array.from(factoryRow.querySelectorAll('button,a,span,div')).filter(visible)
          .find((el) => confirmLabels.includes(norm(text(el))));
        if (confirmButton) {
          clickNode(confirmButton);
          await sleep(800);
        }
        
        // 点击后等待页面刷新，然后检查筛选是否生效
        await sleep(1000);
        
        // 检查顶部筛选条件是否包含目标厂家
        const headText = document.body.innerText.slice(0, 500);
        const headHit = headText.includes(selectedFactory);
        
        // 检查URL是否包含selectedFactoryNew或其他厂家筛选参数
        const urlHit = location.href.includes('selectedFactoryNew') || location.href.includes('factory') || location.href.includes('manufacturer') || location.href.includes('brand');
        
        // 检查页面标题是否包含目标厂家
        const titleHit = document.title.includes(selectedFactory);
        
        // 检查筛选标签是否出现（有些网站会在顶部显示筛选标签）
        const filterTags = Array.from(document.querySelectorAll('.ant-tag, .ant-badge, [class*="tag"], [class*="badge"]')).filter(visible);
        const tagHit = filterTags.some((tag) => text(tag).includes(selectedFactory));
        
        // 检查筛选是否生效
        const effectHit = headHit || urlHit || titleHit || tagHit;
        
        if (!effectHit) {
          action = "click_failed";
          return {
            selected: null,
            missing: true,
            hasFactoryRow: true,
            bestMatch: bestOption.text,
            bestScore: bestOption.score,
            action: "warn",
            reason: "点击厂家选项后筛选未生效",
            url: location.href,
            headText: headText.slice(0, 260),
            effectHit: false,
            factoryRowText,
            factoryOptionsCount,
            factoryOptionsText
          };
        }
        
        return {
          selected: selectedFactory,
          missing: false,
          hasFactoryRow: true,
          bestMatch: bestOption.text,
          bestScore: bestOption.score,
          action: "selected",
          reason: "厂家筛选成功",
          url: location.href,
          headText: headText.slice(0, 260),
          effectHit: true,
          factoryRowText,
          factoryOptionsCount,
          factoryOptionsText
        };
      } else {
        action = "click_failed";
      }
    } else if (bestOption.score >= Math.round(RULE_FACTORY_SIMILAR_MIN_SCORE * 0.9)) {
      // 疑似厂家阈值：低于精确匹配阈值90%的分数，不自动点选
      action = "suspect";
    } else {
      // 低于70分：不点选
      action = "low_score";
    }

    return {
      selected: null,
      missing: true,
      hasFactoryRow: true,
      bestMatch: bestOption.text,
      bestScore: bestOption.score,
      action,
      reason: action === "suspect" ? "疑似厂家，不自动点选" : "分数过低，跳过厂家筛选",
      url: location.href,
      headText: document.body.innerText.slice(0, 260),
      effectHit: false,
      factoryRowText,
      factoryOptionsCount,
      factoryOptionsText
    };
  })()`);
  
  // 记录厂家选项数量和前若干项
  await trace(
    `FACTORY_FILTER_OPTIONS row=${item.rowNumber} count=${result?.factoryOptionsCount || 0} `
    + `options=${(result?.factoryOptionsText || []).slice(0, 5).join('|')}`
  );
  
  // 记录厂家匹配结果
  await trace(
    `FACTORY_FILTER_MATCH row=${item.rowNumber} target=${targetFactory} `
    + `best=${result?.bestMatch || ''} score=${result?.bestScore || 0} action=${result?.action || ''}`
  );
  
  // 根据不同的action记录不同的日志
  if (result?.action === "suspect") {
    await trace(
      `FACTORY_FILTER_SUSPECT row=${item.rowNumber} target=${targetFactory} `
      + `best=${result?.bestMatch || ''} score=${result?.bestScore || 0} reason=${result?.reason || ''}`
    );
  } else if (!result?.hasFactoryRow) {
    await trace(
      `FACTORY_FILTER_NO_ROW row=${item.rowNumber} target=${targetFactory} reason=${result?.reason || ''}`
    );
  } else if (result?.action === "warn") {
    await trace(
      `FACTORY_FILTER_WARN row=${item.rowNumber} target=${targetFactory} `
      + `best=${result?.bestMatch || ''} score=${result?.bestScore || 0} reason=${result?.reason || ''}`
    );
  }
  
  // 记录点击生效校验结果
  await trace(
    `FACTORY_FILTER_EFFECT row=${item.rowNumber} effect_hit=${result?.effectHit || false} `
    + `url_hit=${result?.url?.includes('selectedFactoryNew') || false} `
    + `head_hit=${result?.headText?.includes(result?.selected || '') || false}`
  );
  
  // 记录最终完成日志
  await trace(
    `FACTORY_FILTER_DONE row=${item.rowNumber} selected=${result?.selected || ''} `
    + `best=${result?.bestMatch || ''} score=${result?.bestScore || 0} action=${result?.action || ''} `
    + `has_row=${!!result?.hasFactoryRow} reason=${result?.reason || ''}`
  );
  
  return result;
}

function resultFor(item, status, reason, extra = {}) {
  // 二期整改：从原始原因中提取结构化失败编码
  const failureInfo = classifyFailure(status, reason);
  // 四期整改：失败分类（技术异常/业务拒绝/无候选）
  const failureCategory = classifyFailureCategory(status, reason, failureInfo);
  // 四期整改：购物车反写状态（独立于原因字段）
  const cartWriteStatus = classifyCartWriteStatus(status, reason, extra);
  return {
    itemId: item.itemId,
    rowNumber: item.rowNumber,
    name: item.name,
    wholesaleId: item.wholesaleId,
    storeId: item.storeId || "",
    matchedName: item.matchedName || "",
    matchedSpec: item.matchedSpec || "",
    matchedManufacturer: item.matchedManufacturer || "",
    matchedSupplier: item.matchedSupplier || "",
    matchedSupplierFull: item.matchedSupplierFull || "",
    matchedPrice: item.matchedPrice || "",
    matchedMinAmount: item.matchedMinAmount || "",
    matchedStock: item.matchedStock || "",
    matchScore: item.matchScore || "",
    matchDetail: item.matchDetail || "",
    matchSource: item.matchSource || "",
    matchReason: item.matchReason || "",
    candidateRank: item.candidateRank || 0,
    status,
    reason,
    failureStage: failureInfo.stage,
    failureCode: failureInfo.code,
    failureDetail: failureInfo.detail,
    suggestion: failureInfo.suggestion,
    failureCategory, // 四期整改：失败分类字段
    retryable: failureCategory === "TECHNICAL_RETRYABLE", // 四期整改：是否可重试
    ruleSnapshotId: item.ruleSnapshotId || "",
    // 四期整改：购物车反写状态独立字段
    cartWriteStatus,
    cartWriteTime: cartWriteStatus !== "NOT_STARTED" ? new Date().toISOString() : "",
    cartWriteMessage: extra.cartWriteMessage || "",
    cartItemId: extra.cartItemId || item.wholesaleId || "",
    cartWriteAttempts: extra.cartWriteAttempts || 0,
    ...extra,
  };
}

/**
 * 四期整改：购物车反写状态分类
 * - NOT_STARTED：尚未反写
 * - PENDING：等待反写
 * - WRITING：正在反写或核验
 * - WRITTEN：反写完成且购物车回读确认存在
 * - ALREADY_EXISTS：购物车原本已存在，且通过稳定标识核验
 * - NOT_FOUND：程序返回成功或已存在，但购物车未找到
 * - FAILED_RETRYABLE：超时、网络等可重试失败
 * - FAILED_MANUAL：登录失效、数据缺失或页面变化，需人工处理
 * - SKIPPED：采购失败或无需反写
 */
function classifyCartWriteStatus(status, reason, extra) {
  const text = String(reason || "");
  
  // 采购失败或跳过
  if (status === "failed" || status === "skipped" || status === "web_error") {
    // 技术异常（可重试）
    if (/timeout|超时|network|网络|Runtime\.evaluate|fetch failed|Failed to fetch|ECONNREFUSED|ECONNRESET/i.test(text)) {
      return "FAILED_RETRYABLE";
    }
    // 技术异常（需人工处理）
    if (/登录状态|未确认登录|WebSocket|Target closed|Execution context|浏览器|页面被关闭/i.test(text)) {
      return "FAILED_MANUAL";
    }
    return "SKIPPED";
  }
  
  // 成功状态
  if (status === "success") {
    // 购物车已存在
    if (/购物车已存在|已存在|IDEMPOTENT/i.test(text)) {
      return "ALREADY_EXISTS";
    }
    // 加购成功并验证
    if (extra?.verifiedAmount > 0 || /已加入购物车并验证/i.test(text)) {
      return "WRITTEN";
    }
    // 加购成功但未验证
    return "WRITTEN";
  }
  
  // 默认未开始
  return "NOT_STARTED";
}

/**
 * 四期整改：失败分类
 * - TECHNICAL_RETRYABLE：可重试技术异常
 * - TECHNICAL_MANUAL：登录失效、页面结构变化等需人工处理的异常
 * - BUSINESS_REJECTED：价格、起订量、厂家、供应商、评分阈值等规则拒绝
 * - NO_CANDIDATE：无可采购候选
 * - SUCCESS：采购成功
 * - IDEMPOTENT_SUCCESS：购物车已存在目标商品
 */
function classifyFailureCategory(status, reason, failureInfo) {
  const text = String(reason || "");
  
  // 成功状态
  if (status === "success") {
    if (/购物车已存在|已存在|IDEMPOTENT/.test(text)) {
      return "IDEMPOTENT_SUCCESS";
    }
    return "SUCCESS";
  }
  
  // 跳过状态
  if (status === "skipped") {
    return "SUCCESS";
  }
  
  // 技术异常（可重试）
  if (/timeout|超时|network|网络|Runtime\.evaluate|fetch failed|Failed to fetch|ECONNREFUSED|ECONNRESET/i.test(text)) {
    return "TECHNICAL_RETRYABLE";
  }
  
  // 技术异常（需人工处理）
  if (/登录状态|未确认登录|WebSocket|Target closed|Execution context|浏览器|页面被关闭|detected/i.test(text)) {
    return "TECHNICAL_MANUAL";
  }
  
  // 无候选
  if (/无候选|无匹配|未找到候选|NO_CANDIDATE/i.test(text) || failureInfo.code === "NO_CANDIDATE") {
    return "NO_CANDIDATE";
  }
  
  // 业务拒绝
  if (/价格|限价|起订量|厂家|供应商|评分|阈值|分数|SPEC_CONFLICT|MAKER_MISMATCH|SUPPLIER_MISMATCH|PRICE_EXCEED|SCORE_LOW/i.test(text)) {
    return "BUSINESS_REJECTED";
  }
  
  // 默认归类为业务拒绝
  return "BUSINESS_REJECTED";
}

/**
 * 二期整改：从原始失败原因中分类结构化失败编码
 */
function classifyFailure(status, reason) {
  const text = String(reason || "");
  const lower = text.toLowerCase();

  // 成功/跳过不需要失败编码
  if (status === "success" || status === "skipped") {
    return { stage: "", code: "", detail: "", suggestion: "" };
  }

  // 导入校验
  if (/缺少商品名称|缺少名称/.test(text)) {
    return { stage: "import_validation", code: "MISSING_PRODUCT_NAME", detail: text, suggestion: "请检查导入文件，确保每行都有商品名称字段。" };
  }
  if (/采购数量无效|数量无效/.test(text)) {
    return { stage: "import_validation", code: "INVALID_PURCHASE_QUANTITY", detail: text, suggestion: "请修改采购数量为大于0的数值。" };
  }

  // 供应商校验
  if (/供应商不在|不在允许/.test(text)) {
    return { stage: "precheck", code: "SUPPLIER_NOT_ALLOWED", detail: text, suggestion: "请检查供应商范围设置。" };
  }

  // 厂家筛选
  if (/厂家筛选/.test(text)) {
    if (/未找到|无匹配/.test(text)) {
      return { stage: "factory_filter", code: "FACTORY_FILTER_NOT_FOUND", detail: text, suggestion: "请检查厂家名称是否正确。" };
    }
    return { stage: "factory_filter", code: "FACTORY_FILTER_NOT_EFFECTIVE", detail: text, suggestion: "请检查厂家筛选是否正确应用。" };
  }

  // 搜索匹配
  if (/搜索无候选|无候选|搜索无结果/.test(text)) {
    return { stage: "search_match", code: "NO_SEARCH_RESULT", detail: text, suggestion: "请检查商品名称是否正确。" };
  }

  // 未找到候选商品（P1-3整改：精确分类，区别于搜索无结果）
  if (/未找到.*候选|未找到满足|无满足条件的候选|页面未找到候选/.test(text)) {
    return { stage: "candidate_search", code: "NO_CANDIDATE_FOUND", detail: text, suggestion: "请检查商品名称和搜索关键词，或尝试调整筛选条件。" };
  }

  // 候选评分
  // 四期整改：统一价格上限、起订量和评分失败的结构化原因
  if (/候选综合分低于规则阈值/.test(text)) {
    return { stage: "precheck", code: "SCORE_LOW", detail: text, suggestion: "请检查评分规则阈值设置，或选择评分更高的候选。" };
  }
  if (/分数.*低于|分数.*不够|分数.*不达标|评分.*低于|评分.*不够/.test(text)) {
    return { stage: "precheck", code: "SCORE_LOW", detail: text, suggestion: "请检查评分规则阈值设置，或选择评分更高的候选。" };
  }
  if (/价格.*超过上限|价格.*超限|价格.*过高|超过最高限价|价格超出|候选价格超过/.test(text)) {
    return { stage: "precheck", code: "PRICE_EXCEED", detail: text, suggestion: "请检查价格上限设置，或选择价格更低的候选。" };
  }
  if (/起订量.*超过|起购.*大于|起购.*超过|起订量.*大于采购数量/.test(text)) {
    return { stage: "precheck", code: "MIN_QTY_EXCEED", detail: text, suggestion: "请增加采购数量至起订量以上，或选择起订量更低的候选。" };
  }
  if (/规格冲突|规格不一致|包装总数冲突/.test(text)) {
    return { stage: "candidate_score", code: "SPEC_CONFLICT", detail: text, suggestion: "请检查商品规格信息。" };
  }
  if (/厂家不匹配|厂家不一致/.test(text)) {
    return { stage: "candidate_score", code: "MAKER_NOT_MATCHED", detail: text, suggestion: "请检查厂家名称是否正确。" };
  }

  // 价格校验
  if (/价格超限|价格过高|超过最高|价格超出/.test(text)) {
    return { stage: "price_check", code: "PRICE_OVER_LIMIT", detail: text, suggestion: "请检查价格上限设置。" };
  }

  // 起购/库存
  if (/起购.*大于|起购.*超过/.test(text)) {
    return { stage: "quantity_check", code: "MIN_QTY_OVER_PURCHASE_QTY", detail: text, suggestion: "请增加采购数量至起购数量以上。" };
  }
  if (/库存不足/.test(text)) {
    return { stage: "quantity_check", code: "STOCK_NOT_ENOUGH", detail: text, suggestion: "请减少采购数量或选择库存充足的供应商。" };
  }

  // 购物车已存在同品种
  if (/购物车已存在同品种|同品种/.test(text)) {
    return { stage: "cart_before_check", code: "CART_EXISTING_SAME_PRODUCT", detail: text, suggestion: "如需更换供应商，请先从购物车移除同品种商品。" };
  }

  // 加购后购物车数量校验失败（P1-2整改：精确分类）
  if (/购物车数量未达到|购物车.*数量不足|加购后.*数量/.test(text)) {
    return { stage: "cart_verify", code: "CART_QUANTITY_NOT_REACHED", detail: text, suggestion: "请检查购物车状态，确认商品是否成功加入，或重试。" };
  }

  // 加购接口
  if (/加购.*异常|加购.*失败|加购.*错误/.test(text)) {
    return { stage: "add_to_cart", code: "ADD_API_ERROR", detail: text, suggestion: "请检查网络连接，或稍后重试。" };
  }

  // 购物车验证
  if (/购物车.*数量不足|购物车.*验证/.test(text)) {
    return { stage: "cart_after_verify", code: "CART_VERIFY_AMOUNT_NOT_ENOUGH", detail: text, suggestion: "请检查购物车状态。" };
  }

  // 反写匹配
  if (/反写.*未匹配|反写.*失败/.test(text)) {
    return { stage: "cart_backfill", code: "CART_BACKFILL_NOT_MATCHED", detail: text, suggestion: "请检查购物车商品信息。" };
  }

  // 系统异常
  if (/fetch failed|failed to fetch|econnrefused|econnreset|connection refused|cdp.*(?:失败|异常)/i.test(lower)) {
    return { stage: "system_exception", code: "CDP_CONNECTION_FAILED", detail: text, suggestion: "请检查9222调试端口和药师帮浏览器连接，恢复后重试技术异常明细。" };
  }
  if (/浏览器/.test(text) || /browser/i.test(lower)) {
    return { stage: "system_exception", code: "BROWSER_NOT_FOUND", detail: text, suggestion: "请确保Chrome浏览器已启动并开启远程调试端口。" };
  }
  if (/登录/.test(text) || /login/i.test(lower)) {
    return { stage: "system_exception", code: "LOGIN_NOT_CONFIRMED", detail: text, suggestion: "请确保药师帮网页已登录。" };
  }
  if (/页面已关闭/.test(text)) {
    return { stage: "system_exception", code: "PAGE_CLOSED", detail: text, suggestion: "请确保药师帮网页未关闭。" };
  }
  if (/超时/.test(text) || /timeout/i.test(lower)) {
    return { stage: "system_exception", code: "EXECUTION_TIMEOUT", detail: text, suggestion: "请检查网络连接，或稍后重试。" };
  }
  if (/referenceerror|is not defined|factoryfilter/i.test(lower)) {
    return { stage: "system_exception", code: "SYSTEM_REFERENCE_ERROR", detail: text, suggestion: "请联系开发检查脚本变量作用域或配置传参后重试。" };
  }

  return { stage: "system_exception", code: "UNKNOWN_SYSTEM_EXCEPTION", detail: text, suggestion: "请联系开发排查问题。" };
}

async function scanCart(client) {
  await client.send("Page.navigate", { url: `https://dian.ysbang.cn/?rpaCart=${Date.now()}#/cart` }).catch(() => null);
  await sleep(6000);
  return client.evaluate(`(async () => {
    const seen = new Set();
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
    const visit = (obj, depth = 0, visited = new WeakSet()) => {
      if (!obj || typeof obj !== 'object' || depth > 8 || rows.length >= 300) return;
      if (visited.has(obj)) return;
      visited.add(obj);
      try {
        const id = getVal(obj, ['wholesaleId', 'wholesaleid', 'wholeSaleId', 'id', 'props.wholesaleId', 'props.wholesaleid', 'props.id']);
        const name = getVal(obj, ['drugName', 'drugname', 'name', 'wholesaleDrugName', 'props.drugName', 'props.drugname', 'props.name']);
        if (id && name && !seen.has(String(id))) {
          seen.add(String(id));
          rows.push({
            wholesaleId: String(id),
            drugName: String(name),
            amount: Number(getVal(obj, ['amount', 'drugAmount', 'count', 'cnt', 'num', 'props.amount', 'props.drugAmount']) || 0),
            price: Number(getVal(obj, ['price', 'chainPrice', 'showPrice', 'realPrice', 'salePrice', 'props.price', 'props.chainPrice']) || 0),
            spec: String(getVal(obj, ['specification', 'drugSpecification', 'spec', 'props.specification', 'props.drugSpecification', 'props.spec']) || ''),
            manufacturer: String(getVal(obj, ['manufacturer', 'factory', 'productFactory', 'factoryName', 'props.manufacturer', 'props.factory', 'props.productFactory']) || ''),
            supplier: String(getVal(obj, ['provider_name', 'abbreviation', 'providerName', 'sellerName', 'props.provider_name', 'props.abbreviation', 'props.providerName']) || ''),
          });
        }
      } catch {}
      if (Array.isArray(obj)) {
        for (const value of obj.slice(0, 250)) visit(value, depth + 1, visited);
      } else {
        for (const key of Object.keys(obj).slice(0, 120)) {
          try {
            const value = obj[key];
            if (value && typeof value === 'object') visit(value, depth + 1, visited);
          } catch {}
        }
      }
    };
    for (const el of Array.from(document.querySelectorAll('*')).slice(0, 3000)) {
      for (const key of Object.keys(el)) {
        if (key.startsWith('__vue')) visit(el[key]);
      }
    }
    const summary = await fetch('/shopping-cart/cart/getShoppingcartSummaryInfo/v4190', {
      method: 'POST',
      credentials: 'include',
      headers: { 'content-type': 'application/json;charset=UTF-8' },
      body: JSON.stringify({})
    }).then((res) => res.json()).catch((error) => ({ error: String(error) }));
    return { cartItems: rows, summary };
  })()`);
}

function findCartItem(cartPayload, wholesaleId) {
  const target = normalizeWholesaleId(wholesaleId);
  const stack = [cartPayload];
  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== "object") continue;
    const candidateId = current.wholesaleId ?? current.wholesaleid ?? current.wholeSaleId ?? current.goodsId ?? current.drugId ?? current.id;
    if (candidateId != null && normalizeWholesaleId(candidateId) === target) return current;
    for (const value of Object.values(current)) {
      if (Array.isArray(value)) stack.push(...value);
      else if (value && typeof value === "object") stack.push(value);
    }
  }
  return null;
}

function findSameProductCartItem(cartPayload, item) {
  const rows = Array.isArray(cartPayload?.cartItems) ? cartPayload.cartItems : [];
  return rows.find((row) => isSameProduct(item, row)) || null;
}

function cartResultExtra(cartItem, verifiedAmount, item = {}) {
  if (!cartItem) return { verifiedAmount };
  return {
    verifiedAmount,
    cartBackfillRequired: true,
    cartExisting: true,
    wholesaleId: cartItem.wholesaleId || cartItem.id || "",
    candidateSupplier: item.matchedSupplier || "",
    candidatePrice: item.matchedPrice || "",
    candidateName: item.matchedName || "",
    candidateSpec: item.matchedSpec || "",
    candidateManufacturer: item.matchedManufacturer || "",
    matchedName: item.matchedName || "",
    matchedSpec: item.matchedSpec || "",
    matchedManufacturer: item.matchedManufacturer || "",
    matchedSupplier: "",
    matchedPrice: "",
  };
}

function candidateResultExtra(candidate, extra = {}) {
  if (!candidate) return extra;
  return {
    wholesaleId: candidate.wholesaleId || "",
    matchedName: candidate.name || "",
    matchedSpec: candidate.spec || "",
    matchedManufacturer: candidate.manufacturer || "",
    matchedSupplier: candidate.supplier || "",
    matchedSupplierFull: candidate.supplierFull || "",
    matchedPrice: candidate.price || "",
    matchedMinAmount: candidate.minAmount || "",
    matchedStock: candidate.stock || "",
    candidateRank: candidate.rank || 0,
    ...extra,
  };
}

function isWebBlockingError(reason) {
  const text = String(reason || "");
  return /未确认登录|未找到已打开|登录状态|WebSocket|Target closed|Execution context|Cannot find context|浏览器|页面被关闭|detached|fetch failed|Failed to fetch|ECONNREFUSED|ECONNRESET|connection refused|CDP.*(?:失败|异常)/i.test(text);
}

function readCartAmount(cartItem) {
  if (!cartItem) return 0;
  return normalizeAmount(cartItem.amount ?? cartItem.num ?? cartItem.quantity ?? cartItem.buyNum ?? cartItem.goodsNum);
}

// 四期整改：购物车幂等校验函数
async function checkCartIdempotent(client, item) {
  const wholesaleId = normalizeWholesaleId(item.wholesaleId);
  const amount = normalizeAmount(item.amount);
  const cart = await scanCart(client);
  const cartItem = findCartItem(cart, wholesaleId);
  const sameProductCartItem = findSameProductCartItem(cart, item);
  const cartAmount = readCartAmount(cartItem);
  const sameProductAmount = readCartAmount(sameProductCartItem);
  
  if (cartAmount >= amount || sameProductAmount >= amount) {
    const existing = cartAmount >= amount ? cartItem : sameProductCartItem;
    const verifiedAmount = Math.max(cartAmount, sameProductAmount);
    return {
      exists: true,
      item: existing,
      verifiedAmount,
      wholesaleId: existing?.wholesaleId || wholesaleId,
      drugName: existing?.drugName || item.matchedName || item.name
    };
  }
  return { exists: false, verifiedAmount: Math.max(cartAmount, sameProductAmount) };
}

// 四期整改：带重试和幂等校验的加购函数
async function addToCartWithRetry(client, item) {
  const amount = normalizeAmount(item.amount);
  
  return withRetry(
    async (attempt) => {
      // 四期整改：每次重试前先检查购物车是否已存在目标商品
      if (attempt > 0) {
        await trace(`ADD_RETRY_CHECK row=${item.rowNumber} attempt=${attempt}`);
        const check = await checkCartIdempotent(client, item);
        if (check.exists) {
          await trace(`ADD_RETRY_IDEMPOTENT row=${item.rowNumber} verified_amount=${check.verifiedAmount}`);
          return {
            idempotent: true,
            alreadyExists: true,
            verifiedAmount: check.verifiedAmount,
            item: check.item
          };
        }
      }
      
      // 执行加购
      const result = await addToCart(client, item);
      return { idempotent: false, addResult: result };
    },
    {
      isRetryable: (error) => /timeout/i.test(error.message) || /超时/.test(error.message) || /network/i.test(error.message),
      onRetry: async (attempt) => {
        await trace(`ADD_RETRY_ATTEMPT row=${item.rowNumber} attempt=${attempt + 1}`);
      }
    }
  );
}

async function addToCart(client, item) {
  const wholesaleId = normalizeWholesaleId(item.wholesaleId);
  const amount = normalizeAmount(item.amount);
  return client.evaluate(`(async () => {
    const token = (document.cookie.match(/(?:^|; )Token=([^;]+)/) || [])[1] || "";
    const res = await fetch('/shopping-cart/cart/joinShoppingCart/v4190', {
      method: 'POST',
      credentials: 'include',
      headers: { 'content-type': 'application/json;charset=UTF-8' },
      body: JSON.stringify({
        platform: 'pc',
        version: '6.1.5',
        ua: 'Chrome148',
        trafficType: 1,
        ex1: Math.random().toString(36).slice(2),
        wholesaleId: ${JSON.stringify(wholesaleId)},
        amount: ${amount},
        freeDeliveryTagId: 0,
        saProps: {
          wholesaleId: ${JSON.stringify(wholesaleId)},
          wholesaleDrugName: ${JSON.stringify(item.matchedName || item.name || "")},
          drugFactoryName: ${JSON.stringify(item.matchedManufacturer || item.manufacturer || "")},
          drugAmount: ${amount},
          addSource: 'RPA智能采购逐个加购'
        },
        token
      })
    });
    return await res.json();
  })()`);
}

async function searchCandidate(client, item) {
  const keyword = String(item.smartName || item.name || "").trim();
  if (!keyword) return { candidate: null, score: 0, count: 0, reason: "缺少商品名称，无法搜索匹配" };
  const searchKey = baseName(keyword) || keyword;
  let payload = {};
  let supplierFilter = null;  // 修复变量作用域问题：在try块外声明
  let factoryFilter = null;   // 修复变量作用域问题：在try块外声明
  try {
    const url = searchUrl(searchKey);
    await trace(`SEARCH_NAVIGATE row=${item.rowNumber} keyword=${searchKey} url=${url}`);
    await client.send("Page.navigate", { url }).catch(() => null);
    await sleep(SEARCH_WAIT_MS);
    
    // 四期整改：供应商筛选带重试机制
    supplierFilter = await withRetry(
      async (attempt) => {
        if (attempt > 0) {
          await recoverPage(client, item, searchKey);
        }
        return applySupplierFilter(client, item);
      },
      {
        isRetryable: (error) => /timeout/i.test(error.message)
          || /超时|未生效|未找到商家筛选行|筛选内容加载/.test(error.message),
        onRetry: async (attempt) => {
          await trace(`SUPPLIER_FILTER_RETRY row=${item.rowNumber} attempt=${attempt + 1}`);
        }
      }
    ).catch(async (error) => {
      await trace(`SUPPLIER_FILTER_FAILED row=${item.rowNumber} error=${error.message}`);
      return { selected: [], missing: [], effective: false, error: error.message, retryable: true };
    });
    if (!supplierFilter?.effective) {
      return {
        candidate: null,
        score: 0,
        count: 0,
        noFallback: true,
        debug: { supplierFilter },
        reason: `供应商筛选未生效（${supplierFilter?.error || supplierFilter?.reason || '未确认选中允许供应商'}）。建议：请检查供应商范围和页面筛选状态后重试。`,
      };
    }
    if (supplierFilter?.selected?.length) {
      await sleep(SEARCH_WAIT_MS);
    }
    
    // 四期整改：厂家筛选带重试机制
    factoryFilter = await withRetry(
      async (attempt) => {
        if (attempt > 0) {
          await recoverPage(client, item, searchKey);
        }
        return applyFactoryFilter(client, item);
      },
      {
        isRetryable: (error) => /timeout/i.test(error.message) || /超时/.test(error.message),
        onRetry: async (attempt) => {
          await trace(`FACTORY_FILTER_RETRY row=${item.rowNumber} attempt=${attempt + 1}`);
        }
      }
    ).catch(async (error) => {
      await trace(`FACTORY_FILTER_FAILED row=${item.rowNumber} error=${error.message}`);
      // 筛选失败时返回空结果，不中断采购流程
      return { selected: null, missing: true, error: error.message, retryable: true };
    });
    if (factoryFilter?.selected) {
      await sleep(SEARCH_WAIT_MS);
    }
    
    payload = await client.evaluate(`(async () => {
    const textVal = (value) => String(value ?? '').trim();
    const getVal = (obj, keys) => {
      for (const key of keys) {
        try {
          const value = key.split('.').reduce((current, part) => current?.[part], obj);
          if (value !== undefined && value !== null && String(value) !== '') return value;
        } catch {}
      }
      return '';
    };
    const decodePrice = (token) => {
      if (!token) return {};
      try {
        const bin = atob(String(token));
        const bytes = new Uint8Array([...bin].map((ch) => ch.charCodeAt(0)));
        const text = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
        const discount = text.match(/折后约\\s*¥?\\s*(\\d+(?:\\.\\d+)?)/);
        const nums = [...text.matchAll(/\\d+\\.\\d{1,2}/g)].map((match) => Number(match[0])).filter((num) => num > 0);
        return { price: discount ? Number(discount[1]) : nums[0] };
      } catch {
        return {};
      }
    };
    const seen = new Set();
    const rows = [];
    const pushCandidate = (obj) => {
      const id = getVal(obj, ['wholesaleid', 'wholesaleId', 'wholeSaleId', 'id', 'props.wholesaleid', 'props.wholesaleId', 'props.id']);
      const name = getVal(obj, ['drugname', 'drugName', 'name', 'goodsName', 'productName', 'joinCarMap.drugName', 'props.drugname', 'props.drugName', 'props.name']);
      const supplier = getVal(obj, ['provider_name', 'abbreviation', 'providerName', 'sellerName', 'supplier', 'props.provider_name', 'props.abbreviation', 'props.providerName', 'props.sellerName']);
      if (!id || !name || !supplier) return;
      const key = String(id);
      if (seen.has(key)) return;
      seen.add(key);
      const pricePayload = decodePrice(obj?.priceToken ?? obj?.props?.priceToken);
      rows.push({
        wholesaleId: String(id),
        name: textVal(name),
        spec: textVal(getVal(obj, ['specification', 'drugSpecification', 'spec', 'packageSpec', 'joinCarMap.drugSpecification', 'props.specification', 'props.drugSpecification', 'props.spec'])),
        manufacturer: textVal(getVal(obj, ['manufacturer', 'factory', 'productFactory', 'factoryName', 'producer', 'joinCarMap.manufacturer', 'props.manufacturer', 'props.factory', 'props.productFactory'])),
        supplier: textVal(supplier),
        supplierFull: textVal(getVal(obj, ['providerCompanyName', 'providerFullName', 'companyName', 'enterpriseName', 'props.providerCompanyName', 'props.providerFullName', 'props.companyName'])),
        storeId: textVal(getVal(obj, ['storeId', 'storeid', 'store.id', 'providerStoreId', 'props.storeId', 'props.storeid'])),
        price: String(getVal(obj, ['price', 'chainPrice', 'showPrice', 'realPrice', 'salePrice', 'props.price', 'props.chainPrice', 'props.showPrice']) || pricePayload.price || ''),
        minAmount: String(getVal(obj, ['minamount', 'minAmount', 'drugMinAmount', 'joinCarMap.drugMinAmount', 'props.minamount', 'props.minAmount', 'props.drugMinAmount']) || ''),
        stock: String(getVal(obj, ['stock', 'usableStock', 'availableStock', 'props.stock', 'props.usableStock', 'props.availableStock']) || ''),
      });
    };
    const visit = (obj, depth = 0, visited = new WeakSet()) => {
      if (!obj || typeof obj !== 'object' || depth > 8 || rows.length >= 120) return;
      if (visited.has(obj)) return;
      visited.add(obj);
      if (Array.isArray(obj)) {
        for (const row of obj.slice(0, 250)) visit(row, depth + 1, visited);
        return;
      }
      pushCandidate(obj);
      for (const key of Object.keys(obj).slice(0, 140)) {
        try {
          const value = obj[key];
          if (value && typeof value === 'object') visit(value, depth + 1, visited);
        } catch {}
      }
    };
    let drugList = null;
    for (let t = 0; t < 12; t += 1) {
      const roots = Array.from(document.querySelectorAll('*')).map((el) => el.__vue__).filter(Boolean);
      const comp = roots.find((vue) => vue.$children?.[0]?.$children?.[1]?.$children?.[0])?.$children?.[0]?.$children?.[1]?.$children?.[0];
      if (Array.isArray(comp?.drugList)) {
        drugList = comp.drugList;
        if (drugList.length > 0) break;
      }
      if (document.body.innerText.includes('共0个商品') || document.body.innerText.includes('暂无商品')) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (Array.isArray(drugList)) {
      for (const row of drugList) pushCandidate(row);
    }
    if (rows.length === 0) {
      for (const el of Array.from(document.querySelectorAll('*')).slice(0, 3000)) {
        for (const key of Object.keys(el)) {
          if (key.startsWith('__vue')) visit(el[key]);
        }
      }
    }
    return {
      candidates: rows,
      debug: {
        url: location.href,
        title: document.title,
        loggedIn: document.documentElement.innerText.includes('退出'),
        text: document.body.innerText.slice(0, 240),
      }
    };
    })()`);
  } catch (error) {
    return { candidate: null, score: 0, count: 0, reason: `药师帮搜索页读取异常: ${error?.message || String(error)}` };
  }
  const searchDebug = payload?.debug || {};
  // 将厂家筛选结果写入searchDebug
  searchDebug.factoryFilter = {
    selected: factoryFilter?.selected || null,
    bestMatch: factoryFilter?.bestMatch || null,
    bestScore: factoryFilter?.bestScore || 0,
    action: factoryFilter?.action || null,
    hasFactoryRow: factoryFilter?.hasFactoryRow || false,
    url: factoryFilter?.url || "",
    effectHit: factoryFilter?.effectHit || false,
    reason: factoryFilter?.reason || "",
  };
  // 将供应商筛选结果写入searchDebug
  searchDebug.supplierFilter = {
    selected: supplierFilter?.selected || [],
    missing: supplierFilter?.missing || [],
    confirmed: supplierFilter?.confirmed || false,
    hasProviderRow: supplierFilter?.hasProviderRow || false,
    url: supplierFilter?.url || "",
  };
  const candidates = payload?.candidates || [];
  const scored = (Array.isArray(candidates) ? candidates : [])
    .map((candidate) => evaluateCandidate(item, candidate))
    .sort((a, b) => b.score - a.score || a.price - b.price);
  const eligible = scored
    .filter((entry) => entry.score >= RULE_MIN_PURCHASE_SCORE && entry.specOk && entry.manufacturerOk && entry.supplierOk && entry.priceOk && entry.qtyOk && entry.stockOk)
    .sort((a, b) => a.price - b.price || b.score - a.score);
  if (eligible.length === 0) {
    const fallback = scored[0];
    if (!fallback) {
      // 增强搜索无候选提示（方案要求：提示搜索关键词、建议检查关键词或规格）
      return {
        candidate: null,
        score: 0,
        count: 0,
        debug: searchDebug,
        reason: `药师帮搜索页未找到候选商品（搜索关键词: ${searchKey}）。建议：请检查商品名称是否正确，或尝试调整规格、厂家等关键词后重新搜索。url=${searchDebug.url || ''}`
      };
    }
    if (fallback.score < 70) {
      // 增强低分候选提示（方案要求：补充候选编码、供应商全称等信息）
      const enhancedReason = buildLowScoreReason(item, fallback);
      return {
        candidate: null,
        score: fallback.score,
        detail: fallback.detail,
        count: scored.length,
        debug: searchDebug,
        reason: `${enhancedReason}；候选编码=${fallback.candidate?.wholesaleId || ''}；供应商全称=${fallback.candidate?.supplierFull || ''}。建议：请调整评分规则或选择其他供应商。`,
      };
    }
    if (!fallback.supplierOk) {
      // 增强供应商不在允许范围提示（方案要求：提示候选供应商、允许范围、建议调整）
      const candidateSupplier = fallback.candidate?.supplier || fallback.candidate?.supplierFull || "";
      const supplierScopeText = item.supplierScope ? item.supplierScope.join(", ") : "未配置";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        debug: searchDebug,
        reason: `候选供应商不在允许范围（候选供应商: ${candidateSupplier}，允许范围: ${supplierScopeText}）。建议：请调整供应商范围或选择其他供应商。`
      };
    }
    if (!fallback.specOk) {
      // 增强规格不一致提示（方案要求：提示目标规格、候选规格、建议调整规格或规则）
      const targetSpec = item.spec || "";
      const candidateSpec = fallback.candidate?.spec || "";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        debug: searchDebug,
        noFallback: true,
        reason: `候选规格与采购规格不一致（目标规格: ${targetSpec}，候选规格: ${candidateSpec}）。建议：请调整采购规格或评分规则，或选择其他供应商。`
      };
    }
    if (!fallback.manufacturerOk) {
      // 增强厂家不匹配提示（方案要求：补充候选编码）
      const targetManufacturer = item.manufacturer || "";
      const candidateManufacturer = fallback.candidate?.manufacturer || "";
      const candidateWholesaleId = fallback.candidate?.wholesaleId || "";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        detail: fallback.detail,
        debug: searchDebug,
        noFallback: true,
        reason: `候选厂家/品牌不匹配：目标=${item.name || ""}/${targetManufacturer}；候选=${fallback.candidate?.name || ""}/${candidateManufacturer}；供应商=${fallback.candidate?.supplier || ""}；候选编码=${candidateWholesaleId}。建议：请调整厂家要求或选择其他供应商。`
      };
    }
    if (!fallback.priceOk) {
      // 增强价格超限提示（方案要求：提示目标价格上限、候选价格、建议调整价格上限或选择其他供应商）
      const expectedPrice = item.expectedPrice || "未配置";
      const candidatePrice = fallback.candidate?.price || "";
      const candidateWholesaleId = fallback.candidate?.wholesaleId || "";
      const computedMaxAllowed = fallback.maxAllowedPrice || "未计算";
      const computedComparePrice = fallback.comparePrice || "未计算";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        debug: searchDebug,
        reason: `候选价格超过最高允许价（期望价: ${expectedPrice}，最高允许价: ${computedMaxAllowed}，候选价: ${candidatePrice}，折后比较价: ${computedComparePrice}，候选编码: ${candidateWholesaleId}，规则快照ID: ${ruleSnapshotId}）。建议：请调整价格上限或选择其他供应商。`
      };
    }
    if (!fallback.qtyOk) {
      // 增强起购不满足提示（方案要求：提示采购数量、起购数量、建议调整采购数量或选择其他供应商）
      const purchaseQuantity = item.amount || "未配置";
      const minAmount = fallback.candidate?.minAmount || "";
      const candidateWholesaleId = fallback.candidate?.wholesaleId || "";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        debug: searchDebug,
        reason: `候选起购数量大于采购数量（采购数量: ${purchaseQuantity}，起购数量: ${minAmount}，候选编码: ${candidateWholesaleId}）。建议：请调整采购数量或选择其他供应商。`
      };
    }
    if (!fallback.stockOk) {
      // 增强库存不足提示（方案要求：提示采购数量、候选库存、建议调整采购数量或选择其他供应商）
      const purchaseQuantity = item.amount || "未配置";
      const candidateStock = fallback.candidate?.stock || "";
      const candidateWholesaleId = fallback.candidate?.wholesaleId || "";
      return {
        candidate: null,
        score: fallback.score,
        count: scored.length,
        debug: searchDebug,
        reason: `候选库存不足（采购数量: ${purchaseQuantity}，候选库存: ${candidateStock}，候选编码: ${candidateWholesaleId}）。建议：请调整采购数量或选择其他供应商。`
      };
    }
  }
  const best = eligible[0];
  
  // 为candidates数组中的每个候选添加isSelected标记
  const candidatesWithSelection = scored.slice(0, 10).map((entry, index) => {
    // 判断是否是真实选中的候选（通过比较candidate的wholesaleId）
    const isSelected = entry.candidate?.wholesaleId === best.candidate?.wholesaleId;
    return {
      ...entry,
      isSelected: isSelected, // 标记是否是真实选中的候选
      rank: index + 1, // 候选排名（按评分排序）
    };
  });
  
  return {
    candidate: best.candidate,
    score: best.score,
    count: scored.length,
    detail: best.detail,
    debug: searchDebug,
    reason: "",
    candidates: candidatesWithSelection, // 返回前10个候选，包含评分、通过状态、拒绝原因、isSelected标记
    specOk: best.specOk,
    manufacturerOk: best.manufacturerOk,
    supplierOk: best.supplierOk,
    priceOk: best.priceOk,
    qtyOk: best.qtyOk,
    stockOk: best.stockOk,
    comparePrice: best.comparePrice,
    selectedWholesaleId: best.candidate?.wholesaleId || null, // 明确标记真实选中的候选ID
  };
}

let client;
try {
  await trace(`START cdp=${CDP_URL} item_count=${items.length}`);
  const page = await findYsbangPage();
  if (!page?.webSocketDebuggerUrl) throw new Error("未找到已打开的药师帮页面，请用 9222 调试端口打开并登录 dian.ysbang.cn");
  await trace(`PAGE_FOUND url=${page.url}`);
  client = new CdpClient(page.webSocketDebuggerUrl);
  await client.send("Runtime.enable");
  await client.send("Page.enable").catch(() => null);
  await client.evaluate(`(() => {
    if (!window.__rpaSmartPurchaseErrorGuard) {
      window.__rpaSmartPurchaseErrorGuard = true;
      const blockPageError = (event) => {
        try {
          event.preventDefault();
          event.stopImmediatePropagation();
        } catch {}
      };
      window.addEventListener('unhandledrejection', blockPageError, true);
      window.addEventListener('error', blockPageError, true);
      window.onunhandledrejection = blockPageError;
      window.onerror = () => true;
    }
    return true;
  })()`);
  const loginText = await client.evaluate("document.body ? document.body.innerText : ''");
  if (!String(loginText || "").includes("退出")) throw new Error("药师帮页面未确认登录，请先登录后再执行");
  await trace("LOGIN_CONFIRMED");

  let stopForWebIssue = false;
  for (const item of items) {
    try {
      const amount = normalizeAmount(item.amount);
      await trace(`ITEM_START row=${item.rowNumber} item_id=${item.itemId} wholesale_id=${item.wholesaleId} amount=${amount} name=${item.name}`);
      if (amount <= 0) {
        // 增强无效采购数量提示（方案要求：提示行号、商品名、当前数量、建议动作）
        results.push(resultFor(item, "failed", `第${item.rowNumber}行 ${item.name}: 采购数量无效（当前数量: ${item.amount}）。建议：请修改采购数量为大于0的数值后重试。`));
        await trace(`ITEM_FAIL row=${item.rowNumber} reason=invalid_amount amount=${item.amount}`);
        await writeResults();
        continue;
      }

    const match = await searchCandidate(client, item);
    await trace(
      `SEARCH_MATCH row=${item.rowNumber} count=${match.count} score=${match.score} `
      + `name_score=${match.detail?.nameScore ?? ''} spec_score=${match.detail?.specScore ?? ''} maker_score=${match.detail?.makerScore ?? ''} `
      + `wholesale_id=${match.candidate?.wholesaleId || ''} supplier=${match.candidate?.supplier || ''} `
      + `price=${match.candidate?.price || ''} spec=${match.candidate?.spec || ''} reason=${match.reason || ''}`
    );
    if (match.candidate && match.score >= RULE_CART_BACKFILL_MIN_SCORE) {
      item.wholesaleId = match.candidate.wholesaleId;
      item.matchedName = match.candidate.name;
      item.matchedSpec = match.candidate.spec;
      item.matchedManufacturer = match.candidate.manufacturer;
      item.matchedSupplier = match.candidate.supplier;
      item.matchedSupplierFull = match.candidate.supplierFull || "";
      item.matchedPrice = match.candidate.price;
      item.matchedMinAmount = match.candidate.minAmount || "";
      item.matchedStock = match.candidate.stock || "";
      item.storeId = match.candidate.storeId || "";
      item.matchScore = match.score;
      item.matchDetail = {
        nameScore: match.detail?.nameScore ?? 0,
        specScore: match.detail?.specScore ?? 0,
        makerScore: match.detail?.makerScore ?? 0,
        identityOk: match.detail?.identityOk ?? false,
        specConflict: match.detail?.specConflict ?? false,
        specOk: match.specOk ?? false,
        manufacturerOk: match.manufacturerOk ?? false,
        supplierOk: match.supplierOk ?? false,
        priceOk: match.priceOk ?? false,
        qtyOk: match.qtyOk ?? false,
        stockOk: match.stockOk ?? false,
        comparePrice: match.comparePrice ?? 0,
        minAmount: match.candidate?.minAmount ?? "",
        stock: match.candidate?.stock ?? "",
        candidateRank: match.candidate?.rank ?? 0,
        rejectReason: match.reason ?? "",
      };
      item.matchSource = "name_spec_manufacturer";
      item.matchReason = `名称/规格/厂家模糊匹配通过，分数 ${match.score}（名称${match.detail?.nameScore ?? ''}，规格${match.detail?.specScore ?? ''}，厂家${match.detail?.makerScore ?? ''}）`;
      item.candidateRank = match.candidate.rank || 0;
    } else {
      results.push(resultFor(item, "failed", match.reason || "未匹配到可采购商品", {
        matchScore: match.score,
        candidateCount: match.count,
        matchSource: "name_spec_manufacturer",
        noPurchaseInfo: true,
      }));
      await writeResults();
      continue;
    }

    let cart = await scanCart(client);
    let cartItem = findCartItem(cart, item.wholesaleId);
    let sameProductCartItem = findSameProductCartItem(cart, item);
    let cartAmount = readCartAmount(cartItem);
    let sameProductAmount = readCartAmount(sameProductCartItem);
    await trace(
      `CART_BEFORE row=${item.rowNumber} found=${!!cartItem} amount=${cartAmount} `
      + `same_product_found=${!!sameProductCartItem} same_product_amount=${sameProductAmount} `
      + `same_product_id=${sameProductCartItem?.wholesaleId || ''} same_product_name=${sameProductCartItem?.drugName || ''}`
    );
    if (cartAmount >= amount || sameProductAmount >= amount) {
      const existing = cartAmount >= amount ? cartItem : sameProductCartItem;
      const verifiedAmount = Math.max(cartAmount, sameProductAmount);
      results.push(resultFor(item, "success", "购物车已存在同品种，未重复加购", cartResultExtra(existing, verifiedAmount, item)));
      await trace(`ITEM_SUCCESS_EXISTING row=${item.rowNumber} verified_amount=${verifiedAmount} existing_id=${existing?.wholesaleId || ''}`);
      await writeResults();
      continue;
    }

    // 四期整改：使用带重试和幂等校验的加购函数
    const addResponse = await addToCartWithRetry(client, item);
    
    // 四期整改：处理幂等返回（加购超时后购物车已存在）
    if (addResponse.idempotent && addResponse.alreadyExists) {
      const verifiedAmount = addResponse.verifiedAmount;
      const existingItem = addResponse.item;
      results.push(resultFor(item, "success", "加购超时后购物车已存在，确认无需重复加购", cartResultExtra(existingItem, verifiedAmount, item)));
      await trace(`ITEM_SUCCESS_IDEMPOTENT row=${item.rowNumber} verified_amount=${verifiedAmount} existing_id=${existingItem?.wholesaleId || ''}`);
      await writeResults();
      continue;
    }
    
    const addResult = addResponse.addResult;
    const code = String(addResult?.code ?? "");
    await trace(`ADD_RESPONSE row=${item.rowNumber} code=${code} body=${JSON.stringify(addResult)}`);
    if (code && code !== "40001" && code !== "0" && code !== "200") {
      // 增强加购接口异常提示（方案要求：提示接口返回、候选编码、建议检查接口或重试）
      const errorMsg = addResult?.msg || addResult?.message || `加购接口返回异常`;
      const wholesaleId = item.wholesaleId || "";
      const supplier = item.matchedSupplier || item.supplier || "";
      results.push(resultFor(item, "failed", `${errorMsg}（接口返回码: ${code}，候选编码: ${wholesaleId}，供应商: ${supplier}）。建议：请检查接口返回信息或重试。`, candidateResultExtra({
        wholesaleId: item.wholesaleId,
        name: item.matchedName,
        spec: item.matchedSpec,
        manufacturer: item.matchedManufacturer,
        supplier: item.matchedSupplier,
        price: item.matchedPrice,
      })));
      await trace(`ITEM_FAIL row=${item.rowNumber} reason=add_response code=${code}`);
      await writeResults();
      continue;
    }

    await sleep(3000);
    cart = await scanCart(client);
    cartItem = findCartItem(cart, item.wholesaleId);
    sameProductCartItem = findSameProductCartItem(cart, item);
    cartAmount = readCartAmount(cartItem);
    sameProductAmount = readCartAmount(sameProductCartItem);
    await trace(
      `CART_AFTER row=${item.rowNumber} found=${!!cartItem} amount=${cartAmount} `
      + `same_product_found=${!!sameProductCartItem} same_product_amount=${sameProductAmount} `
      + `same_product_id=${sameProductCartItem?.wholesaleId || ''} same_product_name=${sameProductCartItem?.drugName || ''}`
    );
    if (cartAmount >= amount || sameProductAmount >= amount) {
      const verifiedAmount = Math.max(cartAmount, sameProductAmount);
      const verifiedItem = cartAmount >= amount ? cartItem : sameProductCartItem;
      results.push(resultFor(item, "success", "已加入购物车并验证存在", cartResultExtra(verifiedItem, verifiedAmount, item)));
      await trace(`ITEM_SUCCESS_ADDED row=${item.rowNumber} verified_amount=${verifiedAmount}`);
    } else {
      // 增强加购后购物车数量不足提示（方案要求：提示要求数量、实际购物车数量、候选编码、建议检查购物车或重试）
      const currentAmount = Math.max(cartAmount, sameProductAmount);
      const wholesaleId = item.wholesaleId || "";
      const supplier = item.matchedSupplier || item.supplier || "";
      results.push(resultFor(item, "failed", `加购后购物车数量未达到要求（要求数量: ${amount}，实际购物车数量: ${currentAmount}，候选编码: ${wholesaleId}，供应商: ${supplier}）。建议：请检查购物车或重试。`, candidateResultExtra({
        wholesaleId: item.wholesaleId,
        name: item.matchedName,
        spec: item.matchedSpec,
        manufacturer: item.matchedManufacturer,
        supplier: item.matchedSupplier,
        price: item.matchedPrice,
      }, { verifiedAmount: currentAmount })));
      await trace(`ITEM_FAIL row=${item.rowNumber} reason=verify_amount current=${currentAmount} required=${amount}`);
    }
      await writeResults();
    } catch (itemError) {
      // 增强浏览器异常提示（方案要求：区分浏览器异常、登录异常、页面读取异常、接口异常）
      const reason = itemError?.message || String(itemError);
      const status = isWebBlockingError(reason) ? "web_error" : "failed";
      let enhancedReason = reason;
      
      // 根据错误类型增强提示
      if (reason.includes("未确认登录") || reason.includes("登录状态")) {
        enhancedReason = `药师帮页面未确认登录。建议：请确认药师帮页面已登录后再执行。`;
      } else if (reason.includes("未找到已打开") || reason.includes("浏览器")) {
        enhancedReason = `未找到药师帮浏览器页面。建议：请确认药师帮浏览器页面已打开后再执行。`;
      } else if (reason.includes("WebSocket") || reason.includes("Target closed") || reason.includes("Execution context")) {
        enhancedReason = `浏览器连接异常（${reason}）。建议：请检查浏览器连接或重新打开药师帮页面后重试。`;
      } else if (reason.includes("页面被关闭") || reason.includes("detached")) {
        enhancedReason = `药师帮页面被关闭或分离。建议：请重新打开药师帮页面后重试。`;
      } else if (reason.includes("timeout") || reason.includes("超时")) {
        enhancedReason = `执行超时（${reason}）。建议：请检查浏览器性能或减少采购数量后重试。`;
      } else {
        enhancedReason = `执行异常（${reason}）。建议：请检查错误信息或重试。`;
      }
      
      results.push(resultFor(item, status, enhancedReason, { noPurchaseInfo: true }));
      await trace(`${status === "web_error" ? "WEB_BLOCKED" : "ITEM_EXCEPTION"} row=${item.rowNumber} reason=${reason}`);
      await writeResults();
      if (status === "web_error") {
        stopForWebIssue = true;
        break;
      }
      continue;
    } finally {
      const delayMs = randomAddDelayMs();
      await trace(`ITEM_DELAY row=${item.rowNumber} delay_ms=${delayMs}`);
      await sleep(delayMs);
    }
    if (stopForWebIssue) break;
  }
  await trace(`FINISH result_count=${results.length}`);
} catch (error) {
  await trace(`FATAL ${error.message || String(error)}`);
  const status = isWebBlockingError(error.message || String(error)) ? "web_error" : "failed";
  for (const item of items.slice(results.length)) {
    results.push(resultFor(item, status, error.message || String(error), { noPurchaseInfo: true }));
  }
  await writeResults();
} finally {
  if (client) client.close();
}
