import psutil
class SystemMonitor:
    def __init__(self):
        pass
    
    def get_cpu_usage(self):
        return psutil.cpu_percent(interval=0)
    
    def get_memory_usage(self):
        return psutil.virtual_memory().percent
    
    def get_disk_usage(self):
        return psutil.disk_usage("C:\\").percent
    
    

     