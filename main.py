import psutil
import time
import os
from system.monitor import SystemMonitor
from system.network import NetworkMonitor
sys = SystemMonitor()
net = NetworkMonitor()
def bytes_to_mb(bytes):
    return bytes / 1024**2



def print_statistics(previous_sent_bytes, previous_time, previous_received):
    data_sent = net.get_bytes_sent()
    data_received = net.get_bytes_receieved()
    dashboard = (
        f"""
================================
SYSTEM MONITOR
================================
    
CPU USAGE:  {sys.get_cpu_usage()}%
RAM USAGE:  {sys.get_memory_usage()}%
DISK USAGE: {sys.get_disk_usage()}%


NETWORK
DATA SENT:     {bytes_to_mb(data_sent):.1f} MB
DATA RECEIVED: {bytes_to_mb(data_received):.1f} MB
UPLOAD SPEED: {net.get_upload_speed(previous_sent_bytes,  previous_time):.2f} MB/s
DOWNLOAD SPEED: {net.get_download_speed(previous_received, previous_time):.2f} MB/s
================================"""
    )
    return dashboard, time.time(), data_sent, data_received




while True:
    os.system("cls")
    dashboard, previous_time, previous_sent_bytes, previous_received = print_statistics(previous_sent_bytes, previous_time, previous_received)
    print(dashboard)
    time.sleep(2)
