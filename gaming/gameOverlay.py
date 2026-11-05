import customtkinter as ctk

class GameOverlay(ctk.CTkToplevel):

    def __init__(self, master):
        super().__init__(master)

        self.geometry("280x180+20+20")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.90)

        self.configure(fg_color="#0B1120")