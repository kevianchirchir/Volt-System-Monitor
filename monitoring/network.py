import psutil
import time


class NetworkMonitor:
    def __init__(self):
        pass
    
    def get_bytes_sent(self):
        return psutil.net_io_counters().bytes_sent
    
    def get_bytes_receieved(self):
        return psutil.net_io_counters().bytes_recv
    
    def get_upload_speed(self, previous_sent_bytes,  previous_time):
        return ((self.get_bytes_sent() - previous_sent_bytes) / (time.time() - previous_time) ) / (1024**2)
   
    def get_download_speed(self, previous_received, previous_time):
        return ((self.get_bytes_receieved() - previous_received) / (time.time() - previous_time)) / (1024**2)
    
    def get_download_speed_kbs(self, previous_received, previous_time):
        return ((self.get_bytes_receieved() - previous_received) / (time.time() - previous_time)) / 1024
