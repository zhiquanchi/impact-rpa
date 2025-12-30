import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from notification_service import NotificationService, NotificationPayload


def main():
    NotificationService().send(
        NotificationPayload(message="测试通知：Impact-RPA 桌面通知正常工作")
    )


if __name__ == "__main__":
    main()

