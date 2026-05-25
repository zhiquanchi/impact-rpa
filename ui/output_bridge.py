"""控制台输出中间层：将 Rich Console、loguru、stdout/stderr 统一到单一回调。"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from typing import IO, cast

from loguru import logger
from rich.console import Console

LogEmitter = Callable[[str, str], None]


def infer_log_level(message: str) -> str:
    lowered = message.lower()
    if any(
        token in lowered for token in ("失败", "异常", "错误", "[err]", "traceback")
    ):
        return "error"
    if any(
        token in lowered
        for token in ("警告", "超时", "跳过", "停止请求", "[skip]", "warn")
    ):
        return "warn"
    if any(token in lowered for token in ("完成", "成功", "[ok]", "✓")):
        return "success"
    if any(token in lowered for token in ("开始", "准备", "目标", "处理中")):
        return "highlight"
    return "info"


class QtLogStream(io.TextIOBase):
    """将 write/flush 按行转发到 emit 回调。"""

    def __init__(self, emit_line: Callable[[str], None]):
        super().__init__()
        self._emit_line = emit_line
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text.replace("\r", "")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self._emit_line(line)
        return len(text)

    def flush(self) -> None:
        pending = self._buffer.strip()
        if pending:
            self._emit_line(pending)
        self._buffer = ""

    def isatty(self) -> bool:
        return False


class ConsoleLoggerAdapter:
    """为 BrowserManager 等组件提供 loguru 风格的 info/warning/error 接口。"""

    def __init__(self, bridge: OutputBridge):
        self._bridge = bridge

    def info(self, message: str) -> None:
        self._bridge.emit(message, "info")

    def warning(self, message: str) -> None:
        self._bridge.emit(message, "warn")

    def error(self, message: str) -> None:
        self._bridge.emit(message, "error")

    def debug(self, message: str) -> None:
        self._bridge.emit(message, "info")


class OutputBridge:
    """统一输出路由：Rich Console、loguru、标准流均通过 emit 回调落地。"""

    _LOGURU_LEVEL_MAP = {
        "TRACE": "info",
        "DEBUG": "info",
        "INFO": "info",
        "SUCCESS": "success",
        "WARNING": "warn",
        "ERROR": "error",
        "CRITICAL": "error",
    }

    def __init__(self, emit: LogEmitter):
        self._emit = emit
        self._shared_console: Console | None = None
        self._loguru_handler_id: int | None = None
        self._orig_stdout: IO[str] | None = None
        self._orig_stderr: IO[str] | None = None
        self._stdout_stream: QtLogStream | None = None
        self._stderr_stream: QtLogStream | None = None

    @classmethod
    def for_terminal(cls, console: Console | None = None) -> OutputBridge:
        terminal = console or Console()

        def emit(message: str, level: str) -> None:
            terminal.print(message)

        bridge = cls(emit)
        bridge._shared_console = terminal
        return bridge

    @classmethod
    def for_callback(cls, callback: Callable[[str, str], None]) -> OutputBridge:
        return cls(callback)

    def emit(self, message: str, level: str | None = None) -> None:
        resolved = level or infer_log_level(message)
        self._emit(message, resolved)

    def emit_line(self, message: str, level: str | None = None) -> None:
        self.emit(message, level)

    def create_console(self, width: int = 120) -> Console:
        if self._shared_console is not None:
            return self._shared_console
        stream = QtLogStream(lambda line: self.emit_line(line))
        return Console(
            file=cast(IO[str], stream),
            force_terminal=False,
            color_system=None,
            width=width,
        )

    def create_logger(self) -> ConsoleLoggerAdapter:
        return ConsoleLoggerAdapter(self)

    def install_loguru_sink(self, level: str = "DEBUG") -> int:
        if self._loguru_handler_id is not None:
            return self._loguru_handler_id

        bridge = self

        def sink(message) -> None:
            record = message.record
            text = str(message).rstrip("\n")
            log_level = bridge._LOGURU_LEVEL_MAP.get(record["level"].name, "info")
            bridge.emit(text, log_level)

        self._loguru_handler_id = logger.add(sink, format="{message}", level=level)
        return self._loguru_handler_id

    def uninstall_loguru_sink(self) -> None:
        if self._loguru_handler_id is not None:
            logger.remove(self._loguru_handler_id)
            self._loguru_handler_id = None

    def install_stdio_redirect(self) -> None:
        if self._orig_stdout is not None:
            return
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._stdout_stream = QtLogStream(lambda line: self.emit_line(line))
        self._stderr_stream = QtLogStream(
            lambda line: self.emit_line(line, "error")
        )
        sys.stdout = cast(IO[str], self._stdout_stream)
        sys.stderr = cast(IO[str], self._stderr_stream)

    def uninstall_stdio_redirect(self) -> None:
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
        self._orig_stdout = None
        self._orig_stderr = None
        self._stdout_stream = None
        self._stderr_stream = None

    def flush_stdio(self) -> None:
        if self._stdout_stream is not None:
            self._stdout_stream.flush()
        if self._stderr_stream is not None:
            self._stderr_stream.flush()

    def scoped_redirect(self):
        return _OutputRedirectContext(self)


class _OutputRedirectContext:
    def __init__(self, bridge: OutputBridge):
        self._bridge = bridge

    def __enter__(self) -> OutputBridge:
        self._bridge.install_stdio_redirect()
        return self._bridge

    def __exit__(self, exc_type, exc, tb) -> None:
        self._bridge.flush_stdio()
        self._bridge.uninstall_stdio_redirect()
