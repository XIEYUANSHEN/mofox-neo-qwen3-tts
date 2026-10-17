# Qwen3 语音合成（qwen3_tts）

基于 [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 本地服务的 MoFox Neo 语音合成插件。
调用本地 TTS sidecar 将文本转为语音消息发送，支持自定义参考音色与接口鉴权。

## 功能

- 调用本地 Qwen3-TTS 服务合成语音，以语音消息发出
- 支持自定义参考音色（ref_wav + ref_text）复刻任意声音
- 文本清洗：去除 markdown / emoji / 重复标点，超长按标点智能截断
- 可选 ffmpeg 转 mp3（适配不支持 wav 的平台）
- 私聊 / 群聊门控、冷却防刷、失败补发文字

## 前置条件

1. **Qwen3-TTS sidecar** — 本地运行 Qwen3-TTS 推理服务，默认监听 `http://127.0.0.1:8897/synthesize`
2. **ffmpeg**（可选）— 仅在 `send.transcode_mp3=true` 时需要
3. **MoFox Neo 核心** — 版本 ≥ `1.2.0-rc.2`

## 安装

将本插件放入 MoFox Neo 的插件目录，或在插件市场搜索 `qwen3_tts` 安装。

## 配置

插件配置分四个 section：

### `plugin` — 插件行为

| 字段 | 默认 | 说明 |
|------|------|------|
| `enabled` | `true` | 是否启用 |
| `allow_group` | `false` | 是否允许群聊发语音 |
| `max_chars` | `120` | 单次最大字数（超出按标点截断） |
| `min_chars` | `2` | 低于此长度不合成 |
| `cooldown_s` | `8` | 两次语音最小间隔（秒） |
| `out_dir` | `/tmp/qwen3_tts` | 音频临时输出目录 |
| `keep_files` | `false` | 是否保留音频文件 |
| `keep_on_fail` | `true` | 失败时是否保留音频 |

### `tts` — TTS 服务连接

| 字段 | 默认 | 说明 |
|------|------|------|
| `endpoint` | `http://127.0.0.1:8897/synthesize` | 合成接口地址 |
| `token` | `""` | 鉴权 token（X-TTS-Token），留空不鉴权 |
| `timeout` | `180` | 请求超时（秒） |

### `voice` — 音色

| 字段 | 默认 | 说明 |
|------|------|------|
| `ref_wav` | `""` | 参考音频绝对路径，留空=服务默认音色 |
| `ref_text` | `""` | 参考音频对应文本 |
| `language` | `"Chinese"` | 合成语言 |

### `send` — 发送行为

| 字段 | 默认 | 说明 |
|------|------|------|
| `transcode_mp3` | `false` | 发送前用 ffmpeg 转 mp3 |
| `ffmpeg_path` | `"ffmpeg"` | ffmpeg 路径 |
| `fallback_text` | `""` | 语音失败时补发的文字前缀 |

## Action

### `say_voice`

用配置的音色说一句话，以语音消息发出。

- **调用名**：`action-say_voice`
- **ChatType**：PRIVATE（群聊需 `allow_group=true`）
- **参数**：`content`（str）— 要合成的文本，一句话，≤120 字

> 合成一次约十几秒，请勿频繁调用；一次只放一句话，不要塞长段落。

## 自定义音色示例

以「昔涟」音色为例（需自备参考音频）：

```yaml
voice:
  ref_wav: "/path/to/xilian_ref.wav"
  ref_text: "参考音频对应的文本内容"
  language: "Chinese"
```

> `ref_wav` 指向一段 5~15 秒的干净人声录音，`ref_text` 是这段录音的文字内容。
> 服务端会据此复刻该音色。留空则使用服务端默认音色。

## 目录结构

```
qwen3_tts/
├── manifest.json          # 插件清单
├── plugin.py              # 插件入口
├── config.py              # 配置定义
├── tts_client.py          # TTS HTTP 客户端
├── actions/
│   ├── __init__.py
│   └── say.py             # say_voice action
└── tests/
    └── test_say.py
```

## License

MIT
