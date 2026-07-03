from http.server import HTTPServer, SimpleHTTPRequestHandler
import subprocess, os, tempfile, json, traceback, glob, struct, base64, sys, time
from hashlib import md5
from Crypto.Cipher import AES
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
        j = (j + s[i]) & 0xFF
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
    cipher = AES.new(primary_key, AES.MODE_ECB)
    decrypted_json = cipher.decrypt(encrypted_json)
    pad_len = decrypted_json[-1]
    if pad_len > 0 and pad_len <= 16:
        decrypted_json = decrypted_json[:-pad_len]
    try:
        meta = json.loads(decrypted_json.decode('utf-8'))
    except:
        raise ValueError('NCM 元数据解析失败')
    img_len = struct.unpack_from('<I', data, offset)[0]
    offset += 4 + img_len
    encrypted_audio = data[offset:]
    core_key = bytes([b ^ 0x64 for b in b'neteasecloudmusic'])
    key = md5(core_key).digest()
    enc_audio_key = base64.b64decode(meta['key'])
    cipher2 = AES.new(key, AES.MODE_ECB)
    rc4_key = cipher2.decrypt(enc_audio_key)
    decrypted_audio = rc4_decrypt(rc4_key, encrypted_audio)
    fmt = meta.get('format', 'mp3')
    return decrypted_audio, fmt

def ncmdump_decrypt(file_path):
    code = f'from ncmdump import dump; dump(r"{file_path}")'
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise ValueError(f'ncmdump 解密失败: {result.stderr.strip()}')
    base = os.path.splitext(file_path)[0]
    matches = glob.glob(base + '.*')
    for m in matches:
        ext = os.path.splitext(m)[1].lower()
        if ext in ('.mp3', '.flac', '.wav', '.m4a'):
            with open(m, 'rb') as f:
                data = f.read()
            os.unlink(m)
            return data, ext[1:]
    raise ValueError('ncmdump 解密后未找到输出文件')

def send_json(handler, code, data, filename=None):
    if code >= 400:
        msg = data.get('error', '未知错误')
        ext = os.path.splitext(filename)[1] if filename else ''
        suggestion = ('请确保文件来自官方客户端，或尝试重新下载' if ext == '.ncm'
                      else '文件可能被安全软件拦截，请将程序目录加入信任区并重试')
        deepseek_prompt = f'可以这样对 DeepSeek 提问：“我在使用万能音频转换器时遇到错误：{msg}。文件后缀是 {ext or "未知"}，请问如何解决？”'
        with open('error_log.txt', 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] [服务器{code}错误] 文件: {filename or "无"} {msg} → 建议: {suggestion}\n  💡 {deepseek_prompt}\n')
    response = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', len(response))
    handler.end_headers()
    handler.wfile.write(response)

