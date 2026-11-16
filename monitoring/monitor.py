import psutil
class SystemMonitor:
    def __init__(self):
        pass
    
    def get_cpu_usage(self):
        return psutil.cpu_percent(interval=0.1)
    
    def get_memory_usage(self):
        return psutil.virtual_memory().percent
    
    def get_disk_usage(self):
        return psutil.disk_usage("C:\\").percent
    
    def get_total_memory(self):
        return psutil.virtual_memory().total
    
    def get_cpu_frequency(self):
        return psutil.cpu_freq()

    def get_core_count(self):
        return psutil.cpu_count()
     
print(psutil.sensors_)