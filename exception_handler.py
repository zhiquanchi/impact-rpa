"""
异常日志记录类
用于记录异常情况到文件，并为后续的飞书通知做准备
"""

import json
import os
import traceback
from datetime import datetime
from typing import Any

from loguru import logger


class ExceptionHandler:
    """异常处理器，负责记录异常日志并发送通知"""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.dirname(__file__)
        self.log_dir = os.path.join(self.base_dir, 'logs')
        self.exception_log_file = os.path.join(self.log_dir, 'exceptions_{time:YYYY-MM-DD}.log')
        
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
    
    def log_exception(
        self,
        exception: Exception,
        context: dict[str, Any] | None = None,
        send_notification: bool = False,
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
        
        # 构建异常信息
        exception_info = {
            "exception_id": exception_id,
            "timestamp": datetime.now().isoformat(),
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "traceback": traceback.format_exc(),
            "context": context or {}
        }
        
        # 记录到日志文件
        self._write_to_log(exception_info)
        
        # 记录到loguru，使用logger.exception获取详细堆栈
        logger.exception(f"异常发生: {exception_info['exception_type']} - {exception_info['exception_message']}")
        
        # 发送任务异常通知
        if send_notification:
            self._send_exception_notification(exception_info)
        
        return exception_id
    
    def _write_to_log(self, exception_info: dict[str, Any]) -> None:
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
    
    def _send_exception_notification(self, exception_info: dict[str, Any]) -> None:
        try:
            from core.config_manager import ConfigManager
            from core.settings_service import SettingsService
            from notification_service import NotificationService

            config = ConfigManager()
            settings = SettingsService(config).get_snapshot()
            message = (
                f"{exception_info.get('exception_type')}: "
                f"{exception_info.get('exception_message')}"
            )
            NotificationService().notify_proposal_run(
                settings=settings,
                clicked_count=0,
                completed_all=False,
                error_message=message,
            )
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
    
    def get_recent_exceptions(self, count: int = 10) -> list[dict[str, Any]]:
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
