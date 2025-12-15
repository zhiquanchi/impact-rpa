"""
异常日志记录类
用于记录异常情况到文件，并为后续的飞书通知做准备
"""

import os
import json
import traceback
import inspect
import platform
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger


class ExceptionHandler:
    """异常处理器，负责记录异常日志并发送通知"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(__file__)
        self.log_dir = os.path.join(self.base_dir, 'logs')
        self.exception_log_file = os.path.join(self.log_dir, 'exceptions_{time:YYYY-MM-DD}.log')
        
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
    
    def log_exception(
        self, 
        exception: Exception, 
        context: Optional[Dict[str, Any]] = None,
        send_notification: bool = False
    ) -> str:
        """
        记录异常到日志文件
        
        Args:
            exception: 异常对象
            context: 异常上下文信息
            send_notification: 是否发送通知（预留接口）
            
        Returns:
            异常日志ID
        """
        # 生成异常ID
        exception_id = f"EXC_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 调用点信息（尽量指向业务调用处，而非异常处理器本身）
        caller = None
        try:
            # stack[0] 是当前帧，stack[1] 通常是调用 log_exception 的位置
            stack = inspect.stack()
            if len(stack) > 1:
                frame = stack[1]
                caller = {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.function,
                }
        except Exception:
            caller = None

        # 运行环境信息（排查环境差异、编码/路径等问题时很有用）
        runtime = {
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        }

        def _safe(obj: Any):
            """将任意对象转换为可 JSON 序列化的结构，尽量保留信息。"""
            try:
                json.dumps(obj)
                return obj
            except Exception:
                # dict
                if isinstance(obj, dict):
                    return {str(k): _safe(v) for k, v in obj.items()}
                # list/tuple/set
                if isinstance(obj, (list, tuple, set)):
                    return [_safe(v) for v in obj]
                # fallback
                try:
                    return repr(obj)
                except Exception:
                    return "<unserializable>"

        safe_context = _safe(context or {})

        # 更可靠的堆栈：traceback.format_exc() 依赖“当前正在抛出的异常”，
        # 这里改为直接使用 exception.__traceback__。
        tb = None
        try:
            tb = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        except Exception:
            tb = traceback.format_exc()
        
        # 构建异常信息
        exception_info = {
            "exception_id": exception_id,
            "timestamp": datetime.now().isoformat(),
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "traceback": tb,
            "caller": caller,
            "runtime": runtime,
            "context": safe_context,
        }
        
        # 记录到日志文件
        self._write_to_log(exception_info)
        
        # 记录到loguru，使用logger.exception获取详细堆栈
        logger.exception(f"异常发生: {exception_info['exception_type']} - {exception_info['exception_message']}")
        
        # 预留飞书通知接口
        if send_notification:
            self._send_feishu_notification(exception_info)
        
        return exception_id
    
    def _write_to_log(self, exception_info: Dict[str, Any]):
        """写入异常到日志文件"""
        log_file = os.path.join(
            self.log_dir, 
            f"exceptions_{datetime.now().strftime('%Y-%m-%d')}.log"
        )
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(exception_info, ensure_ascii=False, indent=2) + '\n')
                f.write('-' * 80 + '\n')
        except Exception as e:
            logger.error(f"写入异常日志失败: {e}")
    
    def _send_feishu_notification(self, exception_info: Dict[str, Any]):
        """
        发送飞书通知（预留接口）
        
        Args:
            exception_info: 异常信息字典
        """
        # TODO: 实现飞书通知功能
        logger.info("飞书通知功能待实现")
        pass
    
    def get_recent_exceptions(self, count: int = 10) -> list:
        """
        获取最近的异常记录
        
        Args:
            count: 返回的异常数量
            
        Returns:
            异常记录列表
        """
        log_file = os.path.join(
            self.log_dir, 
            f"exceptions_{datetime.now().strftime('%Y-%m-%d')}.log"
        )
        
        exceptions = []
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 分割异常记录
                    records = content.split('-' * 80)
                    
                    # 解析JSON记录
                    for record in records:
                        record = record.strip()
                        if record:
                            try:
                                exception_data = json.loads(record)
                                exceptions.append(exception_data)
                            except json.JSONDecodeError:
                                continue
                    
                    # 返回最近的记录
                    exceptions = exceptions[-count:]
        
        except Exception as e:
            logger.error(f"读取异常日志失败: {e}")
        
        return exceptions


# 全局异常处理器实例
exception_handler = ExceptionHandler()