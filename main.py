import os
import sys
import re
import json
import time
import ctypes
import threading
import mimetypes
import http.server
import socketserver
import webview

try:
    from pypresence import Presence
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

DISCORD_CLIENT_ID = "ВСТАВЬТЕ_СЮДА_ВАШ_APPLICATION_ID"

user32 = ctypes.windll.user32
GA_ROOT = 2
VK_F2 = 0x71
VK_F5 = 0x74
VK_F11 = 0x7A

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "kalel")
DATA_DIR = os.path.join(APP_DIR, "BrowserProfile")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    "--autoplay-policy=no-user-gesture-required "
    "--enable-features=OverlayScrollbar,DnsOverHttps "
    "--dns-over-https-templates=https://dns.adguard-dns.com/dns-query"
)

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
)

DEFAULT_CONFIG = {
    "first_run": True,
    "start_url": "https://old.yummyani.me",
    "intro_duration": 5.0,
    "intro_audio_path": "",
    "intro_anim_path": "",
    "bookmarks": [
        {"name": "YummyAnime", "url": "https://old.yummyani.me"},
        {"name": "YouTube", "url": "https://www.youtube.com"}
    ]
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    return url

def clean_anime_title(raw_title: str) -> str:
    if not raw_title:
        return ""
    t = re.sub(r'(смотреть онлайн|в хорошем качестве|все серии|озвучка|субтитры).*', '', raw_title, flags=re.IGNORECASE)
    t = t.replace('— YummyAnime', '').replace('| YummyAnime', '').replace('- YouTube', '').strip(' -–—|')
    return t.strip()

def discord_rpc_worker():
    if not HAS_DISCORD or not DISCORD_CLIENT_ID or DISCORD_CLIENT_ID == "ВСТАВЬТЕ_СЮДА_ВАШ_APPLICATION_ID":
        return

    rpc = None
    app_start_time = int(time.time())
    current_anime_name = ""
    anime_watch_start = app_start_time

    while True:
        time.sleep(3.5)

        if rpc is None:
            try:
                rpc = Presence(DISCORD_CLIENT_ID)
                rpc.connect()
            except Exception:
                rpc = None
                time.sleep(5)
                continue

        try:
            if not main_window:
                continue

            current_url = main_window.get_current_url() or ""

            if "127.0.0.1" in current_url:
                rpc.update(
                    details="Запуск kalel...",
                    state="Загрузка",
                    large_image="cat",
                    large_text="kalel Player",
                    start=app_start_time
                )
                continue

            js_code = """
            (function() {
                try {
                    var h1 = document.querySelector('h1');
                    var title = h1 ? h1.innerText : document.title;
                    var ep = document.querySelector('.episode-item.active, .ep-btn.active, [class*="active"][class*="ep"]');
                    return JSON.stringify({
                        title: title || '',
                        ep: ep ? ep.innerText : ''
                    });
                } catch(e) {
                    return JSON.stringify({ title: document.title || '', ep: '' });
                }
            })()
            """
            raw_res = main_window.evaluate_js(js_code)
            parsed = json.loads(raw_res) if raw_res else {}

            raw_title = parsed.get("title", "")
            episode_info = parsed.get("ep", "").strip()
            clean_title = clean_anime_title(raw_title)

            if clean_title and len(clean_title) >= 2 and "Главная" not in clean_title:
                if clean_title != current_anime_name:
                    current_anime_name = clean_title
                    anime_watch_start = int(time.time())

                details_text = f"Смотрит: {clean_title}"[:128]
                state_text = f"Серия: {episode_info}" if episode_info else "Просмотр тайтла"
                timer = anime_watch_start
            else:
                details_text = "Выбирает аниме..."
                state_text = "В каталоге"
                timer = app_start_time

            buttons = None
            if current_url.startswith("http") and "127.0.0.1" not in current_url:
                buttons = [{"label": "Смотреть вместе", "url": current_url}]

            try:
                rpc.update(
                    details=details_text,
                    state=state_text,
                    large_image="cat",
                    large_text="kalel Anime Player",
                    start=timer,
                    buttons=buttons
                )
            except Exception:
                rpc.update(
                    details=details_text,
                    state=state_text,
                    start=timer
                )

        except Exception:
            rpc = None

local_port = 0

class SplashServerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        cfg = load_config()
        path = self.path.split("?")[0]

        if path == "/welcome":
            html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Начальная настройка — kalel</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body {
    background:#0f0f13;
    color:#f3f4f6;
    width:100vw; height:100vh;
    display:flex; justify-content:center; align-items:center;
    user-select:none;
}
.box {
    background:#171821;
    border:1px solid #2b2d3c;
    border-radius:12px;
    padding:28px;
    width:460px;
    box-shadow:0 12px 30px rgba(0,0,0,0.5);
    text-align:center;
}
h2 { font-size:22px; margin-bottom:8px; color:#fff; }
p { font-size:13px; color:#9ca3af; margin-bottom:20px; line-height:1.4; }
.btn-primary {
    width:100%;
    background:#8b5cf6;
    color:#fff;
    border:none;
    border-radius:8px;
    padding:12px;
    font-size:14px;
    font-weight:600;
    cursor:pointer;
    margin-bottom:16px;
    transition:background 0.15s;
}
.btn-primary:hover { background:#7c3aed; }
.divider {
    display:flex; align-items:center; text-align:center;
    color:#6b7280; font-size:12px; margin:16px 0;
}
.divider::before, .divider::after {
    content:''; flex:1; border-bottom:1px solid #2b2d3c;
}
.divider::before { margin-right:8px; }
.divider::after { margin-left:8px; }
.input-row { display:flex; gap:8px; }
input {
    flex:1;
    background:#0d0d12;
    border:1px solid #2b2d3c;
    border-radius:6px;
    color:#fff;
    padding:10px 12px;
    font-size:13px;
    outline:none;
}
input:focus { border-color:#8b5cf6; }
.btn-sec {
    background:#262737;
    color:#fff;
    border:none;
    border-radius:6px;
    padding:10px 14px;
    font-size:13px;
    font-weight:500;
    cursor:pointer;
    transition:background 0.15s;
}
.btn-sec:hover { background:#34364c; }
</style>
</head>
<body>
<div class="box">
    <h2>Добро пожаловать в kalel</h2>
    <p>Выберите стартовый сайт, который будет открываться по умолчанию при каждом запуске программы:</p>
    <button class="btn-primary" onclick="chooseYummy()">Открыть YummyAnime (old.yummyani.me)</button>
    <div class="divider">или задайте свой сайт</div>
    <div class="input-row">
        <input type="text" id="customUrl" placeholder="например: youtube.com" onkeydown="if(event.key==='Enter') chooseCustom()" />
        <button class="btn-sec" onclick="chooseCustom()">Сохранить</button>
    </div>
</div>
<script>
async function chooseYummy() {
    if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.finish_first_run("https://old.yummyani.me");
    }
}
async function chooseCustom() {
    const val = document.getElementById('customUrl').value;
    if (!val || !val.trim()) return;
    if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.finish_first_run(val.trim());
    }
}
</script>
</body>
</html>"""
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path in ["/", "/splash"]:
            anim_path = cfg.get("intro_anim_path", "")
            audio_path = cfg.get("intro_audio_path", "")
            duration = float(cfg.get("intro_duration", 5.0))
            target_url = cfg.get("start_url", DEFAULT_CONFIG["start_url"])

            has_anim = bool(anim_path and os.path.exists(anim_path))
            has_audio = bool(audio_path and os.path.exists(audio_path))

            anim_ext = os.path.splitext(anim_path)[1].lower() if has_anim else ""
            is_video = anim_ext in [".mp4", ".webm"]

            if has_anim:
                if is_video:
                    anim_tag = '<video src="/anim" autoplay playsinline loop class="media"></video>'
                else:
                    anim_tag = '<img src="/anim" class="media" />'
            else:
                anim_tag = '<div style="font-size: 38px; font-weight: bold; color: #8b5cf6;">kalel</div>'

            audio_tag = '<audio src="/audio" autoplay></audio>' if has_audio else ""

            html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    background:#0f0f13;
    width:100vw; height:100vh;
    display:flex; justify-content:center; align-items:center;
    overflow:hidden; cursor:pointer; user-select:none;
    font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
.media {{
    max-width:85vw; max-height:80vh;
    object-fit:contain; border-radius:12px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.7);
}}
.p-bar-wrap {{
    position:fixed; bottom:25px; left:50%; transform:translateX(-50%);
    width:260px; height:4px; background:rgba(255,255,255,0.15);
    border-radius:4px; overflow:hidden;
}}
.p-bar {{
    width:0%; height:100%; background:#8b5cf6;
    transition: width {duration}s linear;
}}
.hint {{
    position:fixed; bottom:8px; left:50%; transform:translateX(-50%);
    font-size:11px; color:rgba(255,255,255,0.4);
}}
</style>
</head>
<body onclick="skip()">
{audio_tag}
{anim_tag}
<div class="p-bar-wrap"><div id="bar" class="p-bar"></div></div>
<div class="hint">Кликните или нажмите Пробел / Esc для пропуска</div>
<script>
const target = "{target_url}";
let done = false;
function skip() {{
    if (done) return;
    done = true;
    window.location.href = target;
}}
window.addEventListener('DOMContentLoaded', () => {{
    setTimeout(() => {{
        const b = document.getElementById('bar');
        if (b) b.style.width = '100%';
    }}, 40);
    setTimeout(skip, {int(duration * 1000)});
}});
window.addEventListener('keydown', skip);
</script>
</body>
</html>"""
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path == "/anim":
            self.serve_file(cfg.get("intro_anim_path", ""))

        elif path == "/audio":
            self.serve_file(cfg.get("intro_audio_path", ""))

        else:
            self.send_error(404)

    def serve_file(self, filepath):
        if not filepath or not os.path.exists(filepath):
            self.send_error(404)
            return
        try:
            mime_type, _ = mimetypes.guess_type(filepath)
            ext = os.path.splitext(filepath)[1].lower()
            if not mime_type:
                if ext == '.mp3': mime_type = 'audio/mpeg'
                elif ext == '.mp4': mime_type = 'video/mp4'
                elif ext == '.webm': mime_type = 'video/webm'
                elif ext == '.gif': mime_type = 'image/gif'
                else: mime_type = 'application/octet-stream'

            size = os.path.getsize(filepath)
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(filepath, "rb") as f:
                while chunk := f.read(128 * 1024):
                    self.wfile.write(chunk)
        except Exception:
            pass

def run_local_server():
    global local_port
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), SplashServerHandler)
    local_port = server.server_address[1]
    server.serve_forever()

SETTINGS_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Настройки — kalel</title>
    <style>
        :root {
            --bg: #111116;
            --card-bg: #191a24;
            --accent: #8b5cf6;
            --accent-hover: #7c3aed;
            --text: #f3f4f6;
            --text-dim: #9ca3af;
            --border: #2b2d3c;
            --danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 18px; font-size: 13px; user-select: none; }
        h2 { font-size: 17px; margin-bottom: 4px; color: #fff; }
        p.desc { font-size: 12px; color: var(--text-dim); margin-bottom: 12px; }
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 12px; }
        .row { display: flex; gap: 6px; margin-top: 6px; align-items: center; }
        input[type="text"], input[type="number"] {
            flex: 1;
            background: #0d0d12;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: #fff;
            padding: 7px 10px;
            font-size: 13px;
            outline: none;
        }
        input:focus { border-color: var(--accent); }
        button {
            background: var(--accent);
            color: #fff;
            border: none;
            border-radius: 6px;
            padding: 7px 12px;
            cursor: pointer;
            font-weight: 500;
            font-size: 12px;
            transition: background 0.15s;
            white-space: nowrap;
        }
        button:hover { background: var(--accent-hover); }
        button.btn-sec { background: #262737; color: #e5e7eb; }
        button.btn-sec:hover { background: #34364c; }
        button.btn-del { background: transparent; color: var(--danger); padding: 5px 8px; }
        button.btn-del:hover { background: rgba(239, 68, 68, 0.15); }
        .bm-list { display: flex; flex-direction: column; gap: 5px; max-height: 140px; overflow-y: auto; margin-top: 6px; }
        .bm-item { display: flex; align-items: center; justify-content: space-between; background: #0d0d12; border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px; }
        .bm-info { display: flex; flex-direction: column; overflow: hidden; }
        .bm-name { font-weight: 600; font-size: 12px; }
        .bm-url { font-size: 11px; color: var(--text-dim); white-space: nowrap; text-overflow: ellipsis; overflow: hidden; max-width: 240px; }
        .bm-actions { display: flex; gap: 4px; }
        .toast {
            position: fixed;
            bottom: 12px;
            left: 50%;
            transform: translateX(-50%);
            background: #10b981;
            color: #fff;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
        }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <h2>Настройки — kalel</h2>
    <p class="desc">Клавиши: <b>F11</b> — полный экран | <b>F2</b> — настройки | <b>F5</b> — обновить</p>

    <div class="card" style="border-left: 3px solid var(--accent);">
        <strong>Заставка при запуске (Интро)</strong>
        <div style="margin-top: 8px;">
            <label style="font-size: 11px; color: var(--text-dim);">Длительность заставки (сек):</label>
            <div class="row">
                <input type="number" id="introDuration" min="1" max="60" step="0.5" value="5" style="max-width: 100px;" />
                <span style="color: var(--text-dim);">сек</span>
            </div>
        </div>

        <div style="margin-top: 10px;">
            <label style="font-size: 11px; color: var(--text-dim);">Файл звука (MP3, WAV, OGG):</label>
            <div class="row">
                <input type="text" id="introAudioPath" readonly placeholder="Звук не выбран" />
                <button class="btn-sec" onclick="pickAudio()">Выбрать</button>
                <button class="btn-del" onclick="clearAudio()">X</button>
            </div>
        </div>

        <div style="margin-top: 10px;">
            <label style="font-size: 11px; color: var(--text-dim);">Анимация (GIF, MP4, WEBM, PNG):</label>
            <div class="row">
                <input type="text" id="introAnimPath" readonly placeholder="Анимация не выбрана" />
                <button class="btn-sec" onclick="pickAnim()">Выбрать</button>
                <button class="btn-del" onclick="clearAnim()">X</button>
            </div>
        </div>

        <div class="row" style="margin-top: 12px;">
            <button onclick="saveIntroSettings()" style="width: 100%;">Сохранить настройки заставки</button>
        </div>
    </div>

    <div class="card">
        <strong>Стартовый сайт</strong>
        <div class="row">
            <input type="text" id="startUrlInput" placeholder="https://old.yummyani.me" />
            <button onclick="saveStartUrl()">Сохранить</button>
        </div>
    </div>

    <div class="card">
        <strong>Открыть сайт прямо сейчас</strong>
        <div class="row">
            <input type="text" id="quickUrlInput" placeholder="youtube.com" onkeydown="if(event.key==='Enter') quickNav()" />
            <button onclick="quickNav()">Перейти</button>
        </div>
    </div>

    <div class="card">
        <strong>Закладки</strong>
        <div class="bm-list" id="bmContainer"></div>
        <div class="row" style="margin-top: 8px;">
            <input type="text" id="bmName" placeholder="Название" style="flex: 0.8;" />
            <input type="text" id="bmUrl" placeholder="https://..." />
            <button onclick="addBookmark()">+ Добавить</button>
        </div>
    </div>

    <div class="card">
        <strong>Данные аккаунтов и Cookie</strong>
        <p class="desc">Все сессии и куки сохраняются автоматически.</p>
        <button class="btn-sec" onclick="openProfileFolder()">Открыть папку с профилем</button>
    </div>

    <div id="toast" class="toast">Сохранено</div>

    <script>
        async function init() {
            if (window.pywebview && window.pywebview.api) {
                const data = await window.pywebview.api.get_data();
                document.getElementById('startUrlInput').value = data.start_url || '';
                document.getElementById('introDuration').value = data.intro_duration || 5;
                document.getElementById('introAudioPath').value = data.intro_audio_path || '';
                document.getElementById('introAnimPath').value = data.intro_anim_path || '';
                renderBookmarks(data.bookmarks || []);
            }
        }
        window.addEventListener('pywebviewready', init);
        setTimeout(init, 200);

        function renderBookmarks(list) {
            const container = document.getElementById('bmContainer');
            container.innerHTML = '';
            if (!list || list.length === 0) {
                container.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:6px;">Закладок нет</div>';
                return;
            }
            list.forEach((bm, i) => {
                const item = document.createElement('div');
                item.className = 'bm-item';
                item.innerHTML = `
                    <div class="bm-info">
                        <span class="bm-name">${bm.name}</span>
                        <span class="bm-url">${bm.url}</span>
                    </div>
                    <div class="bm-actions">
                        <button onclick="navTo('${bm.url}')">Перейти</button>
                        <button class="btn-del" onclick="delBm(${i})">X</button>
                    </div>
                `;
                container.appendChild(item);
            });
        }

        async function pickAudio() {
            const path = await window.pywebview.api.choose_audio_file();
            if (path) document.getElementById('introAudioPath').value = path;
        }

        function clearAudio() {
            document.getElementById('introAudioPath').value = '';
        }

        async function pickAnim() {
            const path = await window.pywebview.api.choose_anim_file();
            if (path) document.getElementById('introAnimPath').value = path;
        }

        function clearAnim() {
            document.getElementById('introAnimPath').value = '';
        }

        async function saveIntroSettings() {
            const dur = parseFloat(document.getElementById('introDuration').value) || 5;
            const audio = document.getElementById('introAudioPath').value;
            const anim = document.getElementById('introAnimPath').value;
            await window.pywebview.api.save_intro_settings(dur, audio, anim);
            showToast("Заставка сохранена!");
        }

        async function saveStartUrl() {
            const url = document.getElementById('startUrlInput').value;
            const ok = await window.pywebview.api.save_start_url(url);
            if (ok) showToast("Стартовый сайт сохранен!");
        }

        async function quickNav() {
            const url = document.getElementById('quickUrlInput').value;
            if (!url) return;
            await window.pywebview.api.navigate(url);
            showToast("Переход выполнен!");
        }

        async function navTo(url) {
            await window.pywebview.api.navigate(url);
            showToast("Переход выполнен!");
        }

        async function addBookmark() {
            const name = document.getElementById('bmName').value;
            const url = document.getElementById('bmUrl').value;
            if (!url) return;
            const updated = await window.pywebview.api.add_bookmark(name, url);
            renderBookmarks(updated);
            document.getElementById('bmName').value = '';
            document.getElementById('bmUrl').value = '';
            showToast("Закладка добавлена!");
        }

        async function delBm(idx) {
            const updated = await window.pywebview.api.remove_bookmark(idx);
            renderBookmarks(updated);
            showToast("Закладка удалена");
        }

        function openProfileFolder() {
            window.pywebview.api.open_profile_folder();
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.className = 'toast show';
            setTimeout(() => { t.className = 'toast'; }, 2200);
        }
    </script>
</body>
</html>
"""

main_window = None
settings_window = None

class MainAPI:
    def finish_first_run(self, url):
        norm = normalize_url(url) or DEFAULT_CONFIG["start_url"]
        cfg = load_config()
        cfg["first_run"] = False
        cfg["start_url"] = norm
        save_config(cfg)
        if main_window:
            main_window.load_url(norm)
        return True

class SettingsAPI:
    def get_data(self):
        cfg = load_config()
        return {
            "start_url": cfg.get("start_url", DEFAULT_CONFIG["start_url"]),
            "intro_duration": cfg.get("intro_duration", 5.0),
            "intro_audio_path": cfg.get("intro_audio_path", ""),
            "intro_anim_path": cfg.get("intro_anim_path", ""),
            "bookmarks": cfg.get("bookmarks", [])
        }

    def choose_audio_file(self):
        if settings_window:
            res = settings_window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Аудиофайлы (*.mp3;*.wav;*.ogg)', 'Все файлы (*.*)')
            )
            if res and len(res) > 0:
                return res[0]
        return ""

    def choose_anim_file(self):
        if settings_window:
            res = settings_window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Анимации и видео (*.gif;*.mp4;*.webm;*.png;*.jpg)', 'Все файлы (*.*)')
            )
            if res and len(res) > 0:
                return res[0]
        return ""

    def save_intro_settings(self, duration, audio_path, anim_path):
        cfg = load_config()
        cfg["intro_duration"] = max(0.5, float(duration))
        cfg["intro_audio_path"] = audio_path.strip()
        cfg["intro_anim_path"] = anim_path.strip()
        save_config(cfg)
        return True

    def navigate(self, url):
        norm = normalize_url(url)
        if main_window and norm:
            main_window.load_url(norm)
        return True

    def save_start_url(self, url):
        norm = normalize_url(url)
        if norm:
            cfg = load_config()
            cfg["start_url"] = norm
            save_config(cfg)
            return True
        return False

    def add_bookmark(self, name, url):
        norm = normalize_url(url)
        if not norm:
            return []
        if not name or not name.strip():
            name = norm.replace("https://", "").replace("http://", "").split("/")[0]
        cfg = load_config()
        cfg.setdefault("bookmarks", []).append({"name": name.strip(), "url": norm})
        save_config(cfg)
        return cfg["bookmarks"]

    def remove_bookmark(self, idx):
        cfg = load_config()
        bms = cfg.get("bookmarks", [])
        if 0 <= idx < len(bms):
            bms.pop(idx)
            cfg["bookmarks"] = bms
            save_config(cfg)
        return cfg.get("bookmarks", [])

    def open_profile_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(DATA_DIR)
            else:
                os.system(f'xdg-open "{DATA_DIR}"')
        except Exception:
            pass
        return True

def open_settings():
    global settings_window
    if settings_window is not None:
        try:
            settings_window.show()
            settings_window.restore()
            return
        except Exception:
            settings_window = None

    settings_window = webview.create_window(
        title="Настройки — kalel",
        html=SETTINGS_HTML,
        js_api=SettingsAPI(),
        width=560,
        height=720,
        resizable=True
    )

    def on_closed():
        global settings_window
        settings_window = None

    settings_window.events.closed += on_closed

def native_hotkeys_listener():
    f11_down = False
    f2_down = False
    f5_down = False

    while True:
        time.sleep(0.04)
        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd:
            continue

        root_hwnd = user32.GetAncestor(fg_hwnd, GA_ROOT)
        main_hwnd = user32.FindWindowW(None, "kalel")
        settings_hwnd = user32.FindWindowW(None, "Настройки — kalel")

        is_our_window = (fg_hwnd in (main_hwnd, settings_hwnd)) or (root_hwnd in (main_hwnd, settings_hwnd))
        if not is_our_window:
            continue

        if user32.GetAsyncKeyState(VK_F11) & 0x8000:
            if not f11_down:
                f11_down = True
                if main_window:
                    main_window.toggle_fullscreen()
        else:
            f11_down = False

        if user32.GetAsyncKeyState(VK_F2) & 0x8000:
            if not f2_down:
                f2_down = True
                open_settings()
        else:
            f2_down = False

        if user32.GetAsyncKeyState(VK_F5) & 0x8000:
            if not f5_down:
                f5_down = True
                if main_window:
                    main_window.evaluate_js("location.reload();")
        else:
            f5_down = False

def inject_adblock(window):
    script = """
    (function() {
        if (window.__adguard_injected) return;
        window.__adguard_injected = true;

        var origOpen = window.open;
        window.open = function(url) {
            if (!url) return null;
            var u = String(url).toLowerCase();
            if (u.includes('1win') || u.includes('1xbet') || u.includes('bet') || 
                u.includes('casino') || u.includes('vulkan') || u.includes('click') || 
                u.includes('pop') || u.includes('track') || u.includes('ad')) {
                return null;
            }
            return origOpen.apply(this, arguments);
        };

        var css = `
            [id*="yandex_rtb"], [class*="yandex-rtb"],
            [id*="google_ads"], [class*="google_ads"],
            iframe[src*="an.yandex.ru"], iframe[src*="doubleclick"],
            iframe[src*="adroll"], iframe[src*="exoclick"],
            .banner-ad, .ad-banner, .advertisement,
            [class*="clickunder"], [id*="clickunder"],
            [class*="popunder"], [id*="popunder"] {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                width: 0 !important;
                opacity: 0 !important;
                pointer-events: none !important;
            }
        `;
        var style = document.createElement('style');
        style.innerHTML = css;
        (document.head || document.documentElement).appendChild(style);
    })();
    """
    try:
        window.run_js(script)
    except Exception:
        pass

def start_watchdog_timer(target_url, timeout_sec):
    def timer_worker():
        time.sleep(timeout_sec + 0.8)
        try:
            curr = main_window.get_current_url()
            if curr and f"127.0.0.1:{local_port}" in curr:
                main_window.load_url(target_url)
        except Exception:
            pass
    threading.Thread(target=timer_worker, daemon=True).start()

def main():
    global main_window
    os.makedirs(DATA_DIR, exist_ok=True)

    threading.Thread(target=run_local_server, daemon=True).start()
    threading.Thread(target=native_hotkeys_listener, daemon=True).start()
    threading.Thread(target=discord_rpc_worker, daemon=True).start()

    time.sleep(0.1)

    config = load_config()
    is_first_run = config.get("first_run", True)
    real_start_url = config.get("start_url", DEFAULT_CONFIG["start_url"])
    intro_audio = config.get("intro_audio_path", "")
    intro_anim = config.get("intro_anim_path", "")
    intro_duration = float(config.get("intro_duration", 5.0))

    has_audio = intro_audio and os.path.exists(intro_audio)
    has_anim = intro_anim and os.path.exists(intro_anim)

    if is_first_run:
        target_initial_url = f"http://127.0.0.1:{local_port}/welcome"
    elif (has_audio or has_anim) and intro_duration > 0:
        target_initial_url = f"http://127.0.0.1:{local_port}/splash"
        start_watchdog_timer(real_start_url, intro_duration)
    else:
        target_initial_url = real_start_url

    main_window = webview.create_window(
        title="kalel",
        url=target_initial_url,
        js_api=MainAPI(),
        width=1280,
        height=820,
        min_size=(640, 480),
        background_color="#0f0f13"
    )

    main_window.events.loaded += lambda: inject_adblock(main_window)

    webview.start(
        storage_path=DATA_DIR,
        private_mode=False,
        user_agent=DESKTOP_USER_AGENT
    )

if __name__ == '__main__':
    main()