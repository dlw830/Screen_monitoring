"""
LanScreenMonitor V1 - 网络选择模块 (NetSelector)
自动选择最优局域网 IPv4 地址和可用端口。
支持：有线/无线局域网、Windows 移动热点（无需外网也可用）。
"""

import ipaddress
import logging
import re
import socket
import subprocess
from typing import List, Optional, Set, Tuple

import psutil

from config import APP_NAME, DEFAULT_PORT, PORT_SCAN_TRIES

logger = logging.getLogger(APP_NAME)

# Windows 移动热点默认网段
_HOTSPOT_SUBNET = "192.168.137."


def _is_usable_private_ipv4(addr: str) -> bool:
    """
    检查是否为可用的 RFC1918 私有地址。
    排除 127.0.0.1 和 169.254.x.x（链路本地/APIPA）。
    """
    try:
        ip = ipaddress.IPv4Address(addr)
        if not ip.is_private:
            return False
        if ip == ipaddress.IPv4Address("127.0.0.1"):
            return False
        # 排除链路本地地址 169.254.0.0/16（网卡未获取 DHCP 时的自动 IP）
        if ip.is_link_local:
            return False
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def _subnet_score(addr: str) -> int:
    """根据网段打分，192.168 > 10 > 172.16/12。"""
    if addr.startswith("192.168"):
        return 0
    if addr.startswith("10."):
        return 1
    if addr.startswith("172."):
        return 2
    return 99


def _is_hotspot_ip(addr: str) -> bool:
    """判断是否为 Windows 移动热点 IP（通常 192.168.137.1）。"""
    return addr.startswith(_HOTSPOT_SUBNET)


def _is_hotspot_nic(nic_name: str) -> bool:
    """
    判断网卡是否为 Windows 移动热点适配器。
    常见名称：
    - 中文：「本地连接* 10」
    - 英文：「Local Area Connection* 10」
    - 底层：「Microsoft Wi-Fi Direct Virtual Adapter」
    """
    name_lower = nic_name.lower()
    # "本地连接*" 是 Windows 热点适配器的典型名称格式
    if "本地连接*" in nic_name or "本地连接 *" in nic_name:
        return True
    if "local area connection*" in name_lower or "local area connection *" in name_lower:
        return True
    if "wi-fi direct" in name_lower:
        return True
    return False


def _nic_type_score(nic_name: str, ip: str = "") -> int:
    """
    根据网卡名称和 IP 推断类型并打分（越小越优先）。
    热点适配器得分 5（仅次于以太网），确保在无外网时被优先选择。
    """
    name_lower = nic_name.lower()

    # 虚拟网卡关键字（排除热点适配器）
    virtual_keywords = [
        "vmware", "virtualbox", "vethernet", "hyper-v",
        "docker", "veth", "virbr", "wsl", "loopback",
    ]
    for kw in virtual_keywords:
        if kw in name_lower:
            return 100

    # Windows 移动热点适配器（通过名称或 IP 识别）
    if _is_hotspot_nic(nic_name) or _is_hotspot_ip(ip):
        return 5

    # 以太网关键字
    eth_keywords = ["ethernet", "以太网", "eth", "enp", "eno"]
    for kw in eth_keywords:
        if kw in name_lower:
            return 0

    # Wi‑Fi 关键字
    wifi_keywords = ["wi-fi", "wifi", "wlan", "wl", "无线"]
    for kw in wifi_keywords:
        if kw in name_lower:
            return 10

    return 50  # 未知类型


