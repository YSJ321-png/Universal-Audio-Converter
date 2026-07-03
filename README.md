# 🎵 万能音频转换器

一个基于 Python + FFmpeg 的浏览器端音频格式转换工具，支持 **NCM 解密**、**28 种输出格式**、**独立编码器备选**、**反馈系统**，纯本地运行，无需联网。

---

## ✨ 主要功能

| 功能 | 说明 |
|------|------|
| 🔓 NCM 解密 | 内置算法 + ncmdump 模块，三种模式可选（自动/内置/ncmdump） |
| 🎧 28 种输出格式 | MP3、FLAC、AAC、WAV、OGG、ALAC、AIFF、APE、WV、TTA、WMA、Opus、AMR、Speex、RealAudio、AC-3、DTS、AU、M4A、CAF、PCM、WebM 等 |
| 📊 音频信息显示 | 时长、采样率、声道、位深、动态范围 |
| ⚙️ 独立编码器备选 | LAME (MP3)、FLAC、oggenc2 (OGG)、opusenc (Opus)、Nero AAC (AAC) |
| 💬 反馈系统 | 用户提交反馈 → 管理员回复 → 历史查看 |
| 🔐 管理员页面 | 密码保护，支持回复、关闭对话、查看错误日志 |
| 📥 一键启动 | 双击 BAT 文件自动启动服务器并打开浏览器 |
| 📖 教程页面 | 内置音频获取指南（F12抓取、官方转换等） |
| 🗑️ 错误日志 | 自动记录，含 DeepSeek 提问建议 |

---

## 🚀 快速开始

### 1. 下载 FFmpeg
从 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip) 下载 FFmpeg，解压后将 `ffmpeg.exe` 和 `ffprobe.exe` 放入项目目录。

### 2. 安装 Python 依赖
```bash
### 3. pip install pycryptodome ncmdump
 启动服务器
在终端执行python server.py或者打开文件里的启动服务器.bat
### 4.打开浏览器
 访问localhost:8000/converter.html(其实打开文件里的启动服务器.bat就可以了）
一定注意！！！！！！！
不要改文件名，并且一定要在一个文件夹
项目结构
万能音频转换器/
├── converter.html      # 前端页面
├── server.py           # 后端服务
├── admin.html          # 管理员页面
├── history.html        # 历史回复页面
├── guide.html          # 教程页面
├── 启动服务器.bat      # 一键启动
├── 重启服务器.bat      # 重启脚本
├── ffmpeg.exe          # FFmpeg 引擎（需自行下载）
├── ffprobe.exe         # 音频分析（需自行下载）
└── README.md           # 本文件
编码器下载
编码器 格式 下载
lame.exe MP3 https://lame.sourceforge.io/
flac.exe FLAC https://xiph.org/flac/download.html
oggenc2.exe OGG https://www.rarewares.org/ogg-oggenc.php
opusenc.exe Opus https://opus-codec.org/downloads/
neroAacEnc.exe AAC https://ftp6.nero.com/tools/NeroAACCodec-1.5.1.zip
许可证：MIT License
🙏致谢
FFmpeg－核心编码引擎
ncmdump -NCM 解密模块
lame-MP3编码器
flac -FLAC 编码器
DeepSeek 制作全过程
