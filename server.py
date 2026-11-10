#!/usr/bin/env python3
"""AI Roundtable v4 - local multi-LLM group discussion with admin panel. Stdlib only. Binds 127.0.0.1 only."""
import json, os, socket, threading, time, urllib.request, urllib.error, datetime, re, tempfile, subprocess, uuid, html as htmlmod
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = "127.0.0.1", int(os.environ.get("ROUNDTABLE_PORT", "8765"))
ENV_PATH = os.path.join(BASE, ".env")

def app_log(msg):
    """Request/error log to stdout (start.sh redirects to server.log). No secrets."""
    try:
        from zoneinfo import ZoneInfo
        ts = datetime.datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M:%S")
        zone = "Europe/Berlin"
    except Exception:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        zone = "local"
    print(f"{ts} [{zone}] {msg}", flush=True)

SETTINGS_PATH = os.path.join(BASE, "settings.json")
TEST_FRESH_SECONDS = 30 * 60
FLOCK = threading.Lock()
SLOCK = threading.Lock()

# ---------- config / env / settings ----------
def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def write_env_key(name, value):
    """Set/replace (or remove if value empty) one key in .env; file stays chmod 600."""
    with FLOCK:
        lines = open(ENV_PATH, encoding="utf-8").read().splitlines() if os.path.exists(ENV_PATH) else []
        out, done = [], False
        for line in lines:
            if re.match(r"^\s*" + re.escape(name) + r"\s*=", line):
                if not done: out.append(f"{name}={value}"); done = True
                continue
            out.append(line)
        if not done: out.append(f"{name}={value}")
        fd, tmp = tempfile.mkstemp(dir=BASE, prefix=".env.tmp")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f: f.write("\n".join(out) + "\n")
        os.replace(tmp, ENV_PATH); os.chmod(ENV_PATH, 0o600)

def load_cfg():
    return json.load(open(os.path.join(BASE, "providers.json"), encoding="utf-8"))

def load_settings():
    cfg = load_cfg()
    s = {}
    if os.path.exists(SETTINGS_PATH):
        try: s = json.load(open(SETTINGS_PATH, encoding="utf-8"))
        except Exception: s = {}
    if not s.get("participants"):
        s["participants"] = [dict(p, enabled=not cfg["providers"].get(p["provider"], {}).get("mock", False))
                             for p in cfg["participants"]]
    else:
        have_n = {p["name"] for p in s["participants"]}
        have_pm = {(p["provider"], p["model"]) for p in s["participants"]}
        for p in cfg.get("participants", []):
            if p["name"] in have_n or (p["provider"], p["model"]) in have_pm: continue
            s["participants"].append(dict(p, enabled=p.get("enabled", True)))
    s.setdefault("tests", {})
    roles = load_roles()
    c = s.setdefault("config", {})
    c.setdefault("rounds", 2); c.setdefault("roles_enabled", True); c.setdefault("judge_enabled", False)
    c.setdefault("manager_enabled", True); c.setdefault("compact_enabled", True); c.setdefault("timeout", 60)
    c.setdefault("office_enabled", True)
    if c.get("access_mode") not in ("ask", "autonomy"):
        c["access_mode"] = "ask"
    perms = c.setdefault("permissions", {})
    perms.setdefault("mode", c["access_mode"])
    roles_p = perms.setdefault("roles", {})
    for role, tools in DEFAULT_ROLE_PERMS.items():
        roles_p.setdefault(role, list(tools))
    # wallet/payments can never be a standing grant
    for role, tools in list(roles_p.items()):
        roles_p[role] = [t for t in tools if t not in ALWAYS_APPROVE]
    perms["always_approve"] = sorted(ALWAYS_APPROVE)

    try: c["timeout"] = max(15, min(180, int(c.get("timeout") or 60)))
    except Exception: c["timeout"] = 60
    names = [p["name"] for p in s["participants"]]
    if not c.get("judge") or c["judge"] not in names:
        c["judge"] = next((n for n in JUDGE_PREF if n in names), names[0] if names else "")
    if not c.get("manager") or c["manager"] not in names:
        c["manager"] = next((n for n in MANAGER_PREF if n in names), c.get("judge") or (names[0] if names else ""))
    if not c.get("secretary") or c["secretary"] not in names or c.get("secretary") == c.get("manager"):
        c["secretary"] = next((n for n in SECRETARY_PREF if n in names and n != c.get("manager")), next((n for n in names if n != c.get("manager")), c.get("manager") or ""))
    used = 0
    order = sorted(range(len(s["participants"])), key=lambda i: (s["participants"][i]["name"] == c["judge"], STRENGTH.index(s["participants"][i]["name"]) if s["participants"][i]["name"] in STRENGTH else 99))
    for i in order:
        p = s["participants"][i]
        if p.get("role") not in roles or p.get("role") == "judge":
            p["role"] = ROLE_ORDER[used % len(ROLE_ORDER)]; used += 1
            p["persona"] = roles[p["role"]]["desc"]
        elif not p.get("persona"):
            p["persona"] = roles[p["role"]]["desc"]
    return s

def load_roles():
    return json.load(open(os.path.join(BASE, "roles.json"), encoding="utf-8"))

# strongest first: heavier roles go to stronger models
STRENGTH = ["GPT-OSS 120B (Groq)", "Nemotron 3 Ultra", "Gemini 3 Flash", "Command A (Cohere)", "Qwen 3.8 27B (Groq)",
            "Nemotron 3.5 Super VL", "Gemini 3.1 Flash Lite", "GPT-OSS 20B (Groq)", "Nemotron 3 Nano Omni", "Grok", "Kimi", "DeepSeek",
            "Mistral", "Gemma 4 31B", "Nemotron 3.5 Lightning", "Dots-3 Note", "Flint (Recursive)", "North Mini Code (Cohere)",
            "Gemma 4 26B", "Xing 4.0 (Xingchen)", "Cerebras", "LFM-2.5 2.6B (Liquid)", "LFM-3 1.7B (Liquid)"]
JUDGE_PREF = ["GPT-OSS 120B (Groq)", "Nemotron 3 Ultra", "Gemini 3 Flash", "Gemini 3.1 Flash Lite"]
MANAGER_PREF = ["Gemini 3.1 Flash Lite", "GPT-OSS 20B (Groq)", "Gemini 3 Flash", "GPT-OSS 120B (Groq)"]
SECRETARY_PREF = ["Gemini 3 Flash", "Gemini 3.1 Flash Lite", "GPT-OSS 20B (Groq)", "Command A (Cohere)"]
ROLE_ORDER = ["philosopher", "devil", "physicist", "math", "skeptic", "software", "economist", "medical",
              "psychologist", "lawyer", "historian", "engineer", "humanities"]
TOOL_DEFS = {
    "web_read": "خواندن وب (فقط صفحات عمومی HTTPS)",
    "code_run": "اجرای کد در پوشهٔ سندباکس",
    "file_read": "خواندن فایل در سندباکس",
    "file_write": "نوشتن فایل در سندباکس",
    "report_write": "نوشتن گزارش کار",
    "assign_tasks": "تخصیص کار به کارکنان",
    "speak_to_user": "صحبت مستقیم با کاربر",
    "wallet": "کیف پول",
    "payments": "پرداخت",
}
ALWAYS_APPROVE = frozenset({"wallet", "payments"})
DEFAULT_ROLE_PERMS = {
    "boss": ["assign_tasks", "speak_to_user", "web_read", "report_write"],
    "secretary": ["report_write", "file_read", "file_write"],
    "software": ["web_read", "code_run", "file_read", "file_write"],
    "engineer": ["web_read", "code_run", "file_read", "file_write"],
    "skeptic": ["web_read"], "historian": ["web_read"], "humanities": ["web_read"],
    "lawyer": ["web_read"], "medical": ["web_read"], "psychologist": ["web_read"],
    "philosopher": ["web_read"], "physicist": ["web_read"], "math": ["web_read"],
    "economist": ["web_read"], "devil": ["web_read"], "judge": [],
    "optimizer": ["web_read", "file_read", "report_write"],
    "inspector": ["web_read", "file_read", "report_write"],
}
SANDBOX = os.path.join(BASE, "sandbox")

SLOW_MODELS = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": 45,
}
PUBLIC_MODEL_LISTS = {"openrouter", "chutes", "huggingface", "novita", "deepinfra"}

