"""Gọi AI: Gemini (gói miễn phí, mặc định) hoặc Claude.

Nguyên tắc:
- Cách chọn và lưu model y như bot timesheet: "auto" = flash-lite-latest trước, rồi các bản lite khác,
  rồi flash-latest, rồi các bản flash; model dò được từ Google xếp hạng và lưu 30 ngày trong
  data/ai_model.json (model, candidates, resolved_at, quota_exhausted [{model, date}], cache_date).
- 404 (model bị khai tử / không mở cho người dùng mới) -> chuyển model kế, nhớ 30 ngày để khỏi gọi lại.
- 429 khi đang tra web (google_search): gói free có quota tra web riêng rất thấp (Gemini 3.x thường = 0) -> hỏi lại
  ngay KHÔNG tra web, dặn AI nói rõ là không có số liệu thời gian thực.
- 429 khác -> chuyển model kế NGAY, không retry.
  429 hết quota NGÀY (body có "PerDay") mới ghi lại để bỏ qua model đó tới mốc reset quota của Google
  (0h giờ Thái Bình Dương, lấy tròn 08:00 UTC ~ 15:00 VN). 429 theo phút chỉ bỏ qua model trong lần gọi này.
  Mọi model đều hết quota ngày -> nghỉ AI 3 tiếng (dùng rule/nội dung có sẵn).
- 503/500/504 (server nghẽn) -> retry 3 lần x 5s, rồi thử 1 model khác hệ, rồi thôi.
- Hết cách -> raise AIError với lời nhắn dễ hiểu; nơi gọi tự dùng nội dung có sẵn (không gọi AI).
  AIError.permanent=True: lỗi không tự hết (chưa có key, key sai/bị chặn: 400 key, 401, 403) -> nơi gọi
  đừng retry, báo người dùng sửa config. AIError.daily_quota=True: mọi model Gemini hết quota ngày.
- Không gửi thinkingConfig: để Google dùng mặc định của từng model (giống bot timesheet). maxOutputTokens đủ lớn
  (8192) nên phần "thinking" không làm cụt câu trả lời; phần thought bị bỏ khi đọc kết quả (_gemini_text).
- Chỉ đếm lượt gọi để xem /aistatus, không tự chặn.

Debug không tốn quota:  python focus_tracker.py ai-models
Thử gọi 1 lần:          python focus_tracker.py ai-test

Gọi được từ nhiều thread cùng lúc (bot Telegram và hàng đợi nền): file cache có khoá.
"""
import base64
import datetime as dt
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from . import ai_context, errors, net
from .logs import audit, get_logger

# Giống bot timesheet: luôn gọi flash-lite-latest trước (gói free, nhanh, ít nghẽn), hết quota thì dùng hết
# các bản lite rồi mới tới flash. Không dùng model pro.
PRIMARY_GEMINI = "gemini-flash-lite-latest"
FALLBACK_GEMINI = "gemini-flash-latest"
FLASH_LITE_EXTRAS = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]
FLASH_EXTRAS = ["gemini-2.5-flash", "gemini-2.0-flash"]
RETRY_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 5
MODEL_LIST_TTL_DAYS = 30
MAX_MODELS_TRIED = 6
MAX_BAD_REQUEST_MODELS = 3   # 400 chung chung ở bấy nhiêu model liên tiếp thì dừng (lỗi nằm ở nội dung, không ở model)
FREE_CALLS_PER_MODEL = 20  # gói free Gemini: khoảng 20 lượt gọi thô/ngày/model (mỗi lần retry cũng tính)
MAX_OUTPUT_TOKENS = 8192
GONE_DAYS = 30             # model trả 404 thì bỏ qua 30 ngày (bằng hạn làm mới danh sách model)
NO_WEB_NOTE = ("\n\n(Lần gọi này KHÔNG tra web được vì Google đang giới hạn tính năng tra web của gói miễn phí. "
               "Nếu câu hỏi cần số liệu mới nhất thì nói rõ là không có số liệu thời gian thực và gợi ý nơi xem; "
               "không bịa số.)")