def _get_gateway_nics() -> Set[str]:
    """
    获取实际拥有默认网关的网卡名称集合。
    通过解析 Windows 'route print' 命令获取准确的网关信息，
    而非简单假设所有 UP 状态的网卡都有网关。
    """
    result: Set[str] = set()
    try:
        # 运行 route print 获取路由表
        output = subprocess.check_output(
            ["route", "print", "0.0.0.0"],
            timeout=5,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000,
        ).decode("gbk", errors="replace")

        # 提取默认路由的网关 IP 和接口 IP
        # 格式: 网络目标   网络掩码   网关         接口          跃点数
        #        0.0.0.0    0.0.0.0    192.168.1.1  192.168.1.100  25
        gateway_ips: Set[str] = set()
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                interface_ip = parts[3]
                gateway_ips.add(interface_ip)

        if gateway_ips:
            # 将接口 IP 映射回网卡名称
            addrs = psutil.net_if_addrs()
            for nic_name, addr_list in addrs.items():
                for snic in addr_list:
                    if snic.family == socket.AF_INET and snic.address in gateway_ips:
                        result.add(nic_name)
                        break

        if result:
            logger.debug(f"拥有默认网关的网卡: {result}")
        else:
            logger.debug("未检测到拥有默认网关的网卡（可能未连接外网）")

    except Exception as e:
        logger.debug(f"查询路由表失败: {e}，将使用备用策略")

    return result


class NetSelector:
    """网络选择器：自动选最佳局域网 IP 与可用端口。"""

    @staticmethod
    def select_best_ipv4() -> str:
        """
        选择最优局域网 IPv4 地址。
        优先级：有网关的以太网 > 有网关的 Wi-Fi > 热点适配器 > 其他。
        当仅有热点可用（无外网）时，自动选择热点 IP。
        返回一个 IP 字符串；如果找不到任何合适地址，返回 '127.0.0.1'。
        """
        candidates: List[Tuple[int, int, str, str]] = []

        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        gateway_nics = _get_gateway_nics()

        for nic_name, addr_list in addrs.items():
            stat = stats.get(nic_name)
            if stat is None or not stat.isup:
                continue

            for snic in addr_list:
                if snic.family != socket.AF_INET:
                    continue

                ip = snic.address
                if not _is_usable_private_ipv4(ip):
                    continue

                nic_score = _nic_type_score(nic_name, ip)

                # 有默认网关的网卡额外加分（降低 score 值）
                if nic_name in gateway_nics:
                    nic_score -= 50

                s_score = _subnet_score(ip)
                candidates.append((nic_score, s_score, ip, nic_name))
                logger.debug(
                    f"候选 IP: {ip} (网卡: {nic_name}, "
                    f"nic_score={nic_score}, subnet_score={s_score}, "
                    f"hotspot={'是' if _is_hotspot_nic(nic_name) or _is_hotspot_ip(ip) else '否'}, "
                    f"gateway={'是' if nic_name in gateway_nics else '否'})"
                )

        if not candidates:
            logger.warning("未找到可用局域网 IPv4 地址，使用 127.0.0.1")
            return "127.0.0.1"

        candidates.sort(key=lambda c: (c[0], c[1]))

        best_ip = candidates[0][2]
        best_nic = candidates[0][3]
        is_hotspot = _is_hotspot_nic(best_nic) or _is_hotspot_ip(best_ip)

        logger.info(
            f"选择最佳 IP: {best_ip} (网卡: {best_nic}"
            f"{', 热点模式' if is_hotspot else ''})"
        )

        if len(candidates) > 1:
            alt = ", ".join(f"{c[2]} ({c[3]})" for c in candidates[1:])
            logger.info(f"备用 IP 列表: {alt}")

        return best_ip

    @staticmethod
    def bind_available_port(start: int = DEFAULT_PORT, tries: int = PORT_SCAN_TRIES) -> int:
        """
        从 start 开始尝试绑定端口，成功后返回端口号。
        最多尝试 tries 次，若全部失败则抛出 RuntimeError。
        """
        for offset in range(tries):
            port = start + offset
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("0.0.0.0", port))
                    logger.info(f"端口 {port} 可用")
                    return port
            except OSError:
                logger.debug(f"端口 {port} 被占用，继续尝试")
                continue

        raise RuntimeError(
            f"无法在 {start}-{start + tries - 1} 范围内找到可用端口。"
            f"请检查是否有其他程序占用了这些端口。"
        )
