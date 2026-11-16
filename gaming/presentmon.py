import psutil
import time
import os
game_processes = [
    # Competitive shooters
    "VALORANT-Win64-Shipping.exe",
    "cs2.exe",
    "FortniteClient-Win64-Shipping.exe",
    "Overwatch.exe",
    "RainbowSix.exe",
    "r5apex.exe",
    "cod.exe",

    # Sandbox / survival
    "RobloxPlayerBeta.exe",
    "Minecraft.Windows.exe",
    "javaw.exe",
    "RustClient.exe",
    "DayZ_x64.exe",
    "Palworld-Win64-Shipping.exe",

    # Open world / action
    "GTA5.exe",
    "Cyberpunk2077.exe",
    "eldenring.exe",
    "witcher3.exe",
    "ACValhalla.exe",
    "RDR2.exe",

    # Other popular games
    "RocketLeague.exe",
    "League of Legends.exe",
    "DeadByDaylight-Win64-Shipping.exe",
    "Terraria.exe",
    "Among Us.exe",
    "Lethal Company.exe",
    "Phasmophobia.exe",
    "FallGuys_client_game.exe",
    "HogwartsLegacy.exe"
]
game_processes = [game.lower() for game in game_processes]

def get_running_games():
    running_games = []
    for process in psutil.process_iter(['pid', 'name']):
        try:
            if process.info['name'].lower() in game_processes:
               running_games.append(process.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return running_games

def display_games(games):
    count = len(games)
    print(f"Games Detected: {count}")
    for game in games:
        if games:
            print(f"""   
    - {(game['name'])} (PID: {(game['pid'])})""")
    print("\nNext scan in 3 seconds...")
       
def monitor_games():
   
    while True:
        print("""
================================
REVOLT GAME MONITOR
================================""")
        games = get_running_games()
        if not games:
              print("""                                  
            No games currently running.""")
        else:
            display_games(games)
        time.sleep(3)
        os.system("cls")
   
monitor_games()