QUOTA_RESET_UTC_HOUR = 8   # quota free Gemini reset lúc 0h giờ Thái Bình Dương ~ 08:00 UTC (15:00 VN)

log = get_logger()
_lock = threading.RLock()


class AIError(Exception):
    """Lỗi AI kèm lời nhắn tiếng Việt cho người dùng.

    permanent: True nếu lỗi không tự hết khi thử lại (chưa cấu hình key, key sai / bị chặn: HTTP 400 key
        không hợp lệ, 401, 403). Nơi gọi thấy permanent thì đừng retry / xếp hàng gọi lại.
    daily_quota: True nếu mọi model Gemini đã hết quota ngày (bot chuyển sang rule/nội dung có sẵn)."""

    def __init__(self, msg="", permanent=False, daily_quota=False):
        super().__init__(msg)
        self.permanent, self.daily_quota = permanent, daily_quota


# ------------------------------------------------------------ cache & usage files

def _path(cfg, name):
    return os.path.join(cfg["data_dir"], name)


def _load(cfg, name):
    try:
        with open(_path(cfg, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        log.debug("Chưa đọc được %s: %s", name, e)
        return {}


def _save(cfg, name, data):
    tmp = f"{_path(cfg, name)}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path(cfg, name))
    except OSError as e:  # file đang bị khoá (antivirus...): bỏ qua lần ghi này, không làm hỏng việc chính
        log.warning("Không ghi được %s: %s", name, e)
        try:
            os.remove(tmp)
        except OSError as e2:
            log.debug("Không xoá được file tạm %s: %s", tmp, e2)


def _today():
    return dt.date.today().isoformat()


def _now():
    return time.time()


def quota_reset_after(ts):
    """Mốc reset quota free Gemini kế tiếp sau ts (epoch): 08:00 UTC. Không cần tzdata."""
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    r = d.replace(hour=QUOTA_RESET_UTC_HOUR, minute=0, second=0, microsecond=0)
    return (r if r > d else r + dt.timedelta(days=1)).timestamp()


def _exhausted_at(e):
    """Lúc model hết quota. Bản ghi cũ {model, date} (chưa có "at"): coi như 0h ngày đó giờ máy."""
    try:
        return float(e["at"]) if "at" in e else dt.datetime.strptime(e["date"], "%Y-%m-%d").timestamp()
    except (KeyError, TypeError, ValueError) as ex:
        log.debug("Bản ghi quota_exhausted lạ %r: %s", e, ex)
        return 0.0


def _is_daily_429(body):
    low = (body or "").lower()
    return "perday" in low or "per day" in low


def _model_cache(cfg):
    """data/ai_model.json, cùng cấu trúc với bot timesheet:
    {"cache_date", "model", "candidates", "resolved_at", "quota_exhausted": [{"model", "date", "at"}], "offline_until"}
    Model hết quota được bỏ qua tới mốc reset của Google (08:00 UTC) sau lúc hết, không theo ngày giờ VN."""
    cache = _load(cfg, "ai_model.json")
    if cache.get("cache_date") != _today():
        # Ngày mới: quên quota hết hạn hôm qua, quay lại model ưu tiên số 1.
        cache.update({"cache_date": _today(), "model": PRIMARY_GEMINI, "offline_until": 0,
                      "rule_parser_mode": None})
    now = _now()
    cache["quota_exhausted"] = [e for e in cache.get("quota_exhausted") or []
                                if isinstance(e, dict) and e.get("model")
                                and quota_reset_after(_exhausted_at(e)) > now]
    return cache


def exhausted_today(cache):
    return [e["model"] for e in cache.get("quota_exhausted", [])]


def _update_cache(cfg, **changes):
    with _lock:
        cache = _model_cache(cfg)
        for k, v in changes.items():
            if k == "add_exhausted":
                if v not in exhausted_today(cache):
                    cache["quota_exhausted"].append({"model": v, "date": _today(), "at": round(_now())})
            else:
                cache[k] = v
        _save(cfg, "ai_model.json", cache)
        return cache


def gone_models(cache):
    """Model trả 404 (bị khai tử / không mở cho người dùng mới) trong GONE_DAYS ngày qua: khỏi thử lại mỗi lần gọi."""
    limit = _now() - GONE_DAYS * 86400
    return [g["model"] for g in cache.get("gone") or [] if isinstance(g, dict) and g.get("at", 0) > limit]


def _mark_gone(cfg, model):
    with _lock:
        cache = _model_cache(cfg)
        gone = [g for g in cache.get("gone") or [] if isinstance(g, dict) and g.get("model") != model]
        gone.append({"model": model, "at": round(_now())})
        cache["gone"] = gone
        _save(cfg, "ai_model.json", cache)


def _mark_exhausted(cfg, model):
    _update_cache(cfg, add_exhausted=model)
    log.warning("Gemini %s hết quota ngày, bỏ qua tới %s.", model,
                dt.datetime.fromtimestamp(quota_reset_after(_now())).strftime("%d/%m %H:%M"))
    audit("AI_QUOTA_EXHAUSTED", model)


def _redact(cfg, text):
    """Xoá key khỏi chuỗi trước khi ghi log / báo lỗi."""
    text = str(text)
    for k in ("gemini_api_key", "anthropic_api_key"):
        if len(cfg.get(k) or "") >= 8:  # key giả quá ngắn (test) thì bỏ qua, tránh xoá nhầm chữ
            text = text.replace(cfg[k], "***")
    return text


_prompt_lock = threading.Lock()
PROMPT_LOG_PREFIX = "ai-prompts-"  # data/logs/ai-prompts-YYYY-MM-DD.log, housekeeping xoá sau ai_prompt_log_days


def _log_prompt(cfg, purpose, model, system, prompt, image, web, started, answer=None, error=None):
    """Ghi NGUYÊN VĂN prompt đã gửi AI (system + prompt sau khi điền số liệu) và câu trả lời / lỗi, để khi AI trả
    lời lạ thì mở file xem AI đã nhận gì. Không ghi key (đã che), không ghi ảnh (chỉ ghi kích thước)."""
    days = cfg.get("ai_prompt_log_days", 14)
    if not days:
        return
    try:
        folder = os.path.join(cfg["data_dir"], "logs")
        os.makedirs(folder, exist_ok=True)
        now = dt.datetime.now()
        head = (f"===== {now:%Y-%m-%d %H:%M:%S} · purpose={purpose} · model={model or '-'} · web={web} · "
                f"{(time.time() - started) * 1000:.0f} ms · {'LỖI' if error else 'OK'} =====")
        parts = [head, "--- SYSTEM ---", system or "", "--- PROMPT ---", prompt or ""]
        if image:
            parts.append(f"--- ẢNH --- (không lưu ảnh, {len(image)} byte)")
        parts += (["--- LỖI ---", error] if error else ["--- TRẢ LỜI ---", answer or ""])
        text = _redact(cfg, "\n".join(parts)) + "\n\n"
        with _prompt_lock, open(os.path.join(folder, f"{PROMPT_LOG_PREFIX}{now:%Y-%m-%d}.log"), "a",
                                encoding="utf-8") as f:
            f.write(text)
    except Exception as e:  # ghi log prompt lỗi (ổ đầy, file khoá) không được làm hỏng lần gọi AI
        log.warning("Không ghi được log prompt AI: %s", e)


def _words(text):
    return len((text or "").split())


def _count_usage(cfg, model, purpose="", words_in=0, words_out=0):
    """Đếm lượt gọi và số TỪ gửi/nhận (đếm từ thay cho token: nhẹ, đủ để biết đang dùng nhiều hay ít)."""
    with _lock:
        usage = _load(cfg, "ai_usage.json")
        month, today = _today()[:7], _today()
        if usage.get("month") != month:
            usage = {"month": month, "month_count": 0, "days": {}, "models": {}}
        usage["month_count"] = usage.get("month_count", 0) + 1
        usage["month_words_in"] = usage.get("month_words_in", 0) + words_in
        usage["month_words_out"] = usage.get("month_words_out", 0) + words_out
        days, models = usage.setdefault("days", {}), usage.setdefault("models", {})
        days[today] = days.get(today, 0) + 1
        models[model] = models.get(model, 0) + 1
        usage["days"] = dict(sorted(days.items())[-31:])
        detail = usage.setdefault("day_detail", {})
        d = detail.setdefault(today, {"words_in": 0, "words_out": 0, "purposes": {}})
        d["words_in"] += words_in
        d["words_out"] += words_out
        key = (purpose or "khac").split(":")[0]
        d["purposes"][key] = d["purposes"].get(key, 0) + 1
        usage["day_detail"] = dict(sorted(detail.items())[-31:])
        _save(cfg, "ai_usage.json", usage)


def _count_raw(cfg, model):
    """Đếm lượt gọi THÔ theo model trong ngày (mỗi lần retry cũng tốn 1 lượt quota free)."""
    with _lock:
        usage = _load(cfg, "ai_usage.json")
        raw = usage.setdefault("raw", {})
        raw = {d: v for d, v in raw.items() if d >= (dt.date.today() - dt.timedelta(days=7)).isoformat()}
        day = raw.setdefault(_today(), {})
        day[model] = day.get(model, 0) + 1
        usage["raw"] = raw
        _save(cfg, "ai_usage.json", usage)


def usage_summary(cfg):
    """Số liệu dùng AI hôm nay / tháng này (cho /status, /aistatus)."""
    usage = _load(cfg, "ai_usage.json")
    today = usage.get("day_detail", {}).get(_today(), {})
    same_month = usage.get("month") == _today()[:7]
    return {"calls_today": usage.get("days", {}).get(_today(), 0),
            "words_in_today": today.get("words_in", 0), "words_out_today": today.get("words_out", 0),
            "purposes_today": today.get("purposes", {}),
            "calls_month": usage.get("month_count", 0) if same_month else 0,
            "words_in_month": usage.get("month_words_in", 0) if same_month else 0,
            "words_out_month": usage.get("month_words_out", 0) if same_month else 0,
            "raw_today": usage.get("raw", {}).get(_today(), {})}


def clear_cache(cfg):
    """Xoá cache chọn model (lần gọi sau dò lại từ đầu). Không xoá bộ đếm lượt dùng."""
    with _lock:
        try:
            os.remove(_path(cfg, "ai_model.json"))
            return True
        except OSError as e:
            log.debug("Không xoá được ai_model.json: %s", e)
            return False


# ------------------------------------------------------------ provider

def provider(cfg):
    choice = (cfg.get("ai_provider") or "auto").lower()
    if choice == "off":
        return None
    if choice in ("auto", "gemini") and cfg.get("gemini_api_key"):
        return "gemini"
    if choice in ("auto", "claude") and cfg.get("anthropic_api_key"):
        return "claude"
    return None


PURPOSE_NAMES = {"test": "thử AI (ai-test)", "ask": "hỏi AI", "intent": "hiểu tin nhắn", "daily_review": "đánh giá ngày",
                 "weekly_review": "tổng kết tuần", "morning": "chào sáng", "encourage": "khích lệ",
                 "as400_photo": "đọc ảnh AS400", "ai-test": "thử AI"}


def status_text(cfg):
    p = provider(cfg)
    if not p:
        return "AI: chưa cấu hình key, đang dùng nội dung có sẵn."
    cache = _model_cache(cfg)
    usage = _load(cfg, "ai_usage.json")
    u = usage_summary(cfg)
    lines = [f"AI: {p}, model gần nhất: {cache.get('model') or 'chưa gọi lần nào'}",
             f"Hôm nay: {u['calls_today']} lượt, gửi {u['words_in_today']:,} từ, nhận {u['words_out_today']:,} từ",
             f"Tháng này: {u['calls_month']} lượt, gửi {u['words_in_month']:,} từ, nhận {u['words_out_month']:,} từ"]
    if u["purposes_today"]:
        lines.append("Hôm nay dùng cho: " + ", ".join(
            f"{PURPOSE_NAMES.get(k, k)} {v}" for k, v in sorted(u["purposes_today"].items(), key=lambda x: -x[1])))
    budget = int(cfg.get("ai_daily_call_budget") or 0)
    if budget:
        lines.append(f"Hạn mức bạn đặt: {budget} lượt/ngày, còn {max(0, budget - u['calls_today'])} lượt.")
    if p == "gemini":
        free = int(cfg.get("gemini_free_calls_per_model") or FREE_CALLS_PER_MODEL)
        gone = set(exhausted_today(cache))
        rows = []
        for m in [PRIMARY_GEMINI] + FLASH_LITE_EXTRAS + [FALLBACK_GEMINI] + FLASH_EXTRAS:
            used = u["raw_today"].get(m, 0)
            if used or m in (PRIMARY_GEMINI, FALLBACK_GEMINI) or m in gone:
                left = "hết" if m in gone else f"còn ~{max(0, free - used)}"
                rows.append(f"  {m}: {used}/{free} ({left})")
        for m, used in u["raw_today"].items():
            if m not in " ".join(rows):
                rows.append(f"  {m}: {used}/{free}")
        lines.append("Gói free (ước tính, Google không báo số còn lại):\n" + "\n".join(rows))
    if cache.get("quota_exhausted"):
        lines.append("Hết quota hôm nay: " + ", ".join(exhausted_today(cache)))
    if gone_models(cache):
        lines.append("Model Google không mở cho key này (404), bỏ qua 30 ngày: " + ", ".join(gone_models(cache)))
    if cache.get("offline_until", 0) > time.time():
        lines.append("AI tạm nghỉ vì hết quota, bot đang dùng nội dung có sẵn. Vài tiếng nữa tự thử lại.")
    return "\n".join(lines)


# ------------------------------------------------------------ Gemini (REST, không cần SDK)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"


class HTTPStatusError(Exception):
    def __init__(self, code, body=""):
        super().__init__(f"HTTP {code}: {body[:200]}")
        self.code, self.body = code, body


def _http(cfg, method, url, headers, payload=None):
    """Gọi HTTPS bằng thư viện chuẩn (không cần cài SDK, nhẹ RAM). Theo proxy hệ thống của Windows."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=dict(headers, **({"Content-Type": "application/json"} if data else {})))
    timeout = float(cfg.get("ai_timeout_seconds") or 60)
    try:
        with net.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception as e2:
            log.debug("Không đọc được body lỗi HTTP %s: %s", e.code, e2)
            body = ""
        raise HTTPStatusError(e.code, body)


def _gemini_headers(cfg):
    return {"x-goog-api-key": cfg["gemini_api_key"]}  # key trong header, không nằm trong URL/log


def _version(name):
    nums = re.findall(r"(\d+)(?:\.(\d+))?", name)
    return tuple(int(x or 0) for pair in nums[:1] for x in pair) or (0, 0)


def _rank(name):
    low = name.lower()
    tier = 0 if "lite" in low else 1 if "flash" in low else 2
    unstable = 1 if any(x in low for x in ("preview", "exp", "beta", "alpha", "test")) else 0
    return (tier, unstable, tuple(-v for v in _version(low)), name)


def list_gemini_models(cfg):
    """Hỏi Google danh sách model sinh văn bản. Không tốn quota sinh nội dung."""
    names, token = [], ""
    for _ in range(10):
        url = f"{GEMINI_URL}/models?pageSize=200" + (f"&pageToken={token}" if token else "")
        res = _http(cfg, "GET", url, _gemini_headers(cfg))
        for m in res.get("models", []):
            name = (m.get("name") or "").replace("models/", "")
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            if any(x in name for x in ("embedding", "tts", "image", "audio", "live", "veo", "imagen", "aqa",
                                        "gemma", "robotics", "computer-use")):
                continue
            names.append(name)
        token = res.get("nextPageToken")
        if not token:
            break
    return sorted(set(names), key=_rank)


def _gemini_candidates(cfg):
    cache = _model_cache(cfg)
    fresh = (cache.get("resolved_at") or "")[:10] >= (
        dt.date.today() - dt.timedelta(days=MODEL_LIST_TTL_DAYS)).isoformat()
    if not fresh:
        try:
            cache = _update_cache(cfg, candidates=list_gemini_models(cfg)[:8],
                                  resolved_at=dt.datetime.now().isoformat(timespec="seconds"))
        except Exception as e:  # không dò được thì dùng danh sách cũ, không sập
            log.warning("Không dò được danh sách model Gemini: %s", e)
    listed = [m for m in cache.get("candidates", []) if "pro" not in m.lower().split("-")]
    lite = [m for m in listed if "lite" in m]
    flash = [m for m in listed if "lite" not in m]
    wanted = cfg.get("gemini_model") or "auto"
    order = (([] if wanted == "auto" else [wanted]) + [PRIMARY_GEMINI] + FLASH_LITE_EXTRAS + lite
             + [FALLBACK_GEMINI] + FLASH_EXTRAS + flash)
    seen, out = set(), []
    for m in order:
        if m not in seen:
            seen.add(m)
            out.append(m)
    skip = set(exhausted_today(cache)) | set(gone_models(cache))
    return [m for m in out if m not in skip]


STOP_REASONS = {
    "SAFETY": "AI chặn câu trả lời vì bộ lọc an toàn (SAFETY). Thử hỏi cách khác.",
    "PROHIBITED_CONTENT": "AI chặn câu trả lời vì bộ lọc an toàn (PROHIBITED_CONTENT). Thử hỏi cách khác.",
    "BLOCKLIST": "AI chặn câu trả lời vì bộ lọc an toàn (BLOCKLIST). Thử hỏi cách khác.",
    "SPII": "AI chặn câu trả lời vì có thông tin cá nhân nhạy cảm (SPII). Thử hỏi cách khác.",
    "RECITATION": "AI dừng vì câu trả lời giống nguyên văn nội dung có bản quyền (RECITATION). Thử hỏi cách khác.",
    "MAX_TOKENS": "AI hết giới hạn độ dài trước khi kịp trả lời (MAX_TOKENS). Thử hỏi ngắn gọn hơn.",
}


def _gemini_text(res, model=""):
    cands = res.get("candidates") or []
    if not cands:
        reason = (res.get("promptFeedback") or {}).get("blockReason")
        raise AIError("AI từ chối nội dung này." if reason else "AI trả về rỗng.")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    finish = cands[0].get("finishReason") or ""
    if not text:
        raise AIError(STOP_REASONS.get(finish, "AI trả về rỗng."))
    if finish == "MAX_TOKENS":
        log.warning("Gemini %s trả lời bị cắt (MAX_TOKENS), vẫn dùng phần đã có.", model)
    return text


def _gemini_call(cfg, prompt, system, image, web=False):
    parts = [{"text": prompt}]
    if image:
        parts.insert(0, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if web:  # cho Gemini tra Google (giá vàng, tỷ giá, tin tức...)
        body["tools"] = [{"google_search": {}}]
    first_family = None
    server_busy_models = 0
    tried = daily = minute = bad_request = 0
    last_400 = ""
    for model in _gemini_candidates(cfg)[:MAX_MODELS_TRIED]:
        family = "lite" if "lite" in model else "flash"
        if server_busy_models and family == first_family:
            log.warning("Bỏ qua %s: cùng cụm server đang nghẽn.", model)
            continue  # cùng cụm server đang nghẽn: thử vô ích
        tried += 1
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            _count_raw(cfg, model)
            try:
                res = _http(cfg, "POST", f"{GEMINI_URL}/models/{model}:generateContent", _gemini_headers(cfg), body)
                return _gemini_text(res, model), model
            except HTTPStatusError as e:
                code, low = e.code, (e.body or "").lower()
                if code == 404:
                    log.warning("Gemini %s không còn (404), thử model kế.", model)
                    _mark_gone(cfg, model)
                    break
                if code == 429 and body.get("tools"):
                    # Gói free: quota "tra Google" (grounding) riêng và rất thấp, model Gemini 3.x thường là 0,
                    # trong khi gọi thường vẫn còn quota. Hỏi lại ngay không tra web, báo AI là không có số liệu mới.
                    log.warning("Gemini %s từ chối tra web (429: %s), hỏi lại không tra web.", model,
                                _redact(cfg, (e.body or "")[:300]).replace("\n", " "))
                    body.pop("tools")
                    parts[-1]["text"] += NO_WEB_NOTE
                    continue
                if code == 429 and _is_daily_429(e.body):
                    daily += 1
                    _mark_exhausted(cfg, model)
                    break
                if code == 429:
                    minute += 1
                    log.warning("Gemini %s giới hạn lượt/phút (429: %s), thử model kế.", model,
                                _redact(cfg, (e.body or "")[:300]).replace("\n", " "))
                    break
                if code in (500, 503, 504) and attempt < RETRY_ATTEMPTS:
                    log.warning("Gemini %s nghẽn (%s), thử lại lần %d.", model, code, attempt + 1)
                    time.sleep(RETRY_WAIT_SECONDS)
                    continue
                if code in (500, 503, 504):
                    first_family = first_family or family
                    server_busy_models += 1
                    log.warning("Gemini %s vẫn nghẽn (%s) sau %d lần, đổi model.", model, code, attempt)
                    if server_busy_models > 1:
                        raise AIError("Server Gemini đang quá tải. Mình dùng nội dung có sẵn, lát nữa tự thử lại.")
                    break
                key_like = "api key" in low or "api_key" in low
                if code == 400 and body.get("tools") and not key_like:
                    log.warning("Gemini %s không cho tra web, hỏi lại không tra web.", model)
                    body.pop("tools")
                    parts[-1]["text"] += NO_WEB_NOTE
                    continue
                if code == 400 and not key_like and bad_request < MAX_BAD_REQUEST_MODELS - 1:
                    bad_request += 1  # 400 chung chung: model này không nhận, thử model kế trước khi bỏ cuộc
                    last_400 = errors.http(code, e.body)
                    log.warning("Gemini %s trả 400 (%s), thử model kế.", model, errors.http(code, e.body))
                    break
                if code in (400, 401, 403):
                    key_err = code in (401, 403) or "api key" in low or "api_key" in low
                    raise AIError(f"Gemini từ chối: {errors.http(code, e.body)}. "
                                  "Nếu do key: kiểm tra GEMINI_API_KEY trong config/secrets.env.", permanent=key_err)
                raise AIError(f"Gemini lỗi: {errors.http(code, e.body)}.")
    if last_400 and not (minute or server_busy_models):
        raise AIError(f"Gemini từ chối: {last_400}. Nếu do key: kiểm tra GEMINI_API_KEY trong config/secrets.env.")
    if minute or server_busy_models:
        raise AIError("Gemini đang giới hạn lượt gọi hoặc quá tải, lát nữa thử lại. Bot dùng nội dung có sẵn.")
    if daily or not tried:
        raise AIError("Các model Gemini đều hết quota hôm nay. Không mất tiền, quota tự reset khoảng 14–15h "
                      "chiều giờ VN. Bot dùng nội dung có sẵn.", daily_quota=True)
    raise AIError("Các model Gemini đều không dùng được hôm nay (model bị khai tử). Bot dùng nội dung có sẵn.")


# ------------------------------------------------------------ Claude

def _claude_call(cfg, prompt, system, image, web=False):
    content = [{"type": "text", "text": prompt}]
    if image:
        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(image).decode()}})
    body = {"model": cfg.get("claude_model") or "claude-opus-5-5", "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system
    if web:  # công cụ tìm kiếm web của Claude (tính phí theo lượt tìm)
        body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
    headers = {"x-api-key": cfg["anthropic_api_key"], "anthropic-version": "2023-06-01"}
    try:
        try:
            res = _http(cfg, "POST", CLAUDE_URL, headers, body)
        except HTTPStatusError as e:
            if e.code != 400 or not web:
                raise
            log.warning("Claude không cho tra web (%s), hỏi lại không tra web.", _redact(cfg, e))
            body.pop("tools")
            res = _http(cfg, "POST", CLAUDE_URL, headers, body)
    except HTTPStatusError as e:
        if e.code == 429:
            raise AIError("Claude đang giới hạn lượt gọi, lát nữa thử lại.")
        if e.code in (401, 403):
            raise AIError("Claude từ chối key. Kiểm tra ANTHROPIC_API_KEY trong config/secrets.env.", permanent=True)
        raise AIError(f"Claude lỗi: {errors.http(e.code, e.body)}.")
    stop = res.get("stop_reason")
    if stop == "refusal":
        raise AIError("Claude từ chối yêu cầu này.")
    text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise AIError(STOP_REASONS["MAX_TOKENS"] if stop == "max_tokens" else "AI trả về rỗng.")
    if stop == "max_tokens":
        log.warning("Claude trả lời bị cắt (max_tokens), vẫn dùng phần đã có.")
    return text, res.get("model") or body["model"]


# ------------------------------------------------------------ public

def generate(cfg, prompt, system="", image=None, purpose="", web=False):
    """Trả về (text, model). Lỗi thì raise AIError (nội dung lời nhắn đã thân thiện).
    web=True: cho AI tra web khi cần thông tin mới (giá vàng, tỷ giá, tin tức); model không hỗ trợ thì bỏ qua."""
    p = provider(cfg)
    system = ai_context.ensure_context(cfg, system)  # AI không có trí nhớ: lần gọi nào cũng kèm đủ BỐI CẢNH
    words_in = _words(prompt) + _words(system)
    if not p:
        log.info("AI bỏ qua (%s): chưa cấu hình key.", purpose)
        raise AIError("Chưa cấu hình API key cho AI.", permanent=True)
    cache = _model_cache(cfg)
    if cache.get("offline_until", 0) > time.time():
        log.info("AI bỏ qua (%s): đang nghỉ vì hết quota tới %s.", purpose,
                 dt.datetime.fromtimestamp(cache["offline_until"]).strftime("%H:%M"))
        raise AIError("AI tạm không dùng được (hết quota), bot dùng nội dung có sẵn. Vài tiếng nữa tự thử lại.")
    started = time.time()
    try:
        text, model = (_gemini_call if p == "gemini" else _claude_call)(cfg, prompt, system, image, web)
    except AIError as e:
        msg = _redact(cfg, e)
        e.args = (msg,)  # body lỗi có thể chép lại key: không đưa ra log / Telegram
        log.warning("AI fail provider=%s purpose=%s web=%s in=%d %dms permanent=%s: %s", p, purpose, web, words_in,
                    (time.time() - started) * 1000, e.permanent, msg)
        _log_prompt(cfg, purpose, "", system, prompt, image, web, started, error=msg)
        audit("AI_ERROR", f"{purpose}: {msg}")
        if e.daily_quota:
            # Mọi model hết quota ngày: dùng rule/nội dung có sẵn, 3 tiếng sau thử lại. quota_exhausted vẫn nhớ
            # tới mốc reset của Google (08:00 UTC) nên lần sau bỏ qua các model đã hết.
            _update_cache(cfg, offline_until=time.time() + 3 * 3600, rule_parser_mode=_today())
            log.warning("AI nghỉ 3 tiếng (hết quota ngày mọi model), dùng rule/nội dung có sẵn.")
        raise
    except Exception as e:  # lỗi lạ (mạng, SDK...) cũng không được làm bot chết
        msg = _redact(cfg, f"{type(e).__name__}: {e}")
        log.warning("AI fail provider=%s purpose=%s web=%s in=%d %dms lỗi bất ngờ: %s", p, purpose, web, words_in,
                    (time.time() - started) * 1000, msg, exc_info=True)
        _log_prompt(cfg, purpose, "", system, prompt, image, web, started, error=msg)
        audit("AI_ERROR", f"{purpose}: {msg}")
        raise AIError(f"Không gọi được AI: {_redact(cfg, errors.explain(e))}.")
    _update_cache(cfg, model=model)
    _count_usage(cfg, model, purpose, words_in, _words(text))
    _log_prompt(cfg, purpose, model, system, prompt, image, web, started, answer=text)
    log.info("AI ok provider=%s model=%s purpose=%s web=%s in=%d out=%d %dms", p, model, purpose, web, words_in,
             _words(text), (time.time() - started) * 1000)
    audit("AI_CALL", f"{purpose} model={model}")
    return text, model

