(function () {
  const $ = (id) => document.getElementById(id);
  const on = (el, evt, handler) => { if (el) el.addEventListener(evt, handler); };
  let voices = [];
  let showAllVoices = false;

  function friendlyFetchError(err) {
    const m = (err && err.message) || String(err);
    if (/Failed to fetch|NetworkError|fetch 失败/i.test(m)) {
      return "服务器未响应（请确认 Flask 正在 http://127.0.0.1:5000/ 运行，且页面也是通过该地址打开，不要用 file:// 或其他端口打开）。";
    }
    return m;
  }

  async function loadVoices() {
    const status = $("status");
    if (status) status.textContent = "正在加载声音列表...";
    try {
      const url = showAllVoices ? "/api/voices?all=1" : "/api/voices";
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      voices = await res.json();
      renderVoices();
      if (status) status.textContent = showAllVoices
        ? "已显示全部 " + voices.length + " 个声音"
        : "已显示 " + voices.length + " 个中文声音（可切换到全部语言）";
    } catch (e) {
      if (status) status.textContent = "";
      if ($("msg")) $("msg").textContent = "加载声音列表失败: " + friendlyFetchError(e);
    }
  }

  function renderVoices() {
    const sel = $("voice");
    if (!sel) return;
    sel.innerHTML = "";
    if (!voices || voices.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "没有可用的声音";
      sel.appendChild(opt);
      return;
    }
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.name;
      const short = v.name && v.locale ? v.name.replace(v.locale + "-", "") : (v.name || "");
      opt.textContent = v.locale + " · " + short + " · " + (v.gender || "");
      sel.appendChild(opt);
    }
    updateVoiceInfo();
  }

  function updateVoiceInfo() {
    const name = $("voice") && $("voice").value;
    const v = voices && voices.find(function (x) { return x.name === name; });
    if ($("voice-info")) $("voice-info").textContent = v ? "说明: " + (v.friendly || v.name) : "";
  }

  on($("voice"), "change", updateVoiceInfo);
  on($("bgm-volume"), "input", function (e) {
    const lbl = $("bgm-vol-label");
    if (lbl) lbl.textContent = e.target.value;
  });
  on($("bgm"), "change", function (e) {
    const info = $("bgm-info");
    if (!info) return;
    const f = e.target.files && e.target.files[0];
    info.textContent = f
      ? "已选择：" + f.name + "（" + (f.size / 1024).toFixed(1) + " KB）"
      : "不上传则只生成纯语音 TTS。";
  });

  const TIMEOUT_SECONDS = 180;

  on($("btn-gen"), "click", async function () {
    const textarea = $("text");
    const text = textarea ? textarea.value.trim() : "";
    if (!text) { if ($("msg")) $("msg").textContent = "请输入文本"; return; }
    if ($("msg")) $("msg").textContent = "";
    const result = $("result");
    if (result) result.classList.remove("visible");
    const btn = $("btn-gen");
    if (!btn) return;
    btn.disabled = true;
    const originalBtnText = btn.textContent;

    const controller = new AbortController();
    const bgmEl = $("bgm");
    const baseMsg = (bgmEl && bgmEl.files && bgmEl.files[0])
      ? "生成中（含背景音乐混音）"
      : "生成中";
    let elapsed = 0;
    btn.textContent = baseMsg + "... 0s";
    const timer = setInterval(function () {
      elapsed += 1;
      btn.textContent = baseMsg + "... " + elapsed + "s";
      const status = $("status");
      if (status) status.textContent = "（" + elapsed + "s / 最长 " + TIMEOUT_SECONDS + "s）";
      if (elapsed >= TIMEOUT_SECONDS) controller.abort();
    }, 1000);

    try {
      const fd = new FormData();
      fd.append("text", text);
      fd.append("voice", $("voice") ? $("voice").value : "zh-CN-XiaoxiaoNeural");
      fd.append("rate", $("rate") ? $("rate").value : "0");
      fd.append("volume", $("volume") ? $("volume").value : "0");
      fd.append("pitch", $("pitch") ? $("pitch").value : "0");
      fd.append("bgm_volume", $("bgm-volume") ? $("bgm-volume").value : "20");
      const bgmFile = bgmEl && bgmEl.files && bgmEl.files[0];
      if (bgmFile) fd.append("bgm", bgmFile, bgmFile.name);

      const resp = await fetch("/api/generate", {
        method: "POST",
        body: fd,
        signal: controller.signal,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "生成失败");
      const status = $("status");
      if (status) status.textContent = "完成 · 用时 " + elapsed + "s · MP3 " + Math.round(data.mp3_size / 1024) + " KB · SRT " + data.srt_size + " B";
      const player = $("player");
      if (player) player.src = "/api/listen/" + data.token + "?t=" + Date.now();
      const dlMp3 = $("dl-mp3"); if (dlMp3) dlMp3.href = data.mp3_url;
      const dlSrt = $("dl-srt"); if (dlSrt) dlSrt.href = data.srt_url;
      if (result) result.classList.add("visible");
      if (data.warning && $("msg")) $("msg").textContent = "提示: " + data.error;
    } catch (e) {
      const msg = $("msg");
      if (!msg) return;
      if (e.name === "AbortError") {
        msg.textContent = "超时（" + TIMEOUT_SECONDS + "s）或已取消。文本过长？请缩短后再试。";
      } else {
        msg.textContent = "错误: " + friendlyFetchError(e);
      }
    } finally {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = originalBtnText;
    }
  });

  on($("btn-toggle-lang"), "click", function () {
    showAllVoices = !showAllVoices;
    const btn = $("btn-toggle-lang");
    if (btn) btn.textContent = showAllVoices ? "只显示中文声音" : "显示全部语言";
    loadVoices();
  });

  loadVoices();
})();
