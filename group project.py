from graphics import *
from PIL import Image as PILImage
import json
import time
import os
import random

# --- 1. DATA & CONFIG ---
STARTUP_WARNINGS = []

def load_json(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        message = f"JSON file not found: {filename}"
        print(f"[Startup Warning] {message}")
        STARTUP_WARNINGS.append(message)
        return {}
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON in {filename}: {exc}"
        print(f"[Startup Warning] {message}")
        STARTUP_WARNINGS.append(message)
        return {}
    except OSError as exc:
        message = f"Could not read {filename}: {exc}"
        print(f"[Startup Warning] {message}")
        STARTUP_WARNINGS.append(message)
        return {}

TYPE_DATA_FILE = 'typechart (1).json'
RAW_TYPE_DATA = load_json(TYPE_DATA_FILE)

MOVE_TYPES = {
    "Seismic Toss": "fighting", "Psychic": "psychic", "Psybeam": "psychic", "Hyper Beam": "normal",
    "Ice Beam": "ice", "Thunderbolt": "electric", "Surf": "water", "Blizzard": "ice",
    "Thunder": "electric", "Earthquake": "ground", "Rock Slide": "rock", "Dig": "ground",
    "Slash": "normal", "Mega Drain": "grass", "Explosion": "normal", "Hydro Pump": "water",
    "Swift": "normal", "Tri Attack": "normal", "Wing Attack": "flying", "Leech Life": "bug",
    "Body Slam": "normal", "Solar Beam": "grass", "Razor Leaf": "grass", "Drill Peck": "flying"
}

TYPE_COLORS = {
    "normal": "#A8A878", "fire": "#F08030", "water": "#6890F0", "grass": "#78C850",
    "electric": "#F8D030", "ice": "#98D8D8", "fighting": "#C03028", "poison": "#A040A0",
    "ground": "#E0C068", "flying": "#A890F0", "psychic": "#F85888", "bug": "#A8B820",
    "rock": "#B8A038", "ghost": "#705898", "dragon": "#7038F8"
}

POKEMON_DB = load_json('pokemon_db.json')

# --- 2. HELPERS ---
def get_sprite(anchor, name, is_back=False):
    sprite_base = name.lower()
    candidate_files = (
        [f"back sprites/{sprite_base} (copy).png", f"back sprites/{sprite_base}.png", f"{sprite_base} (copy).png", f"{sprite_base}.png"]
        if is_back else
        [f"front sprites/{sprite_base}.png", f"{sprite_base}.png"]
    )

    filename = next((f for f in candidate_files if os.path.exists(f)), None)
    if not filename:
        return None

    temp_gif = filename.replace(".png", "_temp.gif").replace(" ", "_")
    try:
        if not os.path.exists(temp_gif):
            PILImage.open(filename).convert("RGBA").save(temp_gif, "GIF")
        return Image(anchor, temp_gif)
    except:
        return None

def flicker_sprite(win, sprite):
    for _ in range(3):
        sprite.undraw()
        time.sleep(0.08)
        sprite.draw(win)
        time.sleep(0.08)

def draw_retro_box(win, p1, p2):
    outer = Rectangle(p1, p2)
    outer.setWidth(4); outer.setOutline("black"); outer.setFill("white"); outer.draw(win)
    return outer

def calculate_damage(attacker, defender, move):
    if move.fixed: return move.power, False, 1.0
    a_stat = attacker.att if move.category == "Physical" else attacker.spc
    d_stat = defender.dfn if move.category == "Physical" else defender.spc
    base = ((((2 * attacker.level / 5 + 2) * move.power * a_stat / d_stat) / 50) + 2)
    crit = 2.0 if random.random() < 0.0625 else 1.0
    stab = 1.5 if move.type == attacker.type else 1.0
    t_mult = TYPE_DATA.get(move.type, {}).get(defender.type, 1.0)
    return int(base * crit * stab * t_mult), crit > 1.0, t_mult

def smooth_hp_drop(win, bar, pct_text, start_hp, end_hp, max_hp, x_start, y_top):
    actual_end = max(0, end_hp)
    current_hp = start_hp
    while current_hp > actual_end:
        current_hp -= 1
        if current_hp < actual_end: current_hp = actual_end
        p_val = int((current_hp / max_hp) * 100)
        
        if current_hp <= 0:
            pct_text.setText("FAINTED")
            pct_text.setStyle("bold"); pct_text.setTextColor("red")
        else:
            pct_text.setText(f"{p_val}%")

        bar.undraw()
        bar = Rectangle(Point(x_start, y_top), Point(x_start + (1.8 * p_val), y_top + 10))
        bar.setFill("#2ed573" if p_val > 30 else "#ff4757"); bar.draw(win)
        time.sleep(0.005)
    return bar

# --- 3. CLASSES ---
class Pokemon:
    def __init__(self, name):
        data = POKEMON_DB[name]
        self.name, self.type = name, data["type"]
        self.max_hp = self.current_hp = data["max_hp"]
        self.att, self.dfn, self.spc = data["attack"], data["defense"], data["special"]
        self.level = 50
        self.moves = [Move(m) for m in data["moves"]]

class Move:
    def __init__(self, data):
        self.name = data["name"]
        self.power = data["power"]
        self.category = data["category"]
        self.fixed = data.get("fixed", False)
        self.type = MOVE_TYPES.get(self.name, "normal")

# --- 4. SCREENS ---
def pick_team(win):
    win.setBackground("#2f3542")
    title = Text(Point(400, 35), "SELECT 3 POKÉMON")
    title.setSize(20); title.setStyle("bold"); title.setTextColor("white"); title.draw(win)
    names = list(POKEMON_DB.keys())
    buttons, selected = [], []
    for i, name in enumerate(names):
        col, row = i % 6, i // 6
        x, y = 75 + (col * 130), 125 + (row * 155)
        r = Rectangle(Point(x-60, y-70), Point(x+60, y+70))
        r.setFill(TYPE_COLORS.get(POKEMON_DB[name]["type"], "white"))
        r.setOutline("white"); r.draw(win); buttons.append(r)
        img = get_sprite(Point(x, y-10), name)
        if img: img.draw(win)
        lbl = Text(Point(x, y+55), name.upper())
        lbl.setSize(8); lbl.setStyle("bold"); lbl.draw(win)
    while len(selected) < 3:
        click = win.getMouse()
        for i, btn in enumerate(buttons):
            p1, p2 = btn.getP1(), btn.getP2()
            if p1.getX() < click.getX() < p2.getX() and p1.getY() < click.getY() < p2.getY():
                if i not in selected:
                    selected.append(i); btn.setOutline("#2ed573"); btn.setWidth(5)
    for item in win.items[:]: item.undraw()
    return [Pokemon(names[idx]) for idx in selected]

def choose_valid_switch(win, team, current_idx, btns):
    click = win.getMouse()
    for i, b in enumerate(btns):
        if b.getP1().getX() < click.getX() < b.getP2().getX() and b.getP1().getY() < click.getY() < b.getP2().getY():
            if team[i].current_hp <= 0 or i == current_idx:
                invalid_msg = "You can't switch to that Pokémon!"
                if team[i].current_hp <= 0:
                    invalid_msg = f"{team[i].name.upper()} has fainted!"
                elif i == current_idx:
                    invalid_msg = f"{team[i].name.upper()} is already out!"
                warn = Text(Point(400, 495), invalid_msg)
                warn.setStyle("bold")
                warn.setTextColor("red")
                warn.draw(win)
                time.sleep(0.8)
                warn.undraw()
                return choose_valid_switch(win, team, current_idx, btns)
            return i
    return choose_valid_switch(win, team, current_idx, btns)

def switch_menu(win, team, current_idx):
    box = draw_retro_box(win, Point(100, 80), Point(700, 520))
    txt = Text(Point(400, 110), "BRING OUT WHICH POKÉMON?"); txt.setStyle("bold"); txt.draw(win)
    btns, labels = [], []
    for i, p in enumerate(team):
        y_off = 160 + (i * 100)
        r = Rectangle(Point(150, y_off), Point(650, y_off+80))
        color = "#ffffff" if p.current_hp > 0 else "#bdc3c7"
        if i == current_idx: color = "#dfe6e9"
        r.setFill(color); r.draw(win); btns.append(r)
        hp_p = int((max(0, p.current_hp)/p.max_hp)*100)
        label_str = f"{p.name.upper()} - FAINTED" if p.current_hp <= 0 else f"{p.name.upper()} - {hp_p}% HP"
        l = Text(Point(400, y_off+40), label_str); l.setStyle("bold"); l.draw(win); labels.append(l)
    new_idx = choose_valid_switch(win, team, current_idx, btns)
    for item in [box, txt] + btns + labels: item.undraw()
    return new_idx

# --- 5. MAIN ---
def main():
    win = GraphWin("Pokémon Battle", 800, 600)
    player_team = pick_team(win)
    enemy_team = [Pokemon(name) for name in random.sample(list(POKEMON_DB.keys()), 3)]
    p_idx, e_idx = 0, 0
    
    try:
        bg_pil = PILImage.open("background.webp").resize((800, 600))
        bg_pil.save("battle_bg_temp.gif", "GIF")
        background = Image(Point(400, 300), "battle_bg_temp.gif")
        background.draw(win)
    except:
        win.setBackground("white")

    msg_box = draw_retro_box(win, Point(10, 410), Point(450, 590))
    act_box = draw_retro_box(win, Point(460, 410), Point(790, 590))
    startup_warning_text = ""
    if STARTUP_WARNINGS:
        startup_warning_text = "WARNING:\n" + "\n".join(STARTUP_WARNINGS)
    log_text = Text(Point(230, 500), startup_warning_text); log_text.setSize(12); log_text.draw(win)
    
    p_hud = draw_retro_box(win, Point(450, 260), Point(780, 360))
    e_hud = draw_retro_box(win, Point(20, 30), Point(350, 130))
    p_name_txt = Text(Point(530, 285), ""); p_name_txt.setStyle("bold"); p_name_txt.draw(win)
    e_name_txt = Text(Point(100, 55), ""); e_name_txt.setStyle("bold"); e_name_txt.draw(win)
    p_pct_txt = Text(Point(730, 325), ""); p_pct_txt.draw(win)
    e_pct_txt = Text(Point(300, 95), ""); e_pct_txt.draw(win)
    p_hp_bar = Rectangle(Point(530, 320), Point(710, 330)); p_hp_bar.draw(win)
    e_hp_bar = Rectangle(Point(100, 90), Point(280, 100)); e_hp_bar.draw(win)

    btns, btn_lbls = [], []
    move_coords = [(480, 430), (640, 430), (480, 490), (640, 490)]
    for x, y in move_coords:
        r = Rectangle(Point(x, y), Point(x+140, y+50)); r.draw(win); btns.append(r)
        l = Text(Point(x+70, y+25), ""); l.draw(win); btn_lbls.append(l)
    sw_btn = Rectangle(Point(560, 550), Point(700, 580)); sw_btn.setFill("#ffa502"); sw_btn.draw(win); btns.append(sw_btn)
    Text(Point(630, 565), "PKMN").draw(win)

    first_load = True
    while e_idx < 3 and p_idx < 3:
        curr_p, curr_e = player_team[p_idx], enemy_team[e_idx]
        p_name_txt.setText(curr_p.name.upper()); e_name_txt.setText(curr_e.name.upper())
        p_sprite = get_sprite(Point(-150, 340), curr_p.name, is_back=True)
        e_sprite = get_sprite(Point(950, 170), curr_e.name, is_back=False)
        p_sprite.draw(win); e_sprite.draw(win)

        if first_load:
            battle_intro = f"Trainer wants to battle!\nThey sent out {curr_e.name.upper()}!"
            if startup_warning_text:
                log_text.setText(f"{startup_warning_text}\n\n{battle_intro}")
            else:
                log_text.setText(battle_intro)
            for _ in range(35): p_sprite.move(10, 0); e_sprite.move(-10, 0); time.sleep(0.01)
            first_load = False
        else:
            p_sprite.undraw(); p_sprite = get_sprite(Point(200, 340), curr_p.name, is_back=True); p_sprite.draw(win)
            e_sprite.undraw(); e_sprite = get_sprite(Point(600, 170), curr_e.name, is_back=False); e_sprite.draw(win)

        while curr_p.current_hp > 0 and curr_e.current_hp > 0:
            p_p = int((max(0, curr_p.current_hp)/curr_p.max_hp)*100)
            e_p = int((max(0, curr_e.current_hp)/curr_e.max_hp)*100)
            p_pct_txt.setText(f"{p_p}%"); e_pct_txt.setText(f"{e_p}%")
            p_pct_txt.setTextColor("black"); e_pct_txt.setTextColor("black")
            
            p_hp_bar.undraw(); p_hp_bar = Rectangle(Point(530, 320), Point(530+(1.8*p_p), 330))
            p_hp_bar.setFill("#2ed573" if p_p > 30 else "#ff4757"); p_hp_bar.draw(win)
            e_hp_bar.undraw(); e_hp_bar = Rectangle(Point(100, 90), Point(100+(1.8*e_p), 100))
            e_hp_bar.setFill("#2ed573" if e_p > 30 else "#ff4757"); e_hp_bar.draw(win)

            for i in range(4): 
                mv = curr_p.moves[i]
                btn_lbls[i].setText(mv.name.upper()); btns[i].setFill(TYPE_COLORS.get(mv.type, "white"))

            action = None
            while not action:
                click = win.getMouse()
                for i, b in enumerate(btns):
                    if b.getP1().getX() < click.getX() < b.getP2().getX() and b.getP1().getY() < click.getY() < b.getP2().getY():
                        action = ("attack", curr_p.moves[i]) if i < 4 else ("switch", None)

            if action[0] == "switch":
                p_idx = switch_menu(win, player_team, p_idx)
                p_sprite.undraw(); e_sprite.undraw(); break 
            else:
                dmg, crit, mult = calculate_damage(curr_p, curr_e, action[1])
                old_hp = curr_e.current_hp; curr_e.current_hp -= dmg
                log_text.setText(f"{curr_p.name.upper()} used\n{action[1].name.upper()}!"); time.sleep(0.5)
                
                # FLICKER ENEMY ON HIT
                flicker_sprite(win, e_sprite)
                e_hp_bar = smooth_hp_drop(win, e_hp_bar, e_pct_txt, old_hp, curr_e.current_hp, curr_e.max_hp, 100, 90)
                
                if crit: log_text.setText("Critical hit!"); time.sleep(0.8)
                if mult > 1: log_text.setText("It's super effective!"); time.sleep(0.8)
                elif mult < 1 and mult > 0: log_text.setText("It's not very effective..."); time.sleep(0.8)
                
                if curr_e.current_hp <= 0:
                    e_idx += 1; log_text.setText(f"Enemy {curr_e.name.upper()}\nfainted!"); time.sleep(1.5)
                    p_sprite.undraw(); e_sprite.undraw(); break

                ai_move = random.choice(curr_e.moves)
                dmg, crit, mult = calculate_damage(curr_e, curr_p, ai_move)
                old_hp = curr_p.current_hp; curr_p.current_hp -= dmg
                log_text.setText(f"Enemy {curr_e.name.upper()} used\n{ai_move.name.upper()}!"); time.sleep(0.5)
                
                # FLICKER PLAYER ON HIT
                flicker_sprite(win, p_sprite)
                p_hp_bar = smooth_hp_drop(win, p_hp_bar, p_pct_txt, old_hp, curr_p.current_hp, curr_p.max_hp, 530, 320)

                if crit: log_text.setText("Critical hit!"); time.sleep(0.8)
                if mult > 1: log_text.setText("It's super effective!"); time.sleep(0.8)
                elif mult < 1 and mult > 0: log_text.setText("It's not very effective..."); time.sleep(0.8)

                if curr_p.current_hp <= 0:
                    log_text.setText(f"{curr_p.name.upper()}\nfainted!"); time.sleep(1.5)
                    if any(p.current_hp > 0 for p in player_team): p_idx = switch_menu(win, player_team, p_idx)
                    p_sprite.undraw(); e_sprite.undraw(); break

    final_box = draw_retro_box(win, Point(200, 200), Point(600, 400))
    res_txt = Text(Point(400, 300), "YOU WON!" if e_idx >= 3 else "YOU LOST...")
    res_txt.setSize(24); res_txt.setStyle("bold"); res_txt.draw(win)
    win.getMouse(); win.close()

if __name__ == "__main__": main()