def save_settings(s):
    with FLOCK:
        fd, tmp = tempfile.mkstemp(dir=BASE, prefix=".settings.tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        os.chmod(SETTINGS_PATH, 0o600)

def has_key(prov_cfg, env=None):
    if prov_cfg.get("mock"): return True
    env = env if env is not None else load_env()
    if not bool(env.get(prov_cfg.get("env", ""), "")): return False
    for extra in prov_cfg.get("extra_env") or []:
        if not env.get(extra, ""): return False
    return True

# ---------- provider calls ----------
def classify(code, text):
    t = (text or "").lower()
    if code == 413 or "request too large" in t or "too large for model" in t:
        return "too_large"
    if code == 429 or "resource_exhausted" in t or "rate limit" in t:
        return "no_balance" if ("limit: 0" in t or "insufficient" in t) else "rate_limited"
    if "credit" in t and ("no " in t or "insufficient" in t or "exhausted" in t or "purchase" in t or "doesn't have" in t or "does not have" in t):
        return "no_balance"
    if code == 402 or "insufficient balance" in t or "insufficient_quota" in t or "billing" in t or "credit" in t and "balance" in t:
        return "no_balance"
    if code in (401, 403) or "api key not valid" in t or "api_key_invalid" in t or "invalid api key" in t or "incorrect api key" in t or "invalid_api_key" in t or "authentication" in t:
        return "invalid_key"
    if code == 404 or "model_not_found" in t or "not found" in t and "model" in t or "does not exist" in t or "model not exist" in t or "unknown model" in t or "invalid model" in t:
        return "model_not_found"
    if "timeout" in t:
        return "timeout"
    if code == 429 or "rate limit" in t or "resource_exhausted" in t or "quota" in t or "tokens per minute" in t or "tpm" in t:
        return "rate_limited"
    return "error"

class ProviderError(Exception):
    def __init__(self, status, detail): super().__init__(detail); self.status, self.detail = status, detail

def expand_url(url, env=None):
    env = env if env is not None else load_env()
    missing = []
    def repl(m):
        v = env.get(m.group(1), "")
        if not v: missing.append(m.group(1))
        return v
    out = re.sub(r"\{([A-Z][A-Z0-9_]*)\}", repl, url)
    if missing:
        raise ProviderError("no_key", "missing in .env: " + ", ".join(missing))
    return out

def http_json(url, key, body=None, timeout=120):
    headers = {"Content-Type": "application/json",
               "HTTP-Referer": "http://127.0.0.1", "X-Title": "AI Roundtable",
               "User-Agent": "ai-roundtable/4.0 (+local)", "Accept": "application/json"}
    if key: headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try: return json.loads(raw)
            except ValueError:
                raise ProviderError("error", f"service returned a non-JSON reply ({r.headers.get('Content-Type')}): {raw[:80]!r} - endpoint not usable")
    except urllib.error.HTTPError as e:
        full = e.read().decode(errors="replace")
        txt = re.sub(r"\s+", " ", full)[:600]
        raise ProviderError(classify(e.code, full[:4000]), f"HTTP {e.code}: {txt}")
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
            raise ProviderError("timeout", f"timeout after {timeout}s (service busy / high demand)")
        raise ProviderError("error", f"network: {reason}")
    except (TimeoutError, socket.timeout):
        raise ProviderError("timeout", f"timeout after {timeout}s (service busy / high demand)")

def message_text(msg):
    if not isinstance(msg, dict): return ""
    c = msg.get("content")
    if isinstance(c, list):
        c = "".join((p.get("text") or p.get("content") or "") if isinstance(p, dict) else str(p) for p in c)
    if not c:
        c = msg.get("reasoning_content") or msg.get("reasoning") or ""
    return c or ""

def extract_usage(data, messages, text):
    u = (data or {}).get("usage") or {}
    prompt = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    completion = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    total = int(u.get("total_tokens") or 0) or (prompt + completion)
    estimated = False
    if not total:
        raw = sum(len(m.get("content") or "") if isinstance(m.get("content"), str) else 0 for m in (messages or [])) + len(text or "")
        total = max(1, raw // 4)
        estimated = True
    return {"prompt": prompt, "completion": completion, "total": total, "estimated": estimated}

def chat(provider, model, messages, max_tokens=2048, timeout=None):
    cfg = load_cfg()["providers"].get(provider)
    if not cfg: raise ProviderError("error", f"unknown provider {provider}")
    if cfg.get("mock"):
        time.sleep(0.15)
        last = messages[-1]["content"].split("\n\n")[-2] if "\n\n" in messages[-1]["content"] else messages[-1]["content"]
        txt = f"(mock reply) I heard: {last[:120]}"
        return txt, extract_usage({}, messages, txt)
    key = load_env().get(cfg["env"], "")
    if not key: raise ProviderError("no_key", f"{cfg['env']} missing in .env")
    if model == "auto": model = resolve_auto(provider)
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    body.update(cfg.get("extra", {}))
    tmo = timeout if timeout is not None else cfg.get("timeout", 120)
    data = http_json(expand_url(cfg["base_url"]).rstrip("/") + "/chat/completions", key, body, timeout=tmo)
    if "error" in data and not data.get("choices"):
        txt = json.dumps(data["error"])[:400]; raise ProviderError(classify(200, txt), txt)
    ch = (data.get("choices") or [{}])[0]
    txt = message_text(ch.get("message") or {}) or (ch.get("text") or "")
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    return txt, extract_usage(data, messages, txt)

AUTO_CACHE = {}
def resolve_auto(provider):
    """'auto' model: pick a chat model from the provider's /models list (cached)."""
    if provider not in AUTO_CACHE:
        ids = [i for i in list_models(provider) if not re.search(r"embed|whisper|tts|guard|rerank|vision|image|audio", i)]
        if not ids: raise ProviderError("model_not_found", "no models listed")
        pref = [i for i in ids if re.search(r"gpt-oss|llama|qwen", i)]
        AUTO_CACHE[provider] = (pref or ids)[0]
    return AUTO_CACHE[provider]

def test_target(provider, model):
    """Tiny request; stores result in settings under 'provider|model'."""
    try:
        chat(provider, model, [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=256)
        res = {"status": "ok", "detail": "OK" + (f" (auto -> {AUTO_CACHE.get(provider)})" if model == "auto" else "")}
    except ProviderError as e:
        res = {"status": e.status, "detail": e.detail[:600]}
    except Exception as e:
        res = {"status": "error", "detail": str(e)[:300]}
    res.update(time=time.time(), at=time.strftime("%Y-%m-%d %H:%M:%S"))
    with SLOCK:
        s = load_settings(); s["tests"][f"{provider}|{model}"] = res; save_settings(s)
    return res

def test_many(pairs):
    from concurrent.futures import ThreadPoolExecutor
    pairs = list(dict.fromkeys(pairs))
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(pairs, ex.map(lambda pm: test_target(*pm), pairs)))

def list_models(provider, free_only=False):
    cfg = load_cfg()["providers"].get(provider)
    if not cfg or cfg.get("mock"): return [cfg.get("default_model")] if cfg else []
    key = load_env().get(cfg["env"], "")
    if not key and provider not in PUBLIC_MODEL_LISTS: raise ProviderError("no_key", "no key")
    data = http_json(expand_url(cfg["base_url"]).rstrip("/") + "/models", key, timeout=30)
    if free_only:
        return sorted(m["id"] for m in data.get("data", []) if m.get("id", "").endswith(":free"))
    ids = [re.sub(r"^models/", "", m.get("id", "")) for m in data.get("data", [])]
    return sorted(i for i in ids if i)

# ---------- discussion ----------
STATE = {"thinking": None, "running": False, "topic": "", "messages": [], "status": "idle",
         "participants": [], "rounds": 0, "usage": {"prompt": 0, "completion": 0, "total": 0, "calls": 0, "estimated": 0},
         "mode": {}, "desks": [], "office": {}, "approvals": [], "office_events": []}
LOCK = threading.Lock()
STOP = threading.Event()

def empty_usage():
    return {"prompt": 0, "completion": 0, "total": 0, "calls": 0, "estimated": 0}

def add_usage(u):
    if not u: return
    with LOCK:
        tot = STATE.setdefault("usage", empty_usage())
        tot["prompt"] += int(u.get("prompt") or 0)
        tot["completion"] += int(u.get("completion") or 0)
        tot["total"] += int(u.get("total") or 0)
        tot["calls"] += 1
        if u.get("estimated"): tot["estimated"] += 1



def snapshot_desks():
    """Idle office floor plan from enabled participants (grey if no key)."""
    s = load_settings(); env = load_env(); roles = load_roles()
    conf = s.get("config") or {}
    provs = load_cfg().get("providers") or {}
    boss = conf.get("manager") or ""
    sec = conf.get("secretary") or ""
    desks = []
    for p in s.get("participants") or []:
        if not p.get("enabled"): continue
        pr = provs.get(p.get("provider"), {})
        ok = bool(pr) and has_key(pr, env)
        seat = "boss" if p["name"]==boss else "secretary" if p["name"]==sec else "employee"
        title = "مدیر" if seat=="boss" else "منشی" if seat=="secretary" else (roles.get(p.get("role") or "", {}) or {}).get("title", "")
        desks.append({"name": p["name"], "provider": p.get("provider",""), "model": p.get("model",""),
                      "role": p.get("role") or "", "role_title": title, "present": ok, "seat": seat,
                      "reason": "" if ok else "کلید لازمه"})
    return desks

def live_scorecard():
    """Build a live scorecard from messages + optional scorecard.json (no secrets)."""
    path = os.path.join(BASE, "scorecard.json")
    data = {"employees": {}, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    if os.path.isfile(path):
        try: data = json.load(open(path, encoding="utf-8"))
        except Exception: pass
    emps = data.setdefault("employees", {})
    with LOCK:
        msgs = list(STATE.get("messages") or [])
        desks = list(STATE.get("desks") or [])
        thinking = STATE.get("thinking") or {}
    if not desks:
        try: desks = snapshot_desks()
        except Exception: desks = []
    # ensure desks/participants appear
    names = {}
    for d in desks:
        names[d["name"]] = d
    for m in msgs:
        if m.get("kind") in ("internal","boss","secretary","mention","ai") and m.get("speaker") and m["speaker"]!="system":
            names.setdefault(m["speaker"], {"name": m["speaker"], "role": m.get("role",""), "role_title": m.get("role_title",""), "seat": "employee"})
    for name, d in names.items():
        e = emps.setdefault(name, {})
        e.setdefault("role", d.get("role") or "")
        e.setdefault("role_title", d.get("role_title") or "")
        e.setdefault("seat", d.get("seat") or "employee")
        e.setdefault("tokens", 0)
        e.setdefault("calls", 0)
        e.setdefault("rejects", 0)
        e.setdefault("accepts", 0)
        e.setdefault("fails", 0)
        e["current_work"] = ""
        if thinking.get("name")==name:
            e["current_work"] = STATE.get("status") or "working"
    # accumulate from this session messages (do not double-count file history into session totals — keep session fields separate)
    session = {}
    last_text = {}
    for m in msgs:
        name = m.get("speaker")
        if not name or name in ("system","Salar"): continue
        st = session.setdefault(name, {"tokens":0,"calls":0,"rejects":0,"accepts":0,"fails":0,"low_conf":0,"repeat":0,"last":""})
        u = m.get("usage") or {}
        st["tokens"] += int(u.get("total") or 0)
        if m.get("kind") in ("internal","boss","secretary","mention","ai"):
            st["calls"] += 1
        txt = m.get("text") or ""
        if txt in ("(empty report)","(empty reply)","(empty follow-up)"):
            st["fails"] += 1
        conf = (m.get("compact") or {}).get("confidence")
        try:
            if conf is not None and float(conf) < 0.5: st["low_conf"] += 1
        except Exception: pass
        prev = last_text.get(name)
        if prev and txt and prev[:80]==txt[:80]:
            st["repeat"] += 1
        last_text[name] = txt
        if m.get("kind")=="internal" and (m.get("to")=="boss" or not m.get("to")):
            e = emps.setdefault(name, {})
            e["current_work"] = e.get("current_work") or (txt[:80])
    for name, st in session.items():
        e = emps.setdefault(name, {})
        e["session_tokens"] = st["tokens"]
        e["session_calls"] = st["calls"]
        # fatigue 0-100
        fat = min(100, st["tokens"]/80.0 + st["fails"]*15 + st["low_conf"]*8 + st["repeat"]*10)
        fru = min(100, st["fails"]*20 + st["repeat"]*15 + e.get("rejects",0)*20)
        useful = min(100, max(0, st["calls"]*12 - st["fails"]*15 + e.get("accepts",0)*20))
        harm = min(100, e.get("rejects",0)*25 + st["low_conf"]*10)
        e["fatigue"] = round(fat,1)
        e["frustration"] = round(fru,1)
        e["usefulness"] = round(useful,1)
        e["harm"] = round(harm,1)
        e["contribution"] = int(st["tokens"] + useful)
    data["employees"] = emps
    return data


SCORECARD_PATH = os.path.join(BASE, "scorecard.json")
PROJECT_PATH = os.path.join(BASE, "project.json")
PROPOSALS_PATH = os.path.join(BASE, "deputy-proposals.json")
ASK_QUEUE_TOOLS = frozenset({"web_read", "code_run", "file_write", "report_write"})

def berlin_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return datetime.datetime.now().astimezone()

def iso_berlin(dt=None):
    dt = dt or berlin_now()
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
        except Exception:
            pass
    return dt.isoformat(timespec="seconds")

def _load_json(path, default):
    if os.path.isfile(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=BASE, prefix=".data.tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def access_mode():
    try:
        m = (load_settings().get("config") or {}).get("access_mode") or "ask"
    except Exception:
        m = "ask"
    return m if m in ("ask", "autonomy") else "ask"

def record_call(p, usage, latency, ok=True, err=""):
    if not p or not p.get("name"):
        return
    data = _load_json(SCORECARD_PATH, {"employees": {}, "writeups": [], "history": [], "updated": ""})
    e = data.setdefault("employees", {}).setdefault(p["name"], {})
    e["role"] = p.get("role") or e.get("role") or ""
    e["role_title"] = p.get("role_title") or e.get("role_title") or ""
    e["seat"] = p.get("office_seat") or e.get("seat") or "employee"
    e["calls"] = int(e.get("calls") or 0) + 1
    tot = int((usage or {}).get("total") or 0)
    e["tokens"] = int(e.get("tokens") or 0) + tot
    e["last_latency"] = round(float(latency or 0), 2)
    prev = float(e.get("avg_latency") or 0)
    n = int(e.get("calls") or 1)
    e["avg_latency"] = round((prev * (n - 1) + float(latency or 0)) / n, 2)
    if ok:
        e["successes"] = int(e.get("successes") or 0) + 1
    else:
        e["fails"] = int(e.get("fails") or 0) + 1
        if err:
            e["last_error"] = str(err)[:200]
    e["updated"] = iso_berlin()
    data["updated"] = e["updated"]
    _save_json(SCORECARD_PATH, data)

def optimizer_writeup(topic=""):
    """Instant heuristic scorecard write-up (no extra LLM tokens)."""
    live = live_scorecard()
    stored = _load_json(SCORECARD_PATH, {"employees": {}, "writeups": [], "history": []})
    emps = stored.setdefault("employees", {})
    # merge live metrics
    for name, e in (live.get("employees") or {}).items():
        emps.setdefault(name, {}).update({k: v for k, v in e.items() if v is not None})
    writeups = []
    for name, e in emps.items():
        calls = int(e.get("calls") or e.get("session_calls") or 0)
        fails = int(e.get("fails") or 0)
        lat = float(e.get("avg_latency") or e.get("last_latency") or 0)
        toks = int(e.get("tokens") or e.get("session_tokens") or 0)
        fat = float(e.get("fatigue") or 0)
        useful = float(e.get("usefulness") or 0)
        strengths, weak = [], []
        if calls and fails == 0:
            strengths.append("پاسخ‌های کامل بدون خطا")
        if lat and lat < 8:
            strengths.append("سریع (میانگین %.1fs)" % lat)
        if useful >= 40:
            strengths.append("سودمندی بالا")
        if toks and calls and toks / max(calls, 1) < 400:
            strengths.append("مصرف توکن معقول")
        if fails:
            weak.append("خطا یا پاسخ خالی (%d)" % fails)
        if lat and lat > 20:
            weak.append("کند (میانگین %.1fs)" % lat)
        if fat >= 70:
            weak.append("خستگی بالا — بهتر است استراحت/چرخش کند")
        if not strengths and not weak:
            strengths.append("هنوز دادهٔ کافی نیست")
        text = "نقاط قوت: " + ("؛ ".join(strengths) or "—") + ". ضعف‌ها: " + ("؛ ".join(weak) or "مورد جدی نیست") + "."
        rec = {"name": name, "role": e.get("role_title") or e.get("role") or "",
               "strengths": strengths, "weaknesses": weak, "text": text,
               "latency": lat, "tokens": toks, "calls": calls, "successes": int(e.get("successes") or 0),
               "fails": fails}
        writeups.append(rec)
        e["writeup"] = text
        e["strengths"] = strengths
        e["weaknesses"] = weak
    stored["employees"] = emps
    stored["writeups"] = writeups
    stored["updated"] = iso_berlin()
    hist = stored.setdefault("history", [])
    hist.append({"at": stored["updated"], "topic": topic, "writeups": writeups})
    stored["history"] = hist[-30:]
    _save_json(SCORECARD_PATH, stored)
    app_log("optimizer writeup employees=%d" % len(writeups))
    return stored

def inspector_proposals(topic=""):
    """Heuristic inspector/deputy recommendations for the boss (not auto-applied)."""
    stored = _load_json(SCORECARD_PATH, {"employees": {}})
    emps = stored.get("employees") or {}
    conf = load_settings().get("config") or {}
    boss = conf.get("manager") or ""
    props = _load_json(PROPOSALS_PATH, {"proposals": []})
    existing = props.get("proposals") or []
    # keep pending + last applied
    new = []
    scored = []
    for name, e in emps.items():
        useful = float(e.get("usefulness") or 0)
        fails = int(e.get("fails") or 0)
        calls = int(e.get("calls") or e.get("session_calls") or 0)
        fat = float(e.get("fatigue") or 0)
        harm = float(e.get("harm") or 0)
        seat = e.get("seat") or "employee"
        scored.append((useful + calls * 2 - fails * 8, name, e, seat))
    scored.sort(reverse=True)
    def add(action, target, value, reason):
        # skip duplicate pending
        for p in existing:
            if p.get("status") == "pending" and p.get("action") == action and p.get("target") == target and str(p.get("value")) == str(value):
                return
        rec = {"id": uuid.uuid4().hex[:10], "created_at": iso_berlin(), "from": "inspector",
               "action": action, "target": target, "value": value, "reason": reason, "status": "pending",
               "topic": topic}
        new.append(rec)
    if scored:
        best = scored[0]
        if best[2].get("seat") != "boss" and best[1] != boss and best[0] > 8:
            add("set_manager", best[1], best[1],
                "بازرس: %s بالاترین کارنامه را دارد (سودمندی/موفقیت بهتر از بقیه). پیشنهاد می‌شود به‌عنوان مدیر بررسی شود. تصمیم با مدیر/کاربر است." % best[1])
        for _, name, e, seat in scored:
            if int(e.get("fails") or 0) >= 2 and seat == "employee":
                add("set_role", name, "skeptic",
                    "بازرس: %s چند بار خطا یا پاسخ خالی داشته. پیشنهاد تغییر نقش به شکاک (کار سبک‌تر، فقط خواندن) تا کارنامه بهتر شود." % name)
            if float(e.get("fatigue") or 0) >= 70:
                add("rest", name, "",
                    "بازرس: %s خستگی بالایی دارد. پیشنهاد استراحت یا چرخش کار در دور بعد. تغییری در تنظیمات اعمال نمی‌شود مگر تأیید کنی." % name)
    if not new and scored:
        # at least a status recommendation so the admin pane is useful
        name = scored[0][1]
        add("note", name, "",
            "بازرس: در این دور پیشنهاد اجباری نیست. %s فعلاً بهترین کارنامه را دارد. کارمندان را با کارنامه بسنج و در صورت نیاز نقش‌ها را عوض کن." % name)
    if new:
        props["proposals"] = (existing + new)[-40:]
        props["updated"] = iso_berlin()
        _save_json(PROPOSALS_PATH, props)
        app_log("inspector proposals added=%d" % len(new))
    return props

def apply_proposal(pid):
    props = _load_json(PROPOSALS_PATH, {"proposals": []})
    rec = next((p for p in (props.get("proposals") or []) if p.get("id") == pid), None)
    if not rec:
        raise ValueError("پیشنهاد پیدا نشد")
    if rec.get("status") != "pending":
        raise ValueError("این پیشنهاد قبلاً اعمال یا رد شده")
    s = load_settings()
    names = [p["name"] for p in s["participants"]]
    action, target, value = rec.get("action"), rec.get("target"), rec.get("value")
    if action == "set_manager":
        if target not in names:
            raise ValueError("شرکت‌کننده نامعتبر")
        s["config"]["manager"] = target
    elif action == "set_secretary":
        if target not in names:
            raise ValueError("شرکت‌کننده نامعتبر")
        s["config"]["secretary"] = target
    elif action == "set_role":
        roles = load_roles()
        if value not in roles:
            raise ValueError("نقش نامعتبر")
        found = False
        for p in s["participants"]:
            if p["name"] == target:
                p["role"] = value
                p["persona"] = roles[value].get("desc", "")
                found = True
        if not found:
            raise ValueError("شرکت‌کننده نامعتبر")
    elif action in ("rest", "note"):
        pass
    else:
        raise ValueError("اقدام ناشناخته")
    rec["status"] = "applied"
    rec["applied_at"] = iso_berlin()
    save_settings(s)
    _save_json(PROPOSALS_PATH, props)
    app_log("proposal applied id=%s action=%s target=%s" % (pid, action, target))
    return rec

def start_project(topic, cont=False, rounds=0):
    proj = _load_json(PROJECT_PATH, {})
    same = cont and proj.get("goal") and (not topic or topic == proj.get("goal") or topic in (proj.get("goal") or ""))
    if same:
        proj["goal"] = topic or proj.get("goal")
        proj["status"] = "running"
        if rounds:
            proj["rounds_total"] = rounds
        proj["updated_at"] = iso_berlin()
    else:
        proj = {
            "goal": topic, "started_at": iso_berlin(), "updated_at": iso_berlin(),
            "progress": 0, "eta": "", "rounds_done": 0, "rounds_total": rounds or 0,
            "days_elapsed": 0, "remaining_pct": 100, "status": "running",
        }
    _save_json(PROJECT_PATH, proj)
    return enrich_project(proj)

def tick_project(rnd=None, rounds=None, finished=False, stopped=False):
    proj = _load_json(PROJECT_PATH, {})
    if not proj:
        return proj
    if rnd is not None:
        proj["rounds_done"] = rnd
    if rounds is not None:
        proj["rounds_total"] = rounds
    if finished:
        proj["progress"] = 100
        proj["remaining_pct"] = 0
        proj["status"] = "finished"
        proj["eta"] = iso_berlin()
    elif stopped:
        proj["status"] = "stopped"
    else:
        total = max(int(proj.get("rounds_total") or 1), 1)
        done = int(proj.get("rounds_done") or 0)
        proj["progress"] = min(95, int(100 * done / total))
        proj["remaining_pct"] = max(0, 100 - int(proj["progress"]))
    proj["updated_at"] = iso_berlin()
    # elapsed / ETA
    try:
        start = datetime.datetime.fromisoformat(proj["started_at"])
        now = berlin_now()
        if start.tzinfo is None:
            start = start.replace(tzinfo=now.tzinfo)
        elapsed = max(0, (now - start).total_seconds())
        proj["days_elapsed"] = round(elapsed / 86400.0, 4)
        prog = int(proj.get("progress") or 0)
        if 0 < prog < 100:
            total_est = elapsed / (prog / 100.0)
            remain = max(0, total_est - elapsed)
            proj["eta"] = iso_berlin(now + datetime.timedelta(seconds=remain))
    except Exception:
        pass
    _save_json(PROJECT_PATH, proj)
    return enrich_project(proj)

def enrich_project(proj):
    proj = dict(proj or {})
    try:
        if proj.get("started_at"):
            start = datetime.datetime.fromisoformat(proj["started_at"])
            now = berlin_now()
            if start.tzinfo is None:
                start = start.replace(tzinfo=now.tzinfo)
            proj["days_elapsed"] = round(max(0, (now - start).total_seconds()) / 86400.0, 4)
            proj["started_at_label"] = start.strftime("%Y-%m-%d %H:%M") + " (Europe/Berlin)"
    except Exception:
        proj["started_at_label"] = proj.get("started_at") or "—"
    return proj

def finalize_session(topic, status="finished"):
    try:
        optimizer_writeup(topic)
    except Exception as e:
        app_log("optimizer_writeup failed: %s" % e)
    try:
        inspector_proposals(topic)
    except Exception as e:
        app_log("inspector_proposals failed: %s" % e)
    try:
        tick_project(finished=(status == "finished"), stopped=(status == "stopped"))
    except Exception as e:
        app_log("tick_project failed: %s" % e)

def add_msg(speaker, text, kind="ai", provider="", model="", role="", role_title="", usage=None, compact=None):
    rec = {"speaker": speaker, "text": text, "kind": kind, "provider": provider, "model": model,
           "role": role, "role_title": role_title, "t": time.strftime("%H:%M:%S")}
    if usage: rec["usage"] = usage
    if compact: rec["compact"] = compact
    with LOCK:
        STATE["messages"].append(rec)
        evs = STATE.setdefault("office_events", [])
        if kind == "internal":
            dest = rec.get("to") or "boss"
            evs.append({"id": f"{time.time():.3f}-{speaker}", "type": "deliver" if dest=="boss" else "assign",
                        "frm": rec.get("from") or speaker, "to": dest, "text": (text or "")[:80], "t": rec["t"]})
            STATE["office_events"] = evs[-80:]
        if kind == "boss":
            evs.append({"id": f"{time.time():.3f}-boss", "type": "speak", "frm": speaker, "to": "user", "text": (text or "")[:80], "t": rec["t"]})
            STATE["office_events"] = evs[-80:]
    add_usage(usage)

def format_compact(c):
    if not c: return ""
    parts = [f'claim={c.get("claim") or ""}']
    if c.get("target"): parts.append(f'target={c["target"]}')
    if c.get("objection"): parts.append(f'obj={c["objection"]}')
    if c.get("evidence"): parts.append(f'ev={c["evidence"]}')
    if c.get("confidence") is not None: parts.append(f'conf={c["confidence"]}')
    return " | ".join(parts)

def transcript_lines(for_judge=False):
    with LOCK: msgs = list(STATE["messages"])
    compact_on = bool((STATE.get("mode") or {}).get("compact"))
    out = []
    for m in msgs:
        if m["kind"] in ("system", "judge"): continue
        who = "Salar (human moderator)" if m["kind"] == "user" else m["speaker"] + (f" — {m['role_title']}" if m.get("role_title") else "")
        if compact_on and m.get("compact") and not (for_judge and False):
            out.append(f"[{who}]: {format_compact(m['compact'])}")
        else:
            out.append(f"[{who}]: {m['text']}")
    return out

DEBATE_RULES = ("This is a critical debate, NOT a consensus exercise. Rules for every turn: "
    "(1) Name at least one earlier speaker and point out a specific weakness, gap, hidden assumption or error in their argument. "
    "(2) Bring a concrete counter-argument, example or evidence from YOUR OWN field/role. "
    "(3) Advance your own distinct position. "
    "Do NOT open with agreement or praise, never write 'I agree with my colleagues'. Repeating what others said is forbidden. "
    "Concede a point only if you are truly convinced, and then say exactly which argument convinced you. "
    "If you are the first speaker, take a clear, bold position others can attack.")

COMPACT_RULES = (
    "Reply with ONLY a compact JSON object (no markdown fence, no preface), keys exactly: "
    '{"claim":"your core position in one short sentence",'
    '"target":"name of the speaker you challenge, or null if opening",'
    '"objection":"the specific weakness or error you attack, one sentence",'
    '"evidence":"one concrete example, datum or reason from your field",'
    '"confidence":0.0-1.0}. '
    "String values must be in the topic language (Persian if the topic is Persian). Max 40 words per string field."
)

def build_prompt(p, topic, compact=False, ask=None):
    name = p["name"]
    lines = transcript_lines()
    others = ", ".join(f"{q['name']}" + (f" ({q.get('role_title')})" if q.get("role_title") else "") for q in STATE["participants"] if q["name"] != name)
    persona = f" Your role: {p['role_title']}. Persona: {p['persona']} Stay strictly in this role." if p.get("persona") else ""
    extra = " " + COMPACT_RULES if compact else " Be concise (max ~150 words). Do not prefix your reply with your name."
    system = (f"You are {name}, one participant in a round-table debate between several AI models "
              f"({others}) moderated by a human named Salar. Topic: \"{topic}\".{persona} "
              + DEBATE_RULES + extra +
              " Reply in the same language as the topic / the moderator (Persian if they write Persian). "
              "If Salar interjects, prioritise responding to him.")
    focus = f"\n\nThe manager assigned you this sub-question: {ask}" if ask else ""
    user = ("Discussion so far:\n\n" + ("\n\n".join(lines) if lines else "(nobody has spoken yet - you open the discussion)")
            + focus + f"\n\nNow it's your turn, {name}.")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def extract_json(txt):
    if not txt: return None
    t = txt.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I|re.S).strip()
    try: return json.loads(t)
    except Exception: pass
    m = re.search(r"\{.*\}", t, flags=re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception:
        return None

def parse_compact(txt):
    obj = extract_json(txt)
    if not isinstance(obj, dict): return None
    claim = str(obj.get("claim") or "").strip()
    if not claim: return None
    conf = obj.get("confidence")
    try: conf = float(conf) if conf is not None and conf != "" else None
    except Exception: conf = None
    if conf is not None: conf = max(0.0, min(1.0, conf))
    target = obj.get("target")
    if target in ("", "null", "None"): target = None
    elif target is not None: target = str(target).strip() or None
    return {
        "claim": claim[:500],
        "target": (target or "")[:120] or None,
        "objection": str(obj.get("objection") or "").strip()[:500] or None,
        "evidence": str(obj.get("evidence") or "").strip()[:500] or None,
        "confidence": conf,
    }

def timeout_for(provider, model, default=60):
    cfg = load_cfg()["providers"].get(provider) or {}
    t = default
    if model in SLOW_MODELS: t = min(t, SLOW_MODELS[model])
    # do not let a higher provider default override a tighter debate timeout
    return max(15, int(t))

def select_usable(requested_names=None):
    """Enabled + key present + test OK (auto-tests if no fresh OK). Returns (usable, skipped[(name, reason)])."""
    cfg, env, s = load_cfg(), load_env(), load_settings()
    usable, skipped, cand = [], [], []
    for p in s["participants"]:
        if requested_names is not None and p["name"] not in requested_names: continue
        pc = cfg["providers"].get(p["provider"])
        if not p.get("enabled"): continue
        if not pc: skipped.append((p["name"], "unknown provider")); continue
        if not has_key(pc, env): skipped.append((p["name"], "no_key")); continue
        cand.append(p)
    def fresh(p):
        t = s["tests"].get(f"{p['provider']}|{p['model']}")
        return t and t["status"] == "ok" and time.time() - t.get("time", 0) < TEST_FRESH_SECONDS
    results = test_many([(p["provider"], p["model"]) for p in cand if not fresh(p)])
    for p in cand:
        t = results.get((p["provider"], p["model"])) or s["tests"].get(f"{p['provider']}|{p['model']}")
        if t["status"] == "ok":
            usable.append({"name": p["name"], "provider": p["provider"], "model": p["model"], "role": p.get("role", ""), "persona": p.get("persona", "")})
        else: skipped.append((p["name"], t["status"]))
    return usable, skipped

def pick_staff_with_key(name="", exclude=(), fallback=True):
    """Pick an enabled participant that currently has an API key. Does not run test_many."""
    s, cfg, env = load_settings(), load_cfg(), load_env()
    exclude = set(exclude or ())
    parts = [p for p in s["participants"] if p.get("enabled") and p["name"] not in exclude]
    def with_key(p):
        pc = cfg["providers"].get(p.get("provider"))
        return bool(pc) and has_key(pc, env)
    if name:
        found = next((p for p in parts if p["name"] == name and with_key(p)), None)
        if found:
            return dict(found)
        if not fallback:
            return None
    cand = [p for p in parts if with_key(p)]
    cand.sort(key=lambda p: STRENGTH.index(p["name"]) if p["name"] in STRENGTH else 99)
    return dict(cand[0]) if cand else None

def bootstrap_office_chat(topic_hint=""):
    """Make a boss available for chat without starting a full multi-round debate."""
    with LOCK:
        boss = STATE.get("manager")
        if boss:
            timeout = int((STATE.get("mode") or {}).get("timeout") or load_settings()["config"].get("timeout") or 60)
            if not STATE.get("topic"):
                STATE["topic"] = topic_hint or "گفتگوی آزاد با مدیر"
            mode = dict(STATE.get("mode") or {})
            mode.setdefault("office", True)
            mode.setdefault("timeout", timeout)
            STATE["mode"] = mode
            return boss, STATE.get("secretary"), timeout
    conf = load_settings()["config"]
    timeout = max(15, min(180, int(conf.get("timeout") or 60)))
    boss = pick_staff_with_key(conf.get("manager") or "")
    if not boss:
        raise RuntimeError("مدیری با کلید سالم پیدا نشد. در مدیریت یک مدل دارای کلید را به‌عنوان مدیر انتخاب کن.")
    secretary = pick_staff_with_key(conf.get("secretary") or "", exclude={boss["name"]}, fallback=True)
    boss["office_seat"] = "boss"
    boss["role"] = "boss"
    boss["role_title"] = "مدیر"
    if secretary:
        secretary["office_seat"] = "secretary"
        secretary["role"] = "secretary"
        secretary["role_title"] = "منشی"
    desks = []
    try:
        desks = snapshot_desks()
    except Exception:
        desks = []
    with LOCK:
        STATE["manager"] = boss
        STATE["secretary"] = secretary
        STATE["mode"] = {"office": True, "manager": True, "compact": True, "timeout": timeout,
                         "manager_name": boss["name"], "secretary_name": (secretary or {}).get("name") or "",
                         "chat": True}
        STATE["office"] = {"boss": boss, "secretary": secretary}
        if desks:
            STATE["desks"] = desks
        if not STATE.get("topic"):
            STATE["topic"] = topic_hint or "گفتگوی آزاد با مدیر"
        if STATE.get("status") in (None, "", "idle", "finished", "stopped"):
            STATE["status"] = "chat"
    app_log(f"bootstrap chat boss={boss['name']} secretary={(secretary or {}).get('name') or '-'}")
    return boss, secretary, timeout



def staff_transcript(include_internal=True, include_user=True):
    with LOCK: msgs = list(STATE["messages"])
    out = []
    for m in msgs:
        if m["kind"] == "judge": continue
        if m["kind"] == "system" and not include_internal: continue
        if m["kind"] == "internal":
            if not include_internal: continue
            who = m["speaker"] + (f" — {m['role_title']}" if m.get("role_title") else "")
            body = format_compact(m["compact"]) if m.get("compact") else m["text"]
            dest = m.get("to") or "boss"
            out.append(f"[CODE {who} -> {dest}]: {body}")
            continue
        if m["kind"] == "user" and include_user:
            out.append(f"[Salar (human)] : {m['text']}")
        elif m["kind"] in ("boss", "secretary", "mention", "ai"):
            who = m["speaker"] + (f" — {m['role_title']}" if m.get("role_title") else "")
            tag = {"boss": "BOSS TO USER", "secretary": "SECRETARY REPORT", "mention": "DIRECT TO USER", "ai": "SAID"}[m["kind"]]
            out.append(f"[{tag} {who}]: {m['text']}")
    return out


class ToolDenied(Exception):
    def __init__(self, msg, pending=None):
        super().__init__(msg); self.pending = pending

def load_permissions():
    s = load_settings()
    return (s.get("config") or {}).get("permissions") or {"roles": dict(DEFAULT_ROLE_PERMS), "always_approve": sorted(ALWAYS_APPROVE)}

def actor_role_key(p):
    if not p: return ""
    if p.get("office_seat") == "boss" or p.get("role") == "boss" or p.get("role_title") == "مدیر":
        return "boss"
    if p.get("office_seat") == "secretary" or p.get("role") == "secretary" or p.get("role_title") == "منشی":
        return "secretary"
    return p.get("role") or ""

def role_allowlist(role_key):
    perms = load_permissions()
    roles = perms.get("roles") or {}
    allowed = list(roles.get(role_key) or DEFAULT_ROLE_PERMS.get(role_key) or [])
    return [t for t in allowed if t in TOOL_DEFS and t not in ALWAYS_APPROVE]

def allowed_tools(p):
    cap = role_allowlist(actor_role_key(p))
    scope = p.get("task_perms")
    if scope is None:
        return cap
    wanted = [t for t in scope if isinstance(t, str)]
    return [t for t in wanted if t in cap]

def can_use_tool(p, tool):
    tool = (tool or "").strip()
    if tool in ALWAYS_APPROVE:
        return False
    return tool in allowed_tools(p)

def sandbox_path(rel):
    os.makedirs(SANDBOX, exist_ok=True)
    rel = str(rel or "").replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("..") or "/../" in "/"+rel+"/" or rel.startswith("~"):
        raise ToolDenied("path outside sandbox")
    root = os.path.realpath(SANDBOX)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        raise ToolDenied("path outside sandbox")
    return full

def queue_approval(actor, tool, args):
    rec = {"id": uuid.uuid4().hex[:12], "tool": tool, "actor": actor.get("name") if actor else "?",
           "role": actor_role_key(actor), "args": {k: (str(v)[:300] if not isinstance(v, (int, float, bool)) else v)
           for k, v in (args or {}).items() if k.lower() not in ("key","token","secret","password")},
           "status": "pending", "t": time.strftime("%H:%M:%S")}
    with LOCK:
        STATE.setdefault("approvals", []).append(rec)
    return rec

def tool_web_read(args):
    url = str(args.get("url") or args.get("href") or "").strip()
    if not re.match(r"^https://", url, re.I):
        raise ToolDenied("web_read only allows https:// public URLs")
    host = re.sub(r"^https://","",url,flags=re.I).split("/")[0].split("@")[-1].split(":")[0].lower()
    if host in ("localhost","127.0.0.1","::1") or host.endswith(".local") or re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)", host):
        raise ToolDenied("web_read cannot target local/private hosts")
    req = urllib.request.Request(url, headers={"User-Agent": "ai-roundtable/4.0 (+local office)", "Accept": "text/html,text/plain,application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = r.read(60000)
        ctype = (r.headers.get("Content-Type") or "").split(";")[0]
    text = raw.decode("utf-8", errors="replace")
    if "html" in ctype:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = htmlmod.unescape(re.sub(r"\s+", " ", text)).strip()
    return {"ok": True, "url": url, "text": text[:8000]}

def tool_file_read(args):
    path = sandbox_path(args.get("path") or args.get("file") or "")
    if not os.path.isfile(path):
        raise ToolDenied("file not found in sandbox")
    data = open(path, "r", encoding="utf-8", errors="replace").read(80000)
    return {"ok": True, "path": os.path.relpath(path, SANDBOX), "text": data[:8000]}

def tool_file_write(args):
    path = sandbox_path(args.get("path") or args.get("file") or "")
    os.makedirs(os.path.dirname(path) or SANDBOX, exist_ok=True)
    body = str(args.get("content") or args.get("text") or "")
    if len(body) > 200000:
        raise ToolDenied("file too large")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return {"ok": True, "path": os.path.relpath(path, SANDBOX), "bytes": len(body.encode())}

def tool_code_run(args):
    os.makedirs(SANDBOX, exist_ok=True)
    code = str(args.get("code") or "")
    rel = args.get("path") or args.get("file")
    if rel:
        path = sandbox_path(rel)
        if not os.path.isfile(path):
            raise ToolDenied("script not found in sandbox")
    else:
        if not code.strip():
            raise ToolDenied("no code")
        path = sandbox_path("_job.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code[:40000])
    env = {"PATH": "/usr/bin:/bin", "HOME": SANDBOX, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    try:
        r = subprocess.run(["python3", "-I", path], cwd=SANDBOX, env=env, capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "sandbox timeout (8s)"}
    out = (r.stdout or "")[-4000:]
    err = (r.stderr or "")[-2000:]
    return {"ok": r.returncode == 0, "exit": r.returncode, "stdout": out, "stderr": err}

def tool_report_write(args):
    os.makedirs(os.path.join(SANDBOX, "reports"), exist_ok=True)
    name = re.sub(r"[^\w.\-]+", "_", str(args.get("name") or time.strftime("report-%H%M%S")))[:80] or "report"
    path = sandbox_path("reports/" + name + ("" if name.endswith(".md") else ".md"))
    body = str(args.get("content") or args.get("text") or "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body[:100000])
    return {"ok": True, "path": os.path.relpath(path, SANDBOX)}

def execute_tool(actor, tool, args):
    """Single enforcement point. Wallet/payments never run; they become a user-approval request."""
    tool = (tool or "").strip()
    args = args if isinstance(args, dict) else {}
    if tool not in TOOL_DEFS:
        raise ToolDenied(f"unknown tool: {tool}")
    if tool in ALWAYS_APPROVE:
        rec = queue_approval(actor, tool, args)
        raise ToolDenied("wallet/payments always need the user's approval — request queued, not executed", pending=rec)
    # Per-role allowlist always applies (even in full autonomy).
    if tool in ("assign_tasks", "speak_to_user"):
        # these are structural rights, not executable tools
        if not can_use_tool(actor, tool):
            raise ToolDenied(f"{actor.get('name')} has no permission for {tool}")
        return {"ok": True, "note": "structural permission, no side effect"}
    if not can_use_tool(actor, tool):
        raise ToolDenied(f"{actor.get('name')} ({actor_role_key(actor)}) is not allowed to use {tool}. Job cap: {role_allowlist(actor_role_key(actor))}; this task scope: {allowed_tools(actor)}")
    # Ask mode (default): side-effect tools wait for the user's approval. Autonomy runs allowlisted tools.
    # Wallet/payments already returned above and never execute.
    if access_mode() == "ask" and tool in ASK_QUEUE_TOOLS:
        rec = queue_approval(actor, tool, args)
        raise ToolDenied("access mode is Ask — tool queued for the user's approval, not executed", pending=rec)
    if tool == "web_read":
        return tool_web_read(args)
    if tool == "file_read":
        return tool_file_read(args)
    if tool == "file_write":
        return tool_file_write(args)
    if tool == "code_run":
        return tool_code_run(args)
    if tool == "report_write":
        return tool_report_write(args)
    raise ToolDenied(f"no handler for {tool}")

def extract_tool_calls(txt_or_obj):
    obj = txt_or_obj if isinstance(txt_or_obj, dict) else (extract_json(txt_or_obj) or {})
    raw = obj.get("tools") if isinstance(obj, dict) else None
    if raw is None and isinstance(obj, dict):
        raw = obj.get("tool")
    if isinstance(raw, dict):
        raw = [raw]
    out = []
    for t in raw or []:
        if not isinstance(t, dict): continue
        name = str(t.get("name") or t.get("tool") or "").strip()
        if not name: continue
        args = t.get("args") if isinstance(t.get("args"), dict) else {k: v for k, v in t.items() if k not in ("name", "tool", "args")}
        out.append({"name": name, "args": args})
    return out

def run_tools_for(actor, txt_or_obj, limit=2):
    results = []
    for call in extract_tool_calls(txt_or_obj)[:limit]:
        try:
            res = execute_tool(actor, call["name"], call["args"])
            results.append({"tool": call["name"], "ok": True, "result": res})
            add_msg("system", f"🔧 {actor.get('name')} used {call['name']}: ok", "system")
        except ToolDenied as e:
            pending = getattr(e, "pending", None)
            results.append({"tool": call["name"], "ok": False, "error": str(e), "pending": pending["id"] if pending else None})
            add_msg("system", f"⛔ {actor.get('name')} / {call['name']}: {e}", "system")
        except Exception as e:
            results.append({"tool": call["name"], "ok": False, "error": str(e)[:300]})
            add_msg("system", f"⛔ {actor.get('name')} / {call['name']}: {e}", "system")
    return results


def parse_boss_plan(txt, employees):
    obj = extract_json(txt) or {}
    names = {p["name"] for p in employees}
    assign, tasks = [], {}
    for item in (obj.get("assign") or obj.get("speak") or []):
        if not isinstance(item, dict): continue
        n = str(item.get("name") or "").strip()
        task = str(item.get("task") or item.get("ask") or "").strip()[:400]
        if n in names and n not in tasks:
            assign.append(n); tasks[n] = task
            rawp = item.get("perms") or item.get("permissions") or item.get("scope")
            if isinstance(rawp, list):
                tasks.setdefault("_perms", {})[n] = [str(x).strip() for x in rawp if str(x).strip()]
    say = str(obj.get("say") or "").strip()
    if not say and not assign:
        # model ignored JSON and wrote prose — treat as user-facing speech
        say = (txt or "").strip()
    return {"say": say, "assign": assign, "tasks": {k:v for k,v in tasks.items() if k != "_perms"},
            "task_perms": tasks.get("_perms") or {},
            "done": bool(obj.get("done") or obj.get("consensus")),
            "reason": str(obj.get("reason") or "").strip()[:300]}

def resolve_mention(text, people):
    if not text or not people: return None
    cands = []
    for p in people:
        for key in (p.get("name"), p.get("role_title"), p.get("role")):
            if key: cands.append((len(str(key)), str(key), p))
    cands.sort(reverse=True)
    for _, key, p in cands:
        if re.search(r"@" + re.escape(key), text, flags=re.I):
            return p
    return None

def call_model(p, messages, max_tokens, timeout, status, thinking_extra=None):
    with LOCK:
        STATE["status"] = status
        th = {"name": p["name"], "provider": p["provider"], "model": p["model"]}
        if thinking_extra: th.update(thinking_extra)
        STATE["thinking"] = th
    tmo = timeout_for(p["provider"], p["model"], timeout)
    t0 = time.time()
    usage = None
    ok, err = True, ""
    try:
        txt, usage = chat(p["provider"], p["model"], messages, max_tokens=max_tokens, timeout=tmo)
        return (txt or "").strip(), usage, tmo
    except ProviderError as e:
        ok, err = False, e.status
        raise
    except Exception as e:
        ok, err = False, type(e).__name__
        raise
    finally:
        try:
            record_call(p, usage, time.time() - t0, ok=ok, err=err)
        except Exception:
            pass
        with LOCK: STATE["thinking"] = None

BOSS_PROMPT = (
    "You are {name}, the BOSS of an AI office and the ONLY person who talks to the user in natural language. "
    "Employees never address the user; they send you compact coded reports. A secretary sitting beside you will later write the official work report (گزارش کار). "
    "Topic: \"{topic}\"\nStaff roster (name — role): {roster}\nRound {round} of {rounds}.\n"
    "Reply with ONLY a JSON object (no markdown): "
    '{{"say":"natural-language message to the user, in the topic language (Persian if Persian)","assign":[{{"name":"...","task":"specific short task"}}],"done":false}}\n'
    "Rules: 'say' is what the user will read — be a clear, warm, professional manager; never put JSON or code in 'say'. "
    "Assign 1 to 5 employees from the roster with a specific short task (same language as the topic). "
    "After you have enough reports, set done=true and assign=[], and put your conclusion in 'say'. "
    "You may ask the user a clarifying question in 'say' and set done=true if you need input. Only use roster names."
)

EMPLOYEE_OFFICE_PROMPT = (
    "You are {name}{persona} You are an employee in an AI office. You NEVER speak to the user and NEVER write prose for them. "
    "You only send a compact coded report to the boss. "
    + COMPACT_RULES.replace('{','{{').replace('}','}}') +
    " You may also include \"tools\":[{{\"name\":\"web_read\",\"url\":\"https://...\"}}] (or code_run/file_read/file_write/report_write) — only tools in your current permission scope will run. "
    "Wallet and payments always require the user's approval and will not run automatically. "
    " Topic: \"{topic}\". Your allowed tools this turn: {tools}."
)

SECRETARY_PROMPT = (
    "You are {name}, the SECRETARY sitting beside the boss of an AI office. You do not debate. "
    "After the staff finish their work, write a clear work report (گزارش کار) for the user, in the language of the topic (Persian if Persian), using these headings:\n"
    "۱. موضوع\n۲. کارهای انجام‌شده — who was assigned what, very briefly\n۳. یافته‌ها و تصمیم مدیر\n۴. کارهای باز / پیشنهاد بعدی\n"
    "Readable prose, not JSON. Be concise (max ~300 words). Use simple markdown (## headings, - bullets, **bold**)."
)

MENTION_PROMPT = (
    "You are {name}{persona} The user addressed YOU directly by name or role. This is the one exception to the office rule: "
    "answer the user in natural language (Persian if they wrote Persian). Stay in your role, be concise (max ~150 words), no JSON. "
    "Do not speak for the boss. Topic: \"{topic}\"."
)

def run_employee_turn(p, topic, task, timeout, compact=True):
    persona = f", {p['role_title']}. Persona: {p['persona']} Stay strictly in this role." if p.get("persona") else "."
    system = EMPLOYEE_OFFICE_PROMPT.format(name=p["name"], persona=persona, topic=topic, tools=", ".join(allowed_tools(p)) or "none")
    user = ("Internal office traffic so far:\n\n" + ("\n\n".join(staff_transcript()) or "(no reports yet)")
            + (f"\n\nThe boss assigned you this task: {task}" if task else "")
            + f"\n\nSend your compact JSON report to the boss now, {p['name']}.")
    try:
        txt, usage, tmo = call_model(p, [{"role":"system","content":system},{"role":"user","content":user}],
                                     500 if compact else 2048, timeout,
                                     f"{p['name']} is writing a coded report...")
        txt = re.sub(r"^\[?" + re.escape(p["name"]) + r"\]?:\s*", "", txt)
        compact_obj = parse_compact(txt) if compact else None
        if compact and compact_obj: txt = format_compact(compact_obj)
        add_msg(p["name"], txt or "(empty report)", "internal", p["provider"], p["model"], p.get("role",""), p.get("role_title",""),
                usage=usage, compact=compact_obj)
        with LOCK:
            STATE["messages"][-1]["to"] = "boss"
            STATE["messages"][-1]["from"] = p["name"]
        tool_res = run_tools_for(p, txt)
        if tool_res and not STOP.is_set():
            follow = user + "\n\nTool results (already enforced by the permission layer):\n" + json.dumps(tool_res, ensure_ascii=False)[:2500] + "\n\nSend your final compact JSON report to the boss, without repeating denied tools."
            try:
                txt2, usage2, tmo2 = call_model(p, [{"role":"system","content":system},{"role":"user","content":follow}],
                                                500 if compact else 2048, timeout,
                                                f"{p['name']} is writing a follow-up report...")
                txt2 = re.sub(r"^\[?" + re.escape(p["name"]) + r"\]?:\s*", "", txt2 or "")
                c2 = parse_compact(txt2) if compact else None
                if compact and c2: txt2 = format_compact(c2)
                add_msg(p["name"], txt2 or "(empty follow-up)", "internal", p["provider"], p["model"], p.get("role",""), p.get("role_title",""),
                        usage=usage2, compact=c2)
                with LOCK:
                    STATE["messages"][-1]["to"] = "boss"
                    STATE["messages"][-1]["from"] = p["name"]
                run_tools_for(p, txt2, limit=1)
            except ProviderError:
                pass
        return True
    except ProviderError as e:
        tmo = timeout_for(p["provider"], p["model"], timeout)
        if e.status in ("rate_limited", "timeout", "too_large"):
            why = {"rate_limited": "محدودیت نرخ", "timeout": f"زمان تمام شد ({tmo}s)", "too_large": "درخواست خیلی بزرگ بود"}[e.status]
            add_msg("system", f"⏭ {p['name']} skipped ({why})", "system", p["provider"], p["model"])
        else:
            add_msg("system", f"{p['name']} error ({e.status}): {e.detail[:200]}", "system", p["provider"], p["model"])
        return False
    except Exception as e:
        add_msg("system", f"{p['name']} error: {e}", "system")
        return False

def run_boss_turn(boss, topic, employees, rnd, rounds, timeout):
    roster = ", ".join(p["name"] + (f" ({p.get('role_title')})" if p.get("role_title") else "") for p in employees) or "(no employees present)"
    system = BOSS_PROMPT.format(name=boss["name"], topic=topic, roster=roster, round=rnd, rounds=rounds)
    user = "Office traffic so far:\n\n" + ("\n\n".join(staff_transcript()) or "(the user just sent the topic; nobody has worked yet)") + "\n\nReturn the JSON plan (with 'say' for the user) now."
    try:
        txt, usage, tmo = call_model(boss, [{"role":"system","content":system},{"role":"user","content":user}],
                                     900, timeout, f"boss {boss['name']} is deciding...", {"boss": True})
        plan = parse_boss_plan(txt, employees)
        # keep the machine plan as an internal packet (boss -> staff)
        compact_plan = {"claim": plan.get("reason") or "plan", "target": ", ".join(plan.get("assign") or []) or None,
                        "objection": None, "evidence": "; ".join(f"{n}: {plan['tasks'].get(n,'')}" for n in plan.get("assign") or []) or None,
                        "confidence": 1.0 if plan.get("done") else 0.7}
        add_msg(boss["name"], format_compact(compact_plan) if plan.get("assign") or plan.get("done") else (txt[:400]),
                "internal", boss["provider"], boss["model"], "boss", "مدیر", usage=usage, compact=compact_plan)
        with LOCK:
            STATE["messages"][-1]["to"] = "staff"
            STATE["messages"][-1]["from"] = boss["name"]
        if plan.get("say"):
            add_msg(boss["name"], plan["say"], "boss", boss["provider"], boss["model"], "boss", "مدیر")
        return plan
    except ProviderError as e:
        add_msg("system", f"مدیر {boss['name']} خطا ({e.status}): {e.detail[:200]}", "system")
        return {"say": "", "assign": [p["name"] for p in employees[:4]], "tasks": {}, "done": False, "reason": "boss failed"}

def run_secretary(secretary, topic, timeout):
    with LOCK:
        STATE["thinking"] = {"name": secretary["name"], "provider": secretary["provider"], "model": secretary["model"], "secretary": True}
        STATE["status"] = f"secretary {secretary['name']} is writing the work report..."
    lines = staff_transcript()
    msgs = [{"role": "system", "content": SECRETARY_PROMPT.format(name=secretary["name"])},
            {"role": "user", "content": "Office record:\n\n" + "\n\n".join(lines) + "\n\nWrite the گزارش کار now."}]
    try:
        txt, usage = chat(secretary["provider"], secretary["model"], msgs, max_tokens=2500,
                          timeout=timeout_for(secretary["provider"], secretary["model"], min(120, max(timeout, 90))))
        with LOCK: STATE["thinking"] = None
        add_msg(secretary["name"], txt or "(empty report)", "secretary", secretary["provider"], secretary["model"], "secretary", "منشی", usage=usage)
    except ProviderError as e:
        with LOCK: STATE["thinking"] = None
        add_msg("system", f"منشی {secretary['name']} failed ({e.status}): {e.detail[:200]}", "system")

def run_office(topic, employees, rounds, boss, secretary=None, judge=None, timeout=60):
    try:
        for r in range(rounds):
            if STOP.is_set(): raise StopIteration
            with LOCK: STATE["round"] = r + 1
            try: tick_project(rnd=r+1, rounds=rounds)
            except Exception: pass
            plan = run_boss_turn(boss, topic, employees, r + 1, rounds, timeout)
            if STOP.is_set(): raise StopIteration
            if plan.get("done") and r > 0 and not plan.get("assign"):
                break
            by = {p["name"]: p for p in employees}
            speakers = [by[n] for n in plan.get("assign") or [] if n in by]
            if not speakers and not plan.get("done"):
                speakers = list(employees)
            for p in speakers:
                if STOP.is_set(): raise StopIteration
                p["task_perms"] = (plan.get("task_perms") or {}).get(p["name"]); run_employee_turn(p, topic, (plan.get("tasks") or {}).get(p["name"], ""), timeout, compact=True)
            if plan.get("done"):
                # let the boss give a final word after the last reports
                if speakers:
                    plan2 = run_boss_turn(boss, topic, employees, r + 1, rounds, timeout)
                    if plan2.get("say") is not None:
                        pass
                break
        if secretary and not STOP.is_set():
            run_secretary(secretary, topic, timeout)
        if judge and not STOP.is_set():
            run_judge(judge, topic, timeout=timeout)
        with LOCK: STATE["status"] = "finished"
        finalize_session(topic, "finished")
    except StopIteration:
        with LOCK: STATE["status"] = "stopped"
        finalize_session(topic, "stopped")
    finally:
        with LOCK: STATE["running"] = False; STATE["thinking"] = None

def run_mention_reply(person, topic, timeout):
    name = person.get("name") or "?"
    app_log(f"reply start name={name} provider={person.get('provider')} model={person.get('model')}")
    try:
        persona = f". Your role: {person.get('role_title')}. Persona: {person.get('persona')} Stay strictly in this role." if person.get("persona") else "."
        # Boss in open chat always answers the user in natural language (even without @mention).
        if person.get("office_seat") == "boss" or person.get("role") == "boss":
            system = (
                f"You are {name}, the BOSS of an AI office and the ONLY person who talks to the user in natural language. "
                f"Topic: \"{topic or 'گفتگوی آزاد با مدیر'}\". Answer the user's latest message clearly and helpfully, "
                "in the same language they used (Persian if Persian, informal ok). Be concise (max ~180 words). "
                "Do not emit JSON. If staff work is needed you may say you will assign it, but first answer the user."
            )
            kind, extra, title, role = "boss", {"boss": True}, "مدیر", "boss"
        else:
            system = MENTION_PROMPT.format(name=name, persona=persona, topic=topic or "")
            kind, extra, title, role = "mention", {"mention": True}, person.get("role_title") or "", person.get("role") or ""
        user = "Conversation:\n\n" + "\n\n".join(staff_transcript(include_internal=False)) + f"\n\nAnswer the user directly now, {name}."
        try:
            txt, usage, tmo = call_model(person, [{"role":"system","content":system},{"role":"user","content":user}],
                                         800, timeout, f"{name} is answering you...", extra)
            if not (txt or "").strip():
                add_msg("system", f"{name} پاسخ خالی برگرداند. دوباره بفرست یا مدل دیگری را به‌عنوان مدیر انتخاب کن.", "system")
                app_log(f"reply empty name={name}")
            else:
                add_msg(name, txt, kind, person["provider"], person["model"], role, title, usage=usage)
                app_log(f"reply ok name={name} chars={len(txt)} tokens={(usage or {}).get('total')}")
        except ProviderError as e:
            add_msg("system", f"خطای {name} ({e.status}): {e.detail[:200]}", "system")
            app_log(f"reply ProviderError name={name} status={e.status} detail={e.detail[:200]}")
        except Exception as e:
            add_msg("system", f"خطای {name}: {e}", "system")
            app_log(f"reply error name={name}: {e}")
        with LOCK: STATE["status"] = "chat"
    except Exception as e:
        app_log(f"reply crashed name={name}: {e}")
        add_msg("system", f"پاسخ ارسال نشد: {e}", "system")
        with LOCK: STATE["status"] = "chat"
    finally:
        with LOCK: STATE["running"] = False; STATE["thinking"] = None


JUDGE_PROMPT = ("You are {name}, the impartial JUDGE of a round-table debate. You did not take part. Topic: \"{topic}\". "
    "Read the full transcript and write a structured synthesis in the language of the topic (Persian if Persian), using these headings:\n"
    "۱. مواضع شرکت‌کنندگان — one short line per participant (name + role + core position)\n"
    "۲. نقاط توافق\n۳. نقاط اختلاف اصلی\n۴. قوی‌ترین استدلال‌ها — and who made them; also the weakest argument\n"
    "۵. حکم نهایی — your own reasoned verdict on the question, with confidence level and what evidence would change it.\n"
    "Be fair, specific and concise (max ~400 words). Use simple markdown (## headings, - bullets, **bold**); do not use tables. "
    "Write readable prose, not JSON. If turns are in compact claim|target|obj|ev|conf form, expand them into clear Persian.")

MANAGER_PROMPT = ("You are the debate MANAGER / orchestrator, not a participant and not the judge. "
    "Topic: \"{topic}\"\nParticipants (name — role): {roster}\nRound {round} of {rounds}.\n"
    "Pick who should speak THIS round, assign each a focused sub-question, and decide whether the debate should stop early "
    "because positions have already converged.\n"
    "Reply with ONLY a JSON object (no markdown): "
    '{{"speak":[{{"name":"...","ask":"focused sub-question"}}],"consensus":false,"reason":"one short sentence"}}\n'
    "Rules: Pick 2 to 5 speakers (fewer if few remain). Prefer complementary roles; include a devil's advocate if disagreement remains. "
    "Do not pick the exact same subset every round if others still have something new to add. "
    "\"ask\" must be specific, max 30 words, in the topic language (Persian if the topic is Persian). "
    "Set consensus=true only if remaining disagreement is minor and further turns would add little. "
    "Only use names from the roster.")

def run_manager(manager, topic, participants, rnd, rounds, timeout=60):
    roster = ", ".join(p["name"] + (f" ({p.get('role_title')})" if p.get("role_title") else "") for p in participants)
    lines = transcript_lines()
    msgs = [{"role": "system", "content": MANAGER_PROMPT.format(topic=topic, roster=roster, round=rnd, rounds=rounds)},
            {"role": "user", "content": "Transcript so far:\n\n" + ("\n\n".join(lines) if lines else "(nobody has spoken yet)")
             + "\n\nReturn the JSON plan for this round now."}]
    with LOCK:
        STATE["thinking"] = {"name": manager["name"], "provider": manager["provider"], "model": manager["model"], "manager": True}
        STATE["status"] = f"manager {manager['name']} is planning round {rnd}/{rounds}..."
    try:
        txt, usage = chat(manager["provider"], manager["model"], msgs, max_tokens=600, timeout=timeout_for(manager["provider"], manager["model"], timeout))
        add_usage(usage)
        obj = extract_json(txt) or {}
        names = {p["name"] for p in participants}
        speak, asks = [], {}
        for item in (obj.get("speak") or []):
            if not isinstance(item, dict): continue
            n = str(item.get("name") or "").strip()
            if n in names and n not in asks:
                speak.append(n); asks[n] = str(item.get("ask") or "").strip()[:300]
        plan = {"speak": speak, "asks": asks, "consensus": bool(obj.get("consensus")), "reason": str(obj.get("reason") or "").strip()[:300]}
        return plan
    except ProviderError as e:
        add_msg("system", f"مدیر {manager['name']} خطا ({e.status}): این دور همه صحبت می‌کنند", "system")
        return {"speak": [p["name"] for p in participants], "asks": {}, "consensus": False, "reason": "manager failed"}
    finally:
        with LOCK: STATE["thinking"] = None

def run_judge(judge, topic, timeout=60):
    with LOCK:
        STATE["thinking"] = {"name": judge["name"], "provider": judge["provider"], "model": judge["model"], "judge": True}
        STATE["status"] = f"judge {judge['name']} is writing the verdict..."
    lines = transcript_lines(for_judge=True)
    def attempt(body):
        msgs = [{"role": "system", "content": JUDGE_PROMPT.format(name=judge["name"], topic=topic)},
                {"role": "user", "content": "Transcript:\n\n" + body + "\n\nWrite your synthesis and verdict now, in readable Persian prose."}]
        return chat(judge["provider"], judge["model"], msgs, max_tokens=4000, timeout=timeout_for(judge["provider"], judge["model"], min(120, max(timeout, 90))))
    try:
        body = "\n\n".join(lines)
        try:
            txt, usage = attempt(body)
        except ProviderError as e:
            if e.status in ("too_large", "rate_limited") and len(lines) > 6:
                body = "\n\n".join(lines[-10:])
                txt, usage = attempt(body)
            else:
                raise
        with LOCK: STATE["thinking"] = None
        add_msg(judge["name"], txt or "(empty verdict)", "judge", judge["provider"], judge["model"], "judge", "داور", usage=usage)
    except ProviderError as e:
        with LOCK: STATE["thinking"] = None
        add_msg("system", f"Judge {judge['name']} failed ({e.status}): {e.detail[:200]}", "system")

def run_discussion(topic, participants, rounds, judge=None, manager=None, compact=False, timeout=60):
    try:
        spoken = False
        for r in range(rounds):
            if STOP.is_set(): raise StopIteration
            asks, speakers = {}, list(participants)
            if manager:
                plan = run_manager(manager, topic, participants, r + 1, rounds, timeout=timeout)
                if STOP.is_set(): raise StopIteration
                if plan.get("consensus") and spoken:
                    add_msg("system", f"مدیر ({manager['name']}): اجماع — پایان زودهنگام. {plan.get('reason') or ''}".strip(), "system")
                    break
                if plan.get("speak"):
                    by = {p["name"]: p for p in participants}
                    speakers = [by[n] for n in plan["speak"] if n in by] or list(participants)
                    asks = plan.get("asks") or {}
                    add_msg("system", "مدیر این دور را برنامه‌ریزی کرد: " + ", ".join(
                        p["name"] + (f" («{asks[p['name']]}»)" if asks.get(p["name"]) else "") for p in speakers)
                        + (f" — {plan.get('reason')}" if plan.get("reason") else ""), "system")
            for p in speakers:
                if STOP.is_set(): raise StopIteration
                with LOCK:
                    STATE["status"] = f"round {r+1}/{rounds}: {p['name']} is thinking..."
                    STATE["round"] = r + 1
                    STATE["thinking"] = {"name": p["name"], "provider": p["provider"], "model": p["model"]}
                tmo = timeout_for(p["provider"], p["model"], timeout)
                try:
                    txt, usage = chat(p["provider"], p["model"], build_prompt(p, topic, compact=compact, ask=asks.get(p["name"])),
                                      max_tokens=500 if compact else 2048, timeout=tmo)
                    if STOP.is_set(): raise StopIteration
                    txt = re.sub(r"^\[?" + re.escape(p["name"]) + r"\]?:\s*", "", txt or "")
                    compact_obj = parse_compact(txt) if compact else None
                    if compact and compact_obj:
                        txt = format_compact(compact_obj)
                    with LOCK: STATE["thinking"] = None
                    add_msg(p["name"], txt or "(empty reply)", "ai", p["provider"], p["model"], p.get("role", ""), p.get("role_title", ""),
                            usage=usage, compact=compact_obj)
                    spoken = True
                except StopIteration: raise
                except ProviderError as e:
                    with LOCK: STATE["thinking"] = None
                    if e.status in ("rate_limited", "timeout", "too_large"):
                        why = {"rate_limited": "محدودیت نرخ", "timeout": f"زمان تمام شد ({tmo}s)", "too_large": "درخواست خیلی بزرگ بود"}[e.status]
                        add_msg("system", f"⏭ {p['name']} skipped this turn ({why})", "system", p["provider"], p["model"])
                    else:
                        add_msg("system", f"{p['name']} error ({e.status}): {e.detail[:200]}", "system", p["provider"], p["model"])
                except Exception as e:
                    with LOCK: STATE["thinking"] = None
                    add_msg("system", f"{p['name']} error: {e}", "system")
        if judge and not STOP.is_set(): run_judge(judge, topic, timeout=timeout)
        with LOCK: STATE["status"] = "finished"
        finalize_session(topic, "finished")
    except StopIteration:
        with LOCK: STATE["status"] = "stopped"
        finalize_session(topic, "stopped")
    finally:
        with LOCK: STATE["running"] = False; STATE["thinking"] = None

# ---------- HTTP ----------
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
NAME_RE = re.compile(r"^[\w .\-()]{1,40}$", re.U)
MODEL_RE = re.compile(r"^[\w.\-/:@]{1,120}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_\-.:+/=]{8,400}$")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj, ctype="application/json"):
        b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")
    def host_ok(self):  # blocks DNS-rebinding
        return self.headers.get("Host") in ALLOWED_HOSTS
    def admin_view(self):
        cfg, env, s = load_cfg(), load_env(), load_settings()
        provs = []
        for k, v in cfg["providers"].items():
            t = s["tests"].get(f"{k}|{v['default_model']}")
            provs.append({"id": k, "label": v["label"], "env": v.get("env", ""), "extra_env": v.get("extra_env") or [],
                          "mock": bool(v.get("mock")), "has_key": has_key(v, env), "default_model": v["default_model"],
                          "test": t, "tier": v.get("tier", ""), "signup": v.get("signup", "")})
        parts = []
        for p in s["participants"]:
            pc = cfg["providers"].get(p["provider"], {})
            parts.append(dict(p, has_key=has_key(pc, env) if pc else False, test=s["tests"].get(f"{p['provider']}|{p['model']}"),
                              signup=pc.get("signup", ""), tier=pc.get("tier", "")))
        suggested = [{"id": k, "label": v["label"], "tier": v.get("tier", ""), "signup": v.get("signup", ""),
                      "has_key": has_key(v, env), "env": v.get("env", "")}
                     for k, v in cfg["providers"].items() if v.get("signup") and not v.get("mock")]
        perms = s["config"].get("permissions") or {}
        return {"providers": provs, "participants": parts, "roles": load_roles(), "config": s["config"], "suggested": suggested,
                "tools": TOOL_DEFS, "permissions": perms, "always_approve": sorted(ALWAYS_APPROVE)}
    def do_GET(self):
        if not self.host_ok(): return self.send(403, {"error": "bad host"})
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(BASE, "index.html"), "rb").read(), "text/html")
        if path in ("/office", "/office.html"):
            return self.send(200, open(os.path.join(BASE, "office.html"), "rb").read(), "text/html")
        if path.startswith("/static/"):
            fn = path[len("/static/"):]
            types = {"woff2": "font/woff2", "svg": "image/svg+xml", "png": "image/png", "css": "text/css", "js": "text/javascript", "json": "application/json"}
            ext = fn.rsplit(".", 1)[-1]
            fp = os.path.join(BASE, "static", fn)
            if not re.match(r"^[\w.\-]+(?:/[\w.\-]+)*$", fn) or ".." in fn or ext not in types or not os.path.isfile(fp): return self.send(404, {"error": "not found"})
            self.send_response(200); b = open(fp, "rb").read()
            self.send_header("Content-Type", types[ext]); self.send_header("Content-Length", str(len(b)))
            if ext in ("js", "css", "html"):
                self.send_header("Cache-Control", "no-store")
            else:
                self.send_header("Cache-Control", "max-age=86400")
            self.end_headers(); return self.wfile.write(b)
        if path == "/api/state":
            with LOCK:
                out = dict(STATE)
            if not out.get("desks"):
                try: out["desks"] = snapshot_desks()
                except Exception: out["desks"] = []
            return self.send(200, out)
        if path == "/api/scorecard":
            try:
                stored = _load_json(SCORECARD_PATH, {})
            except Exception:
                stored = {}
            live = live_scorecard()
            if stored.get("employees"):
                for k,v in (stored.get("employees") or {}).items():
                    live.setdefault("employees", {}).setdefault(k, {}).update(v)
            live["writeups"] = stored.get("writeups") or []
            live["updated"] = stored.get("updated") or live.get("updated")
            return self.send(200, live)
        if path == "/api/project":
            proj = enrich_project(_load_json(PROJECT_PATH, {"goal":"","started_at":"","progress":0,"eta":""}))
            with LOCK:
                if STATE.get("topic") and not proj.get("goal"): proj["goal"]=STATE["topic"]
            return self.send(200, proj)
        if path == "/api/proposals":
            return self.send(200, _load_json(PROPOSALS_PATH, {"proposals": []}))
        if path in ("/api/admin", "/api/providers"):
            return self.send(200, self.admin_view())
        if path == "/api/permissions":
            return self.send(200, {"tools": TOOL_DEFS, "permissions": load_permissions(), "always_approve": sorted(ALWAYS_APPROVE)})
        if path == "/api/approvals":
            with LOCK: return self.send(200, {"approvals": list(STATE.get("approvals") or [])})
        if path == "/api/models":
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            prov = q.get("provider", [""])[0]
            try: return self.send(200, {"models": list_models(prov, q.get("free", ["0"])[0] == "1")})
            except ProviderError as e: return self.send(200, {"models": [], "error": e.status})
            except Exception as e: return self.send(200, {"models": [], "error": "error"})
        self.send(404, {"error": "not found"})
    def do_POST(self):
        if not self.host_ok():
            app_log(f"POST {self.path} rejected bad host={self.headers.get('Host')!r}")
            return self.send(403, {"error": "bad host"})
        o = self.headers.get("Origin")
        if o is not None and o not in ("http://" + h for h in ALLOWED_HOSTS):
            app_log(f"POST {self.path} rejected bad origin={o!r}")
            return self.send(403, {"error": "bad origin"})
        try: d = self.body()
        except Exception:
            app_log(f"POST {self.path} bad json")
            return self.send(400, {"error": "bad json"})
        if self.path.startswith("/api/"):
            app_log(f"POST {self.path}")
        try:
            return self._do_POST(d)
        except Exception as e:
            app_log(f"POST {self.path} crashed: {type(e).__name__}: {e}")
            return self.send(500, {"error": "server error"})
    def _do_POST(self, d):
        cfg = load_cfg()
        if self.path == "/api/test":
            prov = d.get("provider"); model = d.get("model") or cfg["providers"].get(prov, {}).get("default_model")
            if prov not in cfg["providers"] or not model or not MODEL_RE.match(model): return self.send(400, {"error": "bad provider/model"})
            return self.send(200, test_target(prov, model))
        if self.path == "/api/test-all":
            s = load_settings(); env = load_env()
            pairs = [(p["provider"], p["model"]) for p in s["participants"]
                     if p.get("enabled") and p["provider"] in cfg["providers"] and has_key(cfg["providers"][p["provider"]], env)]
            pairs += [(k, v["default_model"]) for k, v in cfg["providers"].items() if not v.get("mock") and has_key(v, env)]
            r = test_many(pairs)
            return self.send(200, {"ok": True, "tested": len(r), "passed": sum(1 for v in r.values() if v["status"] == "ok")})
        if self.path == "/api/participants":
            new = []
            for p in d.get("participants", []):
                name, prov, model = str(p.get("name", "")).strip(), p.get("provider"), str(p.get("model", "")).strip()
                if not NAME_RE.match(name) or prov not in cfg["providers"] or not MODEL_RE.match(model):
                    return self.send(400, {"error": f"invalid participant: {name or '?'}"})
                if any(x["name"] == name for x in new): return self.send(400, {"error": f"duplicate name: {name}"})
                roles = load_roles()
                role = p.get("role") if p.get("role") in roles and p.get("role") != "judge" else None
                persona = str(p.get("persona") or "").strip()[:4000]
                q = {"name": name, "provider": prov, "model": model, "enabled": bool(p.get("enabled"))}
                if role: q["role"] = role; q["persona"] = persona or roles[role]["desc"]
                new.append(q)
            s = load_settings(); s["participants"] = new; save_settings(s)
            return self.send(200, {"ok": True})
        if self.path == "/api/config":
            s = load_settings(); c = s["config"]
            if "rounds" in d: c["rounds"] = max(1, min(50, int(d["rounds"])))
            if "roles_enabled" in d: c["roles_enabled"] = bool(d["roles_enabled"])
            if "judge_enabled" in d: c["judge_enabled"] = bool(d["judge_enabled"])
            if "manager_enabled" in d: c["manager_enabled"] = bool(d["manager_enabled"])
            if "compact_enabled" in d: c["compact_enabled"] = bool(d["compact_enabled"])
            if "office_enabled" in d: c["office_enabled"] = bool(d["office_enabled"])
            if "access_mode" in d:
                if d["access_mode"] not in ("ask", "autonomy"):
                    return self.send(400, {"error": "access_mode must be ask or autonomy"})
                c["access_mode"] = d["access_mode"]
                c.setdefault("permissions", {})["mode"] = d["access_mode"]
            if "timeout" in d: c["timeout"] = max(15, min(180, int(d["timeout"])))
            names = [p["name"] for p in s["participants"]]
            if "judge" in d:
                if d["judge"] not in names: return self.send(400, {"error": "unknown judge"})
                c["judge"] = d["judge"]
            if "manager" in d:
                if d["manager"] not in names: return self.send(400, {"error": "unknown manager"})
                c["manager"] = d["manager"]
            if "secretary" in d:
                if d["secretary"] not in names: return self.send(400, {"error": "unknown secretary"})
                c["secretary"] = d["secretary"]
            save_settings(s); return self.send(200, {"ok": True, "config": c})
        if self.path == "/api/permissions":
            s = load_settings(); c = s["config"]
            perms = c.setdefault("permissions", {"roles": {}})
            roles_p = perms.setdefault("roles", {})
            incoming = d.get("roles") if isinstance(d.get("roles"), dict) else {}
            known = set(TOOL_DEFS) | set(DEFAULT_ROLE_PERMS)
            for role, tools in incoming.items():
                if role == "judge": 
                    roles_p[role] = []
                    continue
                if role not in DEFAULT_ROLE_PERMS and role not in roles_p and role not in ("boss","secretary"):
                    continue
                clean = []
                for t in tools if isinstance(tools, list) else []:
                    t = str(t).strip()
                    if t in ALWAYS_APPROVE:
                        continue  # never a standing grant
                    if t in TOOL_DEFS:
                        clean.append(t)
                roles_p[role] = clean
            perms["always_approve"] = sorted(ALWAYS_APPROVE)
            save_settings(s)
            return self.send(200, {"ok": True, "permissions": perms, "always_approve": sorted(ALWAYS_APPROVE)})
        if self.path in ("/api/proposals", "/api/proposals/apply"):
            pid = str(d.get("id") or "").strip()
            if d.get("dismiss") or d.get("reject"):
                props = _load_json(PROPOSALS_PATH, {"proposals": []})
                rec = next((p for p in (props.get("proposals") or []) if p.get("id")==pid), None)
                if not rec: return self.send(404, {"error": "unknown proposal"})
                rec["status"] = "dismissed"
                rec["applied_at"] = iso_berlin()
                _save_json(PROPOSALS_PATH, props)
                return self.send(200, {"ok": True, "proposal": rec})
            try:
                rec = apply_proposal(pid)
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            return self.send(200, {"ok": True, "proposal": rec, "config": load_settings()["config"]})
        if self.path == "/api/approvals":
            aid = str(d.get("id") or "").strip()
            approve = bool(d.get("approve"))
            with LOCK:
                rec = next((a for a in (STATE.get("approvals") or []) if a.get("id")==aid), None)
                if not rec: return self.send(404, {"error": "unknown approval"})
                if rec.get("status") != "pending": return self.send(409, {"error": "already decided"})
                rec["status"] = "approved" if approve else "denied"
                rec["decided_at"] = time.strftime("%H:%M:%S")
            # never execute a payment even when approved — only record the user's decision
            add_msg("system", ("کاربر پرداخت/کیف‌پول را تأیید کرد (اجرای خودکار نشد): " if approve else "کاربر پرداخت/کیف‌پول را رد کرد: ") + aid, "system")
            return self.send(200, {"ok": True, "approval": rec, "executed": False})
        if self.path == "/api/key":
            prov = d.get("provider"); val = str(d.get("value", "")).strip()
            pc = cfg["providers"].get(prov)
            if not pc or pc.get("mock") or not re.match(r"^[A-Z0-9_]+$", pc.get("env", "")): return self.send(400, {"error": "bad provider"})
            if val and not KEY_RE.match(val): return self.send(400, {"error": "key format looks invalid (no spaces/newlines)"})
            write_env_key(pc["env"], val)
            return self.send(200, {"ok": True, "has_key": bool(val)})  # value never echoed
        if self.path == "/api/start":
            with LOCK:
                if STATE["running"]: return self.send(409, {"error": "already running"})
            topic = str(d.get("topic", "")).strip()
            if not topic: return self.send(400, {"error": "موضوع را بنویسید / topic required"})
            req = d.get("participants")
            s = load_settings(); conf = s["config"]; roles = load_roles()
            use_office = bool(d.get("office_enabled", conf.get("office_enabled", True)))
            use_judge = bool(d.get("judge_enabled", False if use_office else conf["judge_enabled"]))
            use_roles = bool(d.get("roles_enabled", conf["roles_enabled"]))
            use_manager = True if use_office else bool(d.get("manager_enabled", conf.get("manager_enabled", True)))
            use_compact = True if use_office else bool(d.get("compact_enabled", conf.get("compact_enabled", True)))
            judge_name = d.get("judge") or conf.get("judge")
            manager_name = d.get("manager") or conf.get("manager")
            secretary_name = d.get("secretary") or conf.get("secretary")
            timeout = max(15, min(180, int(d.get("timeout") or conf.get("timeout") or 60)))
            want = set(req) if isinstance(req, list) else None
            if want is not None:
                if use_judge and judge_name: want.add(judge_name)
                if use_manager and manager_name: want.add(manager_name)
                if use_office and secretary_name: want.add(secretary_name)
            usable, skipped = select_usable(want)
            def take(name, exclude=(), fallback=True):
                found = next((p for p in usable if p["name"] == name and p["name"] not in exclude), None)
                if found or not fallback: return found
                cand = [p for p in usable if p["name"] not in exclude]
                cand = sorted(cand, key=lambda p: STRENGTH.index(p["name"]) if p["name"] in STRENGTH else 99)
                need = 2 if not fallback else 1
                return cand[0] if len(cand) >= need else (cand[0] if cand and fallback else None)
            judge = take(judge_name) if use_judge else None
            manager = take(manager_name, exclude={judge["name"]} if judge else ()) if use_manager else None
            secretary = None
            if use_office:
                exc = {x["name"] for x in (manager, judge) if x}
                secretary = take(secretary_name, exclude=exc, fallback=True)
                if secretary and manager and secretary["name"] == manager["name"]:
                    secretary = take("", exclude=exc | {manager["name"]}, fallback=True)
            reserved = set()
            if judge: reserved.add(judge["name"])
            if manager: reserved.add(manager["name"])
            if secretary: reserved.add(secretary["name"])
            staff = [p for p in usable if p["name"] not in reserved]
            for p in staff + [x for x in (manager, secretary, judge) if x]:
                if use_roles and p.get("role") in roles:
                    p["role_title"] = roles[p["role"]]["title"]
                else:
                    if p is manager or p is secretary or p is judge: pass
                    else:
                        p["role"] = ""; p["persona"] = ""; p["role_title"] = ""
            if manager:
                manager["role_title"] = "مدیر"; manager["office_seat"] = "boss"
            if secretary:
                secretary["role_title"] = "منشی"; secretary["office_seat"] = "secretary"
            if use_roles and not use_office and len(staff) >= 2 and not any(p["role"] == "devil" for p in staff):
                dv = staff[1]; dv["role"] = "devil"; dv["role_title"] = roles["devil"]["title"]; dv["persona"] = roles["devil"]["desc"]
            skip_txt = ", ".join(f"{n} ({r})" for n, r in skipped)
            min_need = 1 if (use_office and manager) else 2
            if len(staff) < min_need and not (use_office and manager and secretary):
                return self.send(400, {"error": "حداقل ۲ مدل فعال و سالم لازم است. / At least 2 enabled, working models are needed. "
                                       f"Usable staff: {len(staff)}." + (f" Skipped: {skip_txt}" if skip_txt else ""), "skipped": skipped})
            # desks: enabled people (present or empty)
            present_names = {p["name"] for p in staff} | reserved
            desks = []
            for p in s["participants"]:
                if not p.get("enabled"): continue
                seat = "boss" if manager and p["name"]==manager["name"] else "secretary" if secretary and p["name"]==secretary["name"] else "employee"
                role, title = p.get("role",""), (roles.get(p.get("role") or "", {}) or {}).get("title", "")
                if seat == "boss": title = "مدیر"
                if seat == "secretary": title = "منشی"
                src = manager if seat=="boss" else secretary if seat=="secretary" else next((x for x in staff if x["name"]==p["name"]), p)
                desks.append({"name": p["name"], "provider": p["provider"], "model": p["model"], "role": role,
                              "role_title": title or src.get("role_title") or "", "present": p["name"] in present_names,
                              "seat": seat, "reason": next((r for n,r in skipped if n==p["name"]), "")})
            with LOCK:
                STOP.clear()
                cont = bool(d.get("continue")) and STATE["messages"]
                STATE.update(running=True, topic=topic, participants=staff,
                             rounds=max(1, min(50, int(d.get("rounds") or conf["rounds"]))), status="starting",
                             mode={"office": use_office, "manager": bool(manager), "compact": use_compact, "timeout": timeout,
                                   "manager_name": manager["name"] if manager else "", "secretary_name": secretary["name"] if secretary else ""},
                             desks=desks, office={"boss": manager, "secretary": secretary})
                if not cont:
                    STATE["messages"] = [{"speaker": "Salar", "text": "Topic: " + topic, "kind": "user", "t": time.strftime("%H:%M:%S")}]
                    STATE["usage"] = empty_usage()
            with LOCK:
                STATE["judge"] = judge
                STATE["manager"] = manager
                STATE["secretary"] = secretary
            try:
                start_project(topic, cont=bool(d.get("continue")), rounds=int((STATE.get("rounds") or 0)))
            except Exception as e:
                app_log("start_project failed: %s" % e)
            flags = []
            if use_office: flags.append("دفتر")
            if use_compact: flags.append("پروتکل فشرده")
            if manager: flags.append(f"مدیر: {manager['name']}")
            if secretary: flags.append(f"منشی: {secretary['name']}")
            add_msg("system", ("کارکنان حاضر: " if use_office else "Participants: ") + ", ".join(p["name"] + (f" ({p['role_title']})" if p.get("role_title") else "") for p in staff)
                    + (f" | Judge: {judge['name']}" if judge else "")
                    + (f" | {', '.join(flags)}" if flags else "")
                    + (f" | timeout {timeout}s" if timeout else "")
                    + (f" | غایب: {skip_txt}" if skip_txt else ""), "system")
            if use_office and manager:
                threading.Thread(target=run_office, args=(topic, staff, STATE["rounds"], manager, secretary, judge, timeout), daemon=True).start()
            else:
                threading.Thread(target=run_discussion, args=(topic, staff, STATE["rounds"], judge, manager, use_compact, timeout), daemon=True).start()
            return self.send(200, {"ok": True, "participants": [p["name"] for p in staff],
                                   "judge": judge["name"] if judge else None, "manager": manager["name"] if manager else None,
                                   "secretary": secretary["name"] if secretary else None,
                                   "office": use_office, "compact": use_compact, "skipped": skipped})
        if self.path == "/api/say":
            t = str(d.get("text", "")).strip()
            app_log(f"POST /api/say len={len(t)} preview={t[:80]!r}")
            if not t: return self.send(200, {"ok": True})
            add_msg("Salar", t, "user")
            with LOCK:
                running = STATE["running"]
            if running:
                app_log("POST /api/say queued (already running)")
                return self.send(200, {"ok": True, "queued": True, "status": "busy"})
            try:
                hint = t if len(t) < 80 else "گفتگوی آزاد با مدیر"
                boss, secretary, timeout = bootstrap_office_chat(hint)
            except Exception as e:
                app_log(f"POST /api/say bootstrap failed: {e}")
                add_msg("system", f"پاسخ مدیر ارسال نشد: {e}", "system")
                return self.send(200, {"ok": False, "error": str(e)})
            with LOCK:
                topic = STATE.get("topic") or hint
                staff = list(STATE.get("participants") or [])
            people = staff + [p for p in (boss, secretary) if p]
            if boss:
                boss["office_seat"] = "boss"
            target = resolve_mention(t, people) or boss
            if not target:
                add_msg("system", "مدیری برای پاسخ پیدا نشد.", "system")
                app_log("POST /api/say no target")
                return self.send(200, {"ok": False, "error": "مدیری برای پاسخ پیدا نشد."})
            with LOCK:
                if STATE["running"]:
                    return self.send(200, {"ok": True, "queued": True})
                STATE["running"] = True
                STATE["status"] = "replying"
                STOP.clear()
            app_log(f"POST /api/say reply via {target.get('name')} ({target.get('provider')}/{target.get('model')})")
            threading.Thread(target=run_mention_reply, args=(target, topic, timeout), daemon=True).start()
            return self.send(200, {"ok": True, "direct": target["name"]})
        if self.path == "/api/stop":
            STOP.set(); return self.send(200, {"ok": True})
        if self.path == "/api/clear":
            with LOCK:
                if STATE["running"]: return self.send(409, {"error": "stop first"})
                STATE.update(messages=[], status="idle", topic="", usage=empty_usage(), mode={}, desks=[], office={})
            return self.send(200, {"ok": True})
        if self.path == "/api/save":
            with LOCK: msgs, topic, usage, mode = list(STATE["messages"]), STATE["topic"], dict(STATE.get("usage") or {}), dict(STATE.get("mode") or {})
            os.makedirs(os.path.join(BASE, "transcripts"), exist_ok=True)
            fn = os.path.join(BASE, "transcripts", datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".md")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(f"# {topic}\n\n")
                if usage: f.write(f"- tokens: {usage.get('total', 0)} (prompt {usage.get('prompt', 0)}, completion {usage.get('completion', 0)}, calls {usage.get('calls', 0)})\n")
                if mode: f.write(f"- mode: {json.dumps(mode, ensure_ascii=False)}\n")
                f.write("\n")
                for m in msgs:
                    extra = ""
                    if m.get("usage"): extra += f" · {m['usage'].get('total', 0)} tok"
                    f.write(f"**{m['speaker']}** ({m['t']}{extra}):\n\n{m['text']}\n\n---\n\n")
            return self.send(200, {"ok": True, "file": fn, "usage": usage})
        self.send(404, {"error": "not found"})

if __name__ == "__main__":
    print(f"AI Roundtable on http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
