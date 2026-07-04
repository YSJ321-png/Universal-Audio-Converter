"""
万能音频转换器 - 安全加固版（外网可部署版）
移除本地IP限制，监听0.0.0.0，全部原有安全防护保留，UI前端无需改动
修改：把提问模板从DeepSeek替换为豆包
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import subprocess, os, tempfile, json, traceback, glob, struct, base64, sys, time, re, hashlib, secrets
from hashlib import md5
from Crypto.Cipher import AES
from datetime import datetime
from collections import defaultdict
import threading

# ==================== 配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(BASE_DIR, 'tmp')
os.makedirs(TMP_DIR, exist_ok=True)

ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'YSJ-admin-token-2024')

ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.wma', '.opus', '.amr', '.spx', '.ra', '.aiff', '.ape', '.wv', '.tta', '.caf', '.pcm', '.webm', '.au', '.ac3', '.dts', '.alac', '.ncm'}
ALLOWED_FORMATS = {'mp3', 'aac', 'wav', 'flac', 'ogg', 'alac', 'aiff', 'ape', 'wv', 'tta', 'pcm', 'wma', 'opus', 'amr', 'spx', 'ra', 'ac3', 'dts', 'au', 'caf', 'm4a', 'webm'}
ALLOWED_ENGINES = {'ffmpeg', 'independent'}
ALLOWED_ALGORITHMS = {'auto', 'builtin', 'ncmdump'}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024
MAX_CONCURRENT_REQUESTS = 10
MAX_FEEDBACK_LENGTH = 2000
semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

SECURITY_HEADERS = [
    ('X-Content-Type-Options', 'nosniff'),
    ('X-Frame-Options', 'DENY'),
    ('X-XSS-Protection', '1; mode=block'),
    ('Referrer-Policy', 'no-referrer'),
    ('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:;")
]

# ==================== 安全工具函数 ====================
def validate_path_safety(filename):
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS and ext != '.ncm':
        raise ValueError(f'不支持的文件类型: {ext}')
    random_name = hashlib.sha256(os.urandom(32)).hexdigest()[:16] + ext
    return os.path.join(TMP_DIR, random_name)

def check_api_key(handler):
    auth = handler.headers.get('Authorization', '')
    return secrets.compare_digest(auth, f'Bearer {ADMIN_API_KEY}')

def add_security_headers(handler):
    for key, value in SECURITY_HEADERS:
        handler.send_header(key, value)

def write_error_log(code, msg, filename=None):
    ext = os.path.splitext(filename)[1] if filename else ''
    suggestion = '请确保文件来自官方客户端，或尝试重新下载' if ext == '.ncm' else '文件可能已损坏或被安全软件拦截，请检查文件完整性并重试'
    # 修改此处，把DeepSeek换成豆包
    deepseek_prompt = f'可以这样对豆包提问：“我在使用万能音频转换器时遇到错误：{msg}。文件后缀是 {ext or "未知"}，请问如何解决？”'
    log_entry = f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] [服务器{code}错误] 文件: {filename or "无"} {msg} → 建议: {suggestion}\n  💡 {deepseek_prompt}\n'
    with open(os.path.join(BASE_DIR, 'error_log.txt'), 'a', encoding='utf-8') as f:
        f.write(log_entry)

# ==================== 音频处理核心 ====================
def rc4_decrypt(key, data):
    s = bytearray(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    result = bytearray(len(data))
    i = j = 0
    for idx in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + s[j]) & 0xFF
        s[i], s[j] = s[j], s[i]
        result[idx] = data[idx] ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(result)

def builtin_decrypt_ncm(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    if data[:8] != b'CTENFDAM':
        raise ValueError('不是有效的 NCM 文件')
    offset = 10
    key_len = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    primary_key = data[offset:offset+key_len]
    offset += key_len
    json_len = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    encrypted_json = data[offset:offset+json_len]
    offset += json_len
    # WARNING: ECB mode is used because NCM format mandates it. Do not change unless NCM spec changes.
    cipher = AES.new(primary_key, AES.MODE_ECB)
    decrypted_json = cipher.decrypt(encrypted_json)
    pad_len = decrypted_json[-1]
    if pad_len > 0 and pad_len <= 16:
        decrypted_json = decrypted_json[:-pad_len]
    meta = json.loads(decrypted_json.decode('utf-8'))
    img_len = struct.unpack_from('<I', data, offset)[0]
    offset += 4 + img_len
    encrypted_audio = data[offset:]
    core_key = bytes([b ^ 0x64 for b in b'neteasecloudmusic'])
    key = md5(core_key).digest()
    enc_audio_key = base64.b64decode(meta['key'])
    # WARNING: ECB mode is required to decrypt NCM audio key. Do not change unless NCM spec changes.
    cipher2 = AES.new(key, AES.MODE_ECB)
    rc4_key = cipher2.decrypt(enc_audio_key)
    decrypted_audio = rc4_decrypt(rc4_key, encrypted_audio)
    return decrypted_audio, meta.get('format', 'mp3')

def ncmdump_decrypt(file_path):
    code = f'from ncmdump import dump; dump(r"{file_path}")'
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise ValueError('ncmdump 解密失败')
    base = os.path.splitext(file_path)[0]
    for m in glob.glob(base + '.*'):
        ext = os.path.splitext(m)[1].lower()
        if ext in ('.mp3', '.flac', '.wav', '.m4a'):
            with open(m, 'rb') as f:
                data = f.read()
            os.unlink(m)
            return data, ext[1:]
    raise ValueError('ncmdump 解密后未找到输出文件')

def get_audio_info(file_path):
    ffprobe_path = os.path.join(BASE_DIR, 'ffprobe.exe')
    cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    r = subprocess.run(cmd, capture_output=True, timeout=30, cwd=BASE_DIR)
    if r.returncode != 0:
        raise ValueError('ffprobe 分析失败')
    info = json.loads(r.stdout.decode('utf-8', errors='replace'))
    s = next((s for s in info.get('streams', []) if s['codec_type'] == 'audio'), None)
    if not s: raise ValueError('未找到音频流')
    dynamic_range = None
    try:
        ffmpeg_path = os.path.join(BASE_DIR, 'ffmpeg.exe')
        dr_cmd = [ffmpeg_path, '-i', file_path, '-af', 'volumedetect', '-t', '10', '-f', 'null', '-']
        dr_proc = subprocess.Popen(dr_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=BASE_DIR)
        _, dr_err = dr_proc.communicate(timeout=5)
        dr_output = dr_err.decode('utf-8', errors='replace')
        max_vol = min_vol = None
        for line in dr_output.split('\n'):
            if 'max_volume:' in line:
                try: max_vol = float(line.split(':')[1].strip().split(' ')[0])
                except: pass
            if 'min_volume:' in line:
                try: min_vol = float(line.split(':')[1].strip().split(' ')[0])
                except: pass
        if max_vol is not None and min_vol is not None:
            dynamic_range = round(max_vol - min_vol, 2)
    except:
        pass
    return {
        'sample_rate': int(s.get('sample_rate', 0)),
        'channels': int(s.get('channels', 0)),
        'bits_per_sample': int(s.get('bits_per_raw_sample', s.get('bits_per_sample', 16))),
        'duration': float(info.get('format', {}).get('duration', 0)),
        'dynamic_range': dynamic_range
    }

def convert_audio(fmt, input_data, engine='ffmpeg', input_filename=None):
    input_path = validate_path_safety(input_filename or 'audio.tmp')
    try:
        with open(input_path, 'wb') as f:
            f.write(input_data)
        if engine == 'independent':
            output_path = input_path + '.' + fmt
            exe_map = {
                'mp3': 'lame.exe',
                'flac': 'flac.exe',
                'ogg': 'oggenc2.exe',
                'opus': 'opusenc.exe',
                'aac': 'neroAacEnc.exe'
            }
            if fmt not in exe_map:
                raise ValueError(f'独立编码器不支持 {fmt}')
            exe = os.path.join(BASE_DIR, exe_map[fmt])
            args_map = {
                'mp3': ['-b', '192', input_path, output_path],
                'flac': ['--best', '-o', output_path, input_path],
                'ogg': ['-q', '6', '-o', output_path, input_path],
                'opus': ['--bitrate', '192', input_path, output_path],
                'aac': ['-br', '256000', '-if', input_path, '-of', output_path]
            }
            subprocess.run([exe] + args_map[fmt], check=True, capture_output=True, timeout=120, cwd=BASE_DIR)
            with open(output_path, 'rb') as f:
                return f.read()
        else:
            output_path = input_path + '.' + fmt
            ffmpeg_path = os.path.join(BASE_DIR, 'ffmpeg.exe')
            ffmpeg_cmd = [ffmpeg_path, '-y', '-i', input_path]
            if fmt == 'aac': ffmpeg_cmd += ['-c:a', 'aac', '-b:a', '256k', '-f', 'adts']
            elif fmt == 'mp3': ffmpeg_cmd += ['-c:a', 'libmp3lame', '-b:a', '192k', '-f', 'mp3']
            elif fmt == 'flac': ffmpeg_cmd += ['-c:a', 'flac', '-f', 'flac']
            elif fmt == 'ogg': ffmpeg_cmd += ['-c:a', 'libvorbis', '-f', 'ogg']
            elif fmt == 'wav': ffmpeg_cmd += ['-c:a', 'pcm_s16le', '-f', 'wav']
            elif fmt == 'alac': ffmpeg_cmd += ['-c:a', 'alac', '-f', 'ipod']
            elif fmt == 'aiff': ffmpeg_cmd += ['-c:a', 'pcm_s16be', '-f', 'aiff']
            elif fmt == 'ape': ffmpeg_cmd += ['-c:a', 'ape', '-f', 'ape']
            elif fmt == 'wv': ffmpeg_cmd += ['-c:a', 'wavpack', '-f', 'wv']
            elif fmt == 'tta': ffmpeg_cmd += ['-c:a', 'tta', '-f', 'tta']
            elif fmt == 'pcm': ffmpeg_cmd += ['-c:a', 'pcm_s16le', '-f', 's16le']
            elif fmt == 'wma': ffmpeg_cmd += ['-c:a', 'wmav2', '-b:a', '192k', '-f', 'asf']
            elif fmt == 'opus': ffmpeg_cmd += ['-c:a', 'libopus', '-f', 'opus']
            elif fmt == 'amr': ffmpeg_cmd += ['-c:a', 'libopencore_amrnb', '-ar', '8000', '-ac', '1', '-f', 'amr']
            elif fmt == 'spx': ffmpeg_cmd += ['-c:a', 'libspeex', '-f', 'ogg']
            elif fmt == 'ra': ffmpeg_cmd += ['-c:a', 'real_144', '-f', 'rm']
            elif fmt == 'ac3': ffmpeg_cmd += ['-c:a', 'ac3', '-b:a', '448k', '-f', 'ac3']
            elif fmt == 'dts': ffmpeg_cmd += ['-c:a', 'dts', '-b:a', '1536k', '-strict', '-2', '-f', 'dts']
            elif fmt == 'au': ffmpeg_cmd += ['-c:a', 'pcm_s16be', '-f', 'au']
            elif fmt == 'caf': ffmpeg_cmd += ['-c:a', 'pcm_s16le', '-f', 'caf']
            elif fmt == 'm4a': ffmpeg_cmd += ['-c:a', 'aac', '-b:a', '256k', '-f', 'ipod']
            elif fmt == 'webm': ffmpeg_cmd += ['-c:a', 'libvorbis', '-f', 'webm']
            else: raise ValueError(f'不支持的格式: {fmt}')
            ffmpeg_cmd.append(output_path)
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=120, cwd=BASE_DIR)
            with open(output_path, 'rb') as f:
                return f.read()
    finally:
        for p in [input_path, input_path + '.' + fmt]:
            if os.path.exists(p):
                try: os.unlink(p)
                except: pass

# ==================== HTTP 处理器 ====================
class SecureHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200); self.send_header('Content-Type','text/plain'); self.end_headers()
            self.wfile.write(b'pong')
        elif self.path == '/get_feedback':
            feedbacks = []
            fb_path = os.path.join(BASE_DIR, 'feedback.txt')
            if os.path.exists(fb_path):
                with open(fb_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try: feedbacks.append(json.loads(line))
                            except: pass
            self.send_response(200); self.send_header('Content-Type','application/json'); add_security_headers(self)
            self.end_headers()
            self.wfile.write(json.dumps(feedbacks, ensure_ascii=False).encode())
        elif self.path == '/get_error_log':
            if not check_api_key(self):
                self.send_response(403); self.end_headers(); return
            log_path = os.path.join(BASE_DIR, 'error_log.txt')
            logs = open(log_path, 'r', encoding='utf-8').read() if os.path.exists(log_path) else ''
            self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8'); add_security_headers(self)
            self.end_headers()
            self.wfile.write(logs.encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        if not semaphore.acquire(blocking=False):
            self.send_response(503); self.end_headers(); return
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > MAX_UPLOAD_SIZE:
                self.send_error(413, '上传文件过大')
                return
            body = self.rfile.read(content_length)
            content_type = self.headers.get('Content-Type', '')

            if 'multipart/form-data' in content_type:
                boundary = content_type.split('boundary=')[1].encode()
                parts = body.split(b'--' + boundary)
                file_data, filename, fmt, engine, algorithm = None, None, 'mp3', 'ffmpeg', 'auto'
                for part in parts:
                    if b'name="file"' in part:
                        h = part.find(b'\r\n\r\n')
                        if b'filename="' in part[:h]:
                            filename = part[:h].decode('utf-8','replace').split('filename="')[1].split('"')[0]
                        file_data = part[h+4:].rstrip(b'\r\n')
                    elif b'name="format"' in part:
                        fmt = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace').strip().lower()
                    elif b'name="engine"' in part:
                        engine = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace').strip().lower()
                    elif b'name="algorithm"' in part:
                        algorithm = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace').strip().lower()
                if not file_data: return self.send_error(400, '未收到文件')
                if self.path == '/convert' and fmt not in ALLOWED_FORMATS: return self.send_error(400, '格式不支持')
                if engine not in ALLOWED_ENGINES: return self.send_error(400, '引擎不支持')
                if algorithm not in ALLOWED_ALGORITHMS: return self.send_error(400, '算法不支持')

                is_ncm = filename and filename.lower().endswith('.ncm')
                if algorithm == 'ncmdump' and not is_ncm:
                    return self.send_error(400, '该模型仅 NCM 后缀可使用')

                if is_ncm:
                    ncm_path = validate_path_safety(filename)
                    try:
                        with open(ncm_path, 'wb') as f: f.write(file_data)
                        if algorithm == 'ncmdump':
                            dec_data, dec_fmt = ncmdump_decrypt(ncm_path)
                        elif algorithm == 'builtin':
                            dec_data, dec_fmt = builtin_decrypt_ncm(ncm_path)
                        else:
                            try: dec_data, dec_fmt = builtin_decrypt_ncm(ncm_path)
                            except: dec_data, dec_fmt = ncmdump_decrypt(ncm_path)
                        file_data = dec_data
                    finally:
                        if os.path.exists(ncm_path): os.unlink(ncm_path)

                if self.path == '/info':
                    info_path = validate_path_safety(filename or 'audio.tmp')
                    try:
                        with open(info_path, 'wb') as f: f.write(file_data)
                        info = get_audio_info(info_path)
                        self.send_response(200); self.send_header('Content-Type','application/json'); add_security_headers(self)
                        self.end_headers()
                        self.wfile.write(json.dumps(info, ensure_ascii=False).encode())
                    finally:
                        if os.path.exists(info_path): os.unlink(info_path)
                elif self.path == '/convert':
                    out_data = convert_audio(fmt, file_data, engine, filename)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="converted.{fmt}"')
                    self.send_header('Content-Length', str(len(out_data)))
                    add_security_headers(self)
                    self.end_headers()
                    self.wfile.write(out_data)

            elif 'application/json' in content_type:
                data = json.loads(body)
                if self.path == '/feedback':
                    text = data.get('feedback', '')
                    if len(text) > MAX_FEEDBACK_LENGTH:
                        text = text[:MAX_FEEDBACK_LENGTH]
                    if text.strip():
                        entry = {'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'feedback': text, 'reply': '', 'closed': False}
                        with open(os.path.join(BASE_DIR, 'feedback.txt'), 'a', encoding='utf-8') as f:
                            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                        self.send_response(200); self.send_header('Content-Type','application/json'); add_security_headers(self); self.end_headers()
                        self.wfile.write(b'{"status":"ok"}')
                    else:
                        self.send_error(400, '内容为空')
                elif self.path in ('/reply_feedback', '/close_feedback'):
                    if not check_api_key(self):
                        self.send_response(403); self.end_headers(); return
                    idx = data['index']
                    feedbacks = []
                    fb_path = os.path.join(BASE_DIR, 'feedback.txt')
                    if os.path.exists(fb_path):
                        with open(fb_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try: feedbacks.append(json.loads(line))
                                    except: pass
                    if 0 <= idx < len(feedbacks):
                        if self.path == '/reply_feedback':
                            feedbacks[idx]['reply'] = data['reply']
                        else:
                            feedbacks[idx]['closed'] = True
                        with open(fb_path, 'w', encoding='utf-8') as f:
                            for item in feedbacks: f.write(json.dumps(item, ensure_ascii=False) + '\n')
                        self.send_response(200); self.send_header('Content-Type','application/json'); add_security_headers(self); self.end_headers()
                        self.wfile.write(b'{"status":"ok"}')
                    else:
                        self.send_error(400, '无效索引')
                elif self.path == '/delete_log':
                    if not check_api_key(self):
                        self.send_response(403); self.end_headers(); return
                    log_path = os.path.join(BASE_DIR, 'error_log.txt')
                    if os.path.exists(log_path): os.remove(log_path)
                    self.send_response(200); add_security_headers(self); self.end_headers()
                else:
                    self.send_error(404)
            else:
                self.send_error(400)
        except Exception as e:
            write_error_log(500, str(e), getattr(filename, 'name', None))
            self.send_response(500); add_security_headers(self); self.end_headers()
        finally:
            semaphore.release()

    def send_error(self, code, message=None):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        add_security_headers(self)
        self.end_headers()
        if message:
            self.wfile.write(json.dumps({'error': message}).encode())

if __name__ == '__main__':
    if not os.path.exists(os.path.join(BASE_DIR, 'ffprobe.exe')):
        print('⚠️ 警告：未找到 ffprobe.exe，音频信息获取将不可用')
    error_log_path = os.path.join(BASE_DIR, 'error_log.txt')
    if not os.path.exists(error_log_path):
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write('')
    print('🚀 安全服务器启动: http://0.0.0.0:8000')
    print(f'📋 错误日志路径: {error_log_path}')
    server = HTTPServer(('0.0.0.0', 8000), SecureHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已关闭')