def get_audio_info_from_file(file_path):
    """通过临时文件分析音频，获取时长、动态范围等"""
    # 基本信息
    cmd = ['ffprobe.exe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    if r.returncode != 0:
        raise ValueError('ffprobe 分析失败')
    info = json.loads(r.stdout.decode('utf-8', errors='replace'))

    s = next((s for s in info.get('streams', []) if s['codec_type'] == 'audio'), None)
    if not s:
        raise ValueError('未找到音频流')

    # 时长：优先从 format 中取，否则从 stream 中取
    duration = float(info.get('format', {}).get('duration', s.get('duration', 0)))

    # 位深
    bits = int(s.get('bits_per_raw_sample', s.get('bits_per_sample', 16)))

    # 动态范围（只分析前 10 秒，超时 5 秒）
    dynamic_range = None
    try:
        dr_cmd = ['ffmpeg.exe', '-i', file_path, '-af', 'volumedetect', '-t', '10', '-f', 'null', '-']
        dr_proc = subprocess.Popen(dr_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    except subprocess.TimeoutExpired:
        dr_proc.kill()
    except Exception:
        pass

    return {
        'sample_rate': int(s.get('sample_rate', 0)),
        'channels': int(s.get('channels', 0)),
        'bits_per_sample': bits,
        'duration': duration,
        'dynamic_range': dynamic_range
    }

def encode_with_pipe(fmt, audio_data, engine='ffmpeg'):
    if engine == 'independent':
        tmp_in = os.path.join(BASE_DIR, 'temp_independent_input.bin')
        tmp_out = os.path.join(BASE_DIR, 'temp_independent_output.' + fmt)
        try:
            with open(tmp_in, 'wb') as f: f.write(audio_data)
            codec_map = {
                'mp3': {'exe': 'lame.exe', 'args': ['-b', '192', tmp_in, tmp_out]},
                'flac': {'exe': 'flac.exe', 'args': ['--best', '-o', tmp_out, tmp_in]},
                'ogg': {'exe': 'oggenc2.exe', 'args': ['-q', '6', '-o', tmp_out, tmp_in]},
                'opus': {'exe': 'opusenc.exe', 'args': ['--bitrate', '192', tmp_in, tmp_out]},
                'aac': {'exe': 'neroAacEnc.exe', 'args': ['-br', '256000', '-if', tmp_in, '-of', tmp_out]}
            }
            if fmt not in codec_map: raise ValueError(f'独立编码器不支持 {fmt} 格式')
            exe = codec_map[fmt]['exe']
            if not os.path.exists(exe): raise FileNotFoundError(f'未找到独立编码器 {exe}')
            subprocess.run([exe] + codec_map[fmt]['args'], check=True, capture_output=True, timeout=120)
            with open(tmp_out, 'rb') as f: return f.read()
        finally:
            if os.path.exists(tmp_in): os.unlink(tmp_in)
            if os.path.exists(tmp_out): os.unlink(tmp_out)

    ffmpeg_cmd = ['ffmpeg.exe', '-y', '-i', 'pipe:0']
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
    else: raise ValueError(f'不支持的输出格式: {fmt}')
    ffmpeg_cmd.append('pipe:1')
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate(input=audio_data, timeout=120)
    if proc.returncode != 0:
        error_msg = err.decode('utf-8', errors='replace')
        raise ValueError(f'FFmpeg 转换失败: {error_msg}')
    return out

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200); self.send_header('Content-Type','text/plain'); self.end_headers()
            self.wfile.write(b'pong')
        elif self.path == '/get_feedback':
            feedbacks = []
            if os.path.exists('feedback.txt'):
                with open('feedback.txt','r',encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try: feedbacks.append(json.loads(line))
                            except: feedbacks.append({'time':'','feedback':line,'reply':'','closed':False})
            send_json(self, 200, feedbacks)
        elif self.path == '/get_error_log':
            logs = open('error_log.txt','r',encoding='utf-8').read() if os.path.exists('error_log.txt') else ''
            self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8'); self.end_headers()
            self.wfile.write(logs.encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        try:
            if self.path in ('/info', '/convert'):
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length)
                boundary = self.headers['Content-Type'].split('boundary=')[1].encode()
                parts = body.split(b'--' + boundary)
                file_data, filename, fmt, engine, algorithm = None, None, None, 'ffmpeg', 'auto'
                for part in parts:
                    if b'name="file"' in part:
                        h = part.find(b'\r\n\r\n')
                        if b'filename="' in part[:h]: filename = part[:h].decode('utf-8','replace').split('filename="')[1].split('"')[0]
                        file_data = part[h+4:].rstrip(b'\r\n')
                    elif b'name="format"' in part:
                        fmt = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace')
                    elif b'name="engine"' in part:
                        engine = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace')
                    elif b'name="algorithm"' in part:
                        algorithm = part.split(b'\r\n\r\n',1)[1].split(b'\r\n')[0].decode('utf-8','replace')
                if not file_data: return send_json(self, 400, {'error':'未收到文件'}, filename)
                if self.path == '/convert' and not fmt: return send_json(self, 400, {'error':'缺少格式'}, filename)

                is_ncm = filename and filename.lower().endswith('.ncm')

                if algorithm == 'ncmdump' and not is_ncm:
                    return send_json(self, 400, {'error': '该模型仅 NCM 后缀可使用'}, filename)

                # 确定文件扩展名（用于信息分析）
                if is_ncm:
                    ncm_file = os.path.join(BASE_DIR, 'temp_ncm_input.ncm')
                    try:
                        with open(ncm_file, 'wb') as f: f.write(file_data)
                        if algorithm == 'ncmdump':
                            dec_data, dec_fmt = ncmdump_decrypt(ncm_file)
                        elif algorithm == 'builtin':
                            dec_data, dec_fmt = builtin_decrypt_ncm(ncm_file)
                        else:
                            try:
                                dec_data, dec_fmt = builtin_decrypt_ncm(ncm_file)
                            except Exception:
                                dec_data, dec_fmt = ncmdump_decrypt(ncm_file)
                        file_data = dec_data
                        info_ext = f'.{dec_fmt}'
                    finally:
                        if os.path.exists(ncm_file): os.unlink(ncm_file)
                else:
                    info_ext = os.path.splitext(filename)[1] or '.tmp'

                if self.path == '/info':
                    # 写入临时文件以便 ffprobe 分析
                    tmp_info = os.path.join(BASE_DIR, f'temp_info_audio{info_ext}')
                    try:
                        with open(tmp_info, 'wb') as f:
                            f.write(file_data)
                            f.flush()
                            os.fsync(f.fileno())
                        time.sleep(0.1)
                        info = get_audio_info_from_file(tmp_info)
                        send_json(self, 200, info)
                    except Exception as e:
                        send_json(self, 500, {'error': str(e)}, filename)
                    finally:
                        if os.path.exists(tmp_info): os.unlink(tmp_info)
                else:
                    out_data = encode_with_pipe(fmt, file_data, engine)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', len(out_data))
                    self.end_headers()
                    self.wfile.write(out_data)

            elif self.path == '/feedback':
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                    feedback_text = data.get('feedback', '')
                except:
                    return send_json(self, 400, {'error':'无效请求'})
                if feedback_text:
                    entry = {'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'feedback': feedback_text, 'reply': '', 'closed': False}
                    with open('feedback.txt', 'a', encoding='utf-8') as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                    send_json(self, 200, {'status':'ok'})
                else:
                    send_json(self, 400, {'error':'内容为空'})

            elif self.path == '/reply_feedback':
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                idx, reply = data['index'], data['reply']
                feedbacks = []
                if os.path.exists('feedback.txt'):
                    with open('feedback.txt', 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try: feedbacks.append(json.loads(line))
                                except: feedbacks.append({'time':'','feedback':line,'reply':'','closed':False})
                if 0 <= idx < len(feedbacks):
                    feedbacks[idx]['reply'] = reply
                    with open('feedback.txt', 'w', encoding='utf-8') as f:
                        for item in feedbacks: f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    send_json(self, 200, {'status':'ok'})
                else:
                    send_json(self, 400, {'error':'无效索引'})

            elif self.path == '/close_feedback':
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                idx = data['index']
                feedbacks = []
                if os.path.exists('feedback.txt'):
                    with open('feedback.txt', 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try: feedbacks.append(json.loads(line))
                                except: feedbacks.append({'time':'','feedback':line,'reply':'','closed':False})
                if 0 <= idx < len(feedbacks):
                    feedbacks[idx]['closed'] = True
                    with open('feedback.txt', 'w', encoding='utf-8') as f:
                        for item in feedbacks: f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    send_json(self, 200, {'status':'ok'})
                else:
                    send_json(self, 400, {'error':'无效索引'})

            elif self.path == '/delete_log':
                if os.path.exists('error_log.txt'): os.remove('error_log.txt')
                self.send_response(200); self.end_headers(); self.wfile.write(b'ok')

            else:
                super().do_POST()
        except Exception as e:
            send_json(self, 500, {'error':'服务器内部错误'})

if __name__ == '__main__':
    if not os.path.exists(os.path.join(BASE_DIR, 'ffprobe.exe')):
        print('⚠️ 警告：未找到 ffprobe.exe，音频信息将无法获取。')
    if os.path.exists('error_log.txt'):
        try:
            os.remove('error_log.txt')
            print('🗑️ 已自动清除上一次的错误日志')
        except PermissionError:
            try:
                open('error_log.txt', 'w').close()
            except:
                pass
    print('🚀 服务器启动: http://localhost:8000')
    HTTPServer(('', 8000), Handler).serve_forever()