import pynvml 
class GPUMonitor:
    def __init__(self):
        pynvml.nvmlInit()
        self.gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    

    def get_gpu_usage(self):
        return pynvml.nvmlDeviceGetUtilizationRates(self.gpu).gpu
    
    def get_gpu_temperature(self):
        return pynvml.nvmlDeviceGetTemperature(self.gpu,  pynvml.NVML_TEMPERATURE_GPU)
    
    def get_gpu_memory(self):
        return pynvml.nvmlDeviceGetMemoryInfo(self.gpu)
    
    
game = GPUMonitor()

print(game.get_gpu_usage())
print(game.get_gpu_temperature())
print(game.get_gpu_memory().total / 1048576)

