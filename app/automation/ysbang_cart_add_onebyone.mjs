import fs from "node:fs/promises";

const [, , inputPath, outputPath] = process.argv;
const CDP_URL = process.env.YSBANG_CDP_URL || "http://127.0.0.1:9222";
const ADD_DELAY_MIN_MS = Number(process.env.YSBANG_ADD_DELAY_MIN_MS || 10000);
const ADD_DELAY_MAX_MS = Number(process.env.YSBANG_ADD_DELAY_MAX_MS || 15000);
const CDP_CALL_TIMEOUT_MS = Number(process.env.YSBANG_CDP_CALL_TIMEOUT_MS || 120000);

if (!inputPath || !outputPath) {
  throw new Error("Usage: node ysbang_cart_add_onebyone.mjs <input.json> <output.json>");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const items = Array.isArray(payload.items) ? payload.items : [];
const logPath = payload.logPath || "";
const results = [];
const SEARCH_WAIT_MS = Number(process.env.YSBANG_SEARCH_WAIT_MS || 4500);

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
    } catch {
      // ignore close errors
    }
  }
}

function normalizeAmount(value) {
  const amount = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(amount) && amount > 0 ? amount : 0;
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
  return textScore(sourceCore, targetCore) >= 70;
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
    if (makerScore >= 70) return true;
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
  if (packageTotalConflict(source, target)) return false;
  if (specScore(source, target) >= 70) return true;
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
  const specOk = !item.spec || textScore(item.spec, `${cartItem.spec || ""}${cartName}`) >= 70;
  const makerScore = cartItem.manufacturer ? textScore(item.manufacturer, cartItem.manufacturer) : 0;
  if (!productIdentityCompatible(item.name || item.matchedName || "", cartName, specOk ? 80 : 0, makerScore)) return false;
  const makerOk = !item.manufacturer || makerScore >= 70 || (
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
  let score = Math.round(nameScore * 0.62 + specScoreValue * 0.2 + adjustedMakerScore * 0.18);
  if (!productIdentityCompatible(item.name, candidate.name, specScoreValue, adjustedMakerScore)) return Math.min(score, 61);
  if (item.spec && packageTotalConflict(item.spec, `${candidate.spec || ""}${candidate.name || ""}`)) return Math.min(score, 61);
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
  let total = Math.round(nameScore * 0.62 + specScoreValue * 0.2 + adjustedMakerScore * 0.18);
  if (!productIdentityCompatible(item.name, candidate.name, specScoreValue, adjustedMakerScore)) {
    total = Math.min(total, 61);
    return { nameScore, specScore: specScoreValue, makerScore: adjustedMakerScore, total };
  }
  if (item.spec && packageTotalConflict(item.spec, `${candidate.spec || ""}${candidate.name || ""}`)) {
    total = Math.min(total, 61);
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
  return `候选匹配分数过低: ${detail.total}（${problem}；目标=${item.name || ''}/${item.spec || ''}/${item.manufacturer || ''}；最佳候选=${candidate.name || ''}/${candidate.spec || ''}/${candidate.manufacturer || ''}；供应商=${candidate.supplier || ''}；价格=${candidate.price || ''}）`;
}

function normalizeNumber(value) {
  const number = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(number) ? number : 0;
}

function supplierMatches(candidate, supplierScope) {
  const scope = Array.isArray(supplierScope) ? supplierScope.filter(Boolean) : [];
  if (scope.length === 0) return true;
  const supplierText = normalizeText(`${candidate.supplier || ""}${candidate.supplierFull || ""}`);
  return scope.some((supplier) => {
    const wanted = normalizeText(supplier);
    return wanted && (supplierText.includes(wanted) || wanted.includes(supplierText));
  });
}

function evaluateCandidate(item, candidate) {
  const detail = matchScoreDetail(item, candidate);
  const price = normalizeNumber(candidate.price);
  const comparePrice = price * 0.97;
  const amount = normalizeAmount(item.amount);
  const minAmount = normalizeNumber(candidate.minAmount) || 1;
  const stock = normalizeNumber(candidate.stock) || 999999;
  const maxAllowedPrice = normalizeNumber(item.maxAllowedPrice);
  return {
    candidate,
    score: detail.total,
    detail,
    price,
    comparePrice,
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

async function applySupplierFilter(client, item) {
  const scope = Array.isArray(item.supplierScope)
    ? item.supplierScope.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  if (scope.length === 0) {
    return { selected: [], missing: [], skipped: true };
  }
  await trace(`SUPPLIER_FILTER_START row=${item.rowNumber} scope=${scope.join('|')}`);
  const result = await client.evaluate(`(async () => {
    const scope = ${JSON.stringify(scope)};
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const norm = (value) => String(value || '').replace(/\\s+/g, '').trim();
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
    const allRows = () => Array.from(document.querySelectorAll('.filter-option, .filter-item, [class*="filter"]')).filter(visible);
    const findProviderRow = () => {
      const rows = allRows();
      return rows.find((row) => {
        const value = text(row);
        return (value.includes('\\u5546\\u5bb6') || value.includes('\\u4f9b\\u5e94\\u5546')) && scope.some((supplier) => value.includes(supplier));
      }) || rows.find((row) => {
        const value = text(row);
        return value.includes('\\u5546\\u5bb6') || value.includes('\\u4f9b\\u5e94\\u5546');
      });
    };
    let providerRow = findProviderRow();
    const clicked = [];
    const missing = [];
    const multiButton = providerRow
      ? Array.from(providerRow.querySelectorAll('button,a,span,div')).filter(visible).find((el) => norm(text(el)) === '\\u591a\\u9009')
      : null;
    if (multiButton) {
      clickNode(multiButton);
      await sleep(500);
      providerRow = findProviderRow() || providerRow;
    }
    for (const supplier of scope) {
      const target = norm(supplier);
      const candidates = Array.from((providerRow || document).querySelectorAll('a,button,span,div,label,li')).filter(visible);
      let option = candidates.find((el) => norm(text(el)) === target);
      if (!option) {
        option = candidates.find((el) => {
          const value = norm(text(el));
          return value && (value.includes(target) || target.includes(value)) && value.length <= target.length + 8;
        });
      }
      if (option && clickNode(option)) {
        clicked.push(supplier);
        await sleep(250);
      } else {
        missing.push(supplier);
      }
    }
    const confirmLabels = ['\\u786e\\u5b9a', '\\u786e\\u8ba4'];
    const confirmRoot = providerRow || document;
    const confirmButton = Array.from(confirmRoot.querySelectorAll('button,a,span,div')).filter(visible)
      .find((el) => confirmLabels.includes(norm(text(el))));
    if (confirmButton) {
      clickNode(confirmButton);
      await sleep(1800);
    }
    return {
      selected: clicked,
      missing,
      confirmed: Boolean(confirmButton),
      hasProviderRow: Boolean(providerRow),
      url: location.href,
      headText: document.body.innerText.slice(0, 260),
    };
  })()`);
  await trace(
    `SUPPLIER_FILTER_DONE row=${item.rowNumber} selected=${(result?.selected || []).join('|')} `
    + `missing=${(result?.missing || []).join('|')} confirmed=${!!result?.confirmed} has_row=${!!result?.hasProviderRow}`
  );
  return result;
}

function resultFor(item, status, reason, extra = {}) {
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
    matchedPrice: item.matchedPrice || "",
    matchScore: item.matchScore || "",
    matchDetail: item.matchDetail || "",
    matchSource: item.matchSource || "",
    matchReason: item.matchReason || "",
    status,
    reason,
    ...extra,
  };
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
  const target = String(wholesaleId);
  const stack = [cartPayload];
  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== "object") continue;
    const candidateId = current.wholesaleId ?? current.wholesaleid ?? current.wholeSaleId ?? current.goodsId ?? current.drugId ?? current.id;
    if (candidateId != null && String(candidateId) === target) return current;
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
    matchedPrice: candidate.price || "",
    ...extra,
  };
}

function isWebBlockingError(reason) {
  const text = String(reason || "");
  return /未确认登录|未找到已打开|登录状态|WebSocket|Target closed|Execution context|Cannot find context|浏览器|页面被关闭|detached/i.test(text);
}

function readCartAmount(cartItem) {
  if (!cartItem) return 0;
  return normalizeAmount(cartItem.amount ?? cartItem.num ?? cartItem.quantity ?? cartItem.buyNum ?? cartItem.goodsNum);
}

async function addToCart(client, item) {
  const wholesaleId = String(item.wholesaleId || "").trim();
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
  const keyword = String(item.name || "").trim();
  if (!keyword) return { candidate: null, score: 0, count: 0, reason: "缺少商品名称，无法搜索匹配" };
  const searchKey = baseName(keyword) || keyword;
  let payload = {};
  try {
    const url = searchUrl(searchKey);
    await trace(`SEARCH_NAVIGATE row=${item.rowNumber} keyword=${searchKey} url=${url}`);
    await client.send("Page.navigate", { url }).catch(() => null);
    await sleep(SEARCH_WAIT_MS);
    const supplierFilter = await applySupplierFilter(client, item);
    if (supplierFilter?.selected?.length) {
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
  const candidates = payload?.candidates || [];
  const scored = (Array.isArray(candidates) ? candidates : [])
    .map((candidate) => evaluateCandidate(item, candidate))
    .sort((a, b) => b.score - a.score || a.price - b.price);
  const eligible = scored
    .filter((entry) => entry.score >= 70 && entry.specOk && entry.manufacturerOk && entry.supplierOk && entry.priceOk && entry.qtyOk && entry.stockOk)
    .sort((a, b) => a.price - b.price || b.score - a.score);
  if (eligible.length === 0) {
    const fallback = scored[0];
    if (!fallback) {
      return {
        candidate: null,
        score: 0,
        count: 0,
        debug: searchDebug,
        reason: `药师帮搜索页未找到候选商品；url=${searchDebug.url || ''}`
      };
    }
    if (fallback.score < 70) {
      return {
        candidate: null,
        score: fallback.score,
        detail: fallback.detail,
        count: scored.length,
        debug: searchDebug,
        reason: buildLowScoreReason(item, fallback),
      };
    }
    if (!fallback.supplierOk) {
      return { candidate: null, score: fallback.score, count: scored.length, debug: searchDebug, reason: "候选供应商不在本次允许范围" };
    }
    if (!fallback.specOk) {
      return { candidate: null, score: fallback.score, count: scored.length, debug: searchDebug, noFallback: true, reason: "候选规格与采购规格不一致" };
    }
    if (!fallback.manufacturerOk) {
      return { candidate: null, score: fallback.score, count: scored.length, detail: fallback.detail, debug: searchDebug, noFallback: true, reason: `候选厂家/品牌不匹配：目标=${item.name || ""}/${item.manufacturer || ""}；候选=${fallback.candidate?.name || ""}/${fallback.candidate?.manufacturer || ""}；供应商=${fallback.candidate?.supplier || ""}` };
    }
    if (!fallback.priceOk) {
      return { candidate: null, score: fallback.score, count: scored.length, debug: searchDebug, reason: "候选价格超过最高允许价" };
    }
    if (!fallback.qtyOk) {
      return { candidate: null, score: fallback.score, count: scored.length, debug: searchDebug, reason: "候选起购数量大于采购数量" };
    }
    if (!fallback.stockOk) {
      return { candidate: null, score: fallback.score, count: scored.length, debug: searchDebug, reason: "候选库存不足" };
    }
  }
  const best = eligible[0];
  return {
    candidate: best.candidate,
    score: best.score,
    count: scored.length,
    debug: searchDebug,
    reason: "",
    selected: {
      price: best.price,
      supplierOk: best.supplierOk,
      priceOk: best.priceOk,
      qtyOk: best.qtyOk,
      stockOk: best.stockOk,
    },
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
        results.push(resultFor(item, "failed", "采购数量必须大于0"));
        await trace(`ITEM_FAIL row=${item.rowNumber} reason=invalid_amount amount=${item.amount}`);
        await writeResults();
        continue;
      }

    const originalWholesaleId = String(item.wholesaleId || "").trim();
    const match = await searchCandidate(client, item);
    await trace(
      `SEARCH_MATCH row=${item.rowNumber} count=${match.count} score=${match.score} `
      + `name_score=${match.detail?.nameScore ?? ''} spec_score=${match.detail?.specScore ?? ''} maker_score=${match.detail?.makerScore ?? ''} `
      + `wholesale_id=${match.candidate?.wholesaleId || ''} supplier=${match.candidate?.supplier || ''} `
      + `price=${match.candidate?.price || ''} spec=${match.candidate?.spec || ''} reason=${match.reason || ''}`
    );
    if (match.candidate && match.score >= 70) {
      item.wholesaleId = match.candidate.wholesaleId;
      item.matchedName = match.candidate.name;
      item.matchedSpec = match.candidate.spec;
      item.matchedManufacturer = match.candidate.manufacturer;
      item.matchedSupplier = match.candidate.supplier;
      item.matchedPrice = match.candidate.price;
      item.storeId = match.candidate.storeId || "";
      item.matchScore = match.score;
      item.matchDetail = match.detail || {};
      item.matchSource = "name_spec_manufacturer";
      item.matchReason = `名称/规格/厂家模糊匹配通过，分数 ${match.score}（名称${match.detail?.nameScore ?? ''}，规格${match.detail?.specScore ?? ''}，厂家${match.detail?.makerScore ?? ''}）`;
    } else if (originalWholesaleId && !match.noFallback && !String(item.spec || "").trim()) {
      item.wholesaleId = originalWholesaleId;
      item.matchScore = match.score || "";
      item.matchSource = "fallback_ysb_code";
      item.matchReason = `名称/规格/厂家模糊匹配未通过，退回使用原药师帮编码 ${originalWholesaleId}；原因：${match.reason || `分数 ${match.score}`}`;
      await trace(`FALLBACK_YSB_CODE row=${item.rowNumber} wholesale_id=${originalWholesaleId} reason=${item.matchReason}`);
    } else {
      results.push(resultFor(item, "failed", match.reason || "未匹配到可采购商品，且没有可兜底的药师帮编码", {
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

    const addResult = await addToCart(client, item);
    const code = String(addResult?.code ?? "");
    await trace(`ADD_RESPONSE row=${item.rowNumber} code=${code} body=${JSON.stringify(addResult)}`);
    if (code && code !== "40001" && code !== "0" && code !== "200") {
      results.push(resultFor(item, "failed", addResult?.msg || addResult?.message || `加购接口返回异常: ${code}`, candidateResultExtra({
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
      const currentAmount = Math.max(cartAmount, sameProductAmount);
      results.push(resultFor(item, "failed", `加购后购物车数量未达到要求，当前 ${currentAmount}，要求 ${amount}`, candidateResultExtra({
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
      const reason = itemError?.message || String(itemError);
      const status = isWebBlockingError(reason) ? "web_error" : "failed";
      results.push(resultFor(item, status, reason, { noPurchaseInfo: true }));
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
