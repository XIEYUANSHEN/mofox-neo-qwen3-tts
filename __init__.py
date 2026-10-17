"""qwen3_tts —— Qwen3-TTS 语音插件。

注意：这里**不要** re-export 插件类。框架会自己从 manifest 的 entry_point
加载 plugin.py；在 __init__.py 里 import plugin 会造成加载期循环依赖
（框架的 src.app.plugin_system.* 尚未就绪）→ 报 "cannot import name"。
参考同项目其它插件：server_ops/__init__.py 为空，skill_manager 只放元信息。
"""