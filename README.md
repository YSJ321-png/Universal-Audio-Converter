# 🎵 万能音频转换器

基于 Python + FFmpeg 开发的浏览器本地音频转换工具，支持NCM网易云音乐加密文件解密、二十余种音频格式互转、独立编码器切换，自带用户反馈后台管理，全程本地运行，无需外网服务器中转。

## ✨ 主要功能

| 功能 | 说明 |
|------|------|
| 🔓 NCM解密 | 内置原生解密算法+ncmdump第三方工具，支持自动适配、内置解密、ncmdump专用三种模式 |
| 🎧 全格式互转 | MP3、FLAC、AAC、WAV、OGG、ALAC、AIFF、APE、WV、TTA、WMA、Opus、AMR、Speex、RealAudio、AC-3、DTS、AU、M4A、CAF、PCM、WebM等共计28种格式 |
| 📊 音频参数解析 | 实时读取音频时长、采样率、声道数量、位深度、动态范围参数 |
| ⚙️ 双编码引擎 | FFmpeg通用引擎、独立编码器（LAME、FLAC、oggenc2、opusenc、Nero AAC）自由切换 |
| 💬 用户反馈留言 | 用户提交问题建议，管理员后台在线回复、标记已处理 |
| 🔐 加密管理后台 | Bearer令牌验证登录，可查看反馈、回复内容、清空系统错误日志 |
| 📥 一键批处理启动 | 双击批处理文件自动启动服务，自动跳转浏览器访问页面 |
| 📖 使用教程页面 | 提供音频文件获取、合规使用相关指引 |
| 🗑️ 自动错误日志 | 程序异常自动记录日志，附带给豆包的参考提问模板 |

## 🚀 快速上手

### 1. 获取FFmpeg组件
前往gyan.dev下载FFmpeg完整版，解压后把 `ffmpeg.exe`、`ffprobe.exe` 放到项目根文件夹内。

### 2. 安装Python依赖库
```bash
pip install pycryptodome ncmdump
 
 
3. 运行程序
 
直接双击  启动服务器.bat  批处理文件，程序会自动启动后端服务，并自动打开转换网页。
也可以手动终端运行：  python server.py 
 
⚠️ 重要提醒
请勿修改任何文件原始名称，所有程序、网页、工具必须存放在同一个文件夹内。
 
项目目录结构
 
plaintext
  
万能音频转换器/
├── converter.html      中文版转换页面
├── converter_en.html   英文版转换页面
├── server.py           Python后端服务程序
├── admin.html          管理员后台页面
├── history.html        反馈历史页面
├── guide.html          使用教程页面
├── 启动服务器.bat      一键启动脚本
├── 重启服务器.bat      服务重启脚本
├── ffmpeg.exe          FFmpeg转码核心程序
├── ffprobe.exe         音频信息分析工具
└── README.md           使用说明文档
 
 
独立编码器下载地址
 
程序名 对应格式 官方下载地址 
lame.exe MP3 https://lame.sourceforge.io/ 
flac.exe FLAC无损 https://xiph.org/flac/download.html 
oggenc2.exe OGG格式 https://www.rarewares.org/ogg-oggenc.php 
opusenc.exe Opus格式 https://opus-codec.org/downloads/ 
neroAacEnc.exe AAC格式 https://ftp6.nero.com/tools/NeroAACCodec-1.5.1.zip 
 
开源协议
 
MIT License
 
🙏致谢名单
 
FFmpeg：音视频编码核心底层组件
ncmdump：网易云NCM文件解密工具
LAME、FLAC、oggenc2、opusenc：独立音频编码器
DeepSeek：协助完成整体程序搭建
豆包：提供全套安全加固方案、代码优化修改思路
