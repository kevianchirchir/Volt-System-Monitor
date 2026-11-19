import platform
import pynvml 

class hardware_detection:
    def __init__(self):
        pass
    
    def get_cpu_name(self):
       return platform.processor
   
    def get_gpu_name(self):
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8")
        return gpu_name