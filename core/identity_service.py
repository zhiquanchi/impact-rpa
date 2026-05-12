import hashlib
import uuid

def get_machine_uid() -> str:
    """
    获取机器唯一标识并哈希化。
    结合网卡 MAC 地址生成哈希，确保在同一台机器上结果一致且不可逆。
    """
    node = uuid.getnode()
    # 使用 sha256 增加安全性，防止原始 MAC 地址泄露
    return hashlib.sha256(str(node).encode()).hexdigest()
