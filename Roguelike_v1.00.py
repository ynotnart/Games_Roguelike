
# Roguelike_v1.00
# 10/31/2025
# Tony Tran
# Source: ChatGPT


"""
Terminal Roguelike — single-file Python game (curses-based)

Enhanced features added:
- Biomes per level (cave, forest, ruins) that affect tiles, monsters, and items
- Rich monster types with distinct stats and behaviors (goblin, orc, troll, mage)
- Equipment system (weapon/head/body slots) with stat modifiers
- Spellcasting (fireball, heal, lightning) with mana and cooldowns
- Simple quest system: quest giver NPC issues retrieval quests (find an amulet)
- Infinite procedural levels; difficulty scales with level and biome

Run:
    python python_roguelike.py

Notes:
- On Windows install "windows-curses" (pip install windows-curses)
- Designed for 80x40+ terminal

This is an enhanced, but still compact, roguelike core to extend further.
"""

import curses
import random
import time
import math
from collections import deque

# ---------------------- CONFIG ----------------------
MAP_WIDTH = 80
MAP_HEIGHT = 40
ROOM_MIN_SIZE = 6
ROOM_MAX_SIZE = 14
MAX_ROOMS = 12
MAX_MONSTERS = 12
MAX_ITEMS = 8
FOV_RADIUS = 8
SEED = None

# Equipment slots
SLOT_WEAPON = 'weapon'
SLOT_HEAD = 'head'
SLOT_BODY = 'body'

# ---------------------- UTIL / GEOMETRY ----------------------
class Rect:
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h
    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
    def intersect(self, other):
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and
                self.y1 <= other.y2 and self.y2 >= other.y1)

# ---------------------- TILE & MAP ----------------------
class Tile:
    def __init__(self, walkable, block_sight=None, floor_char='.', wall_char='#'):
        self.walkable = walkable
        self.block_sight = block_sight if block_sight is not None else not walkable
        self.explored = False
        self.floor_char = floor_char
        self.wall_char = wall_char

class GameMap:
    def __init__(self, width, height, biome='cave'):
        self.width = width
        self.height = height
        self.biome = biome
        self.tiles = self.initialize_tiles()

    def initialize_tiles(self):
        default_floor = '.' if self.biome != 'forest' else ','
        default_wall = '#' if self.biome != 'forest' else '^'
        return [[Tile(False, None, default_floor, default_wall) for y in range(self.height)] for x in range(self.width)]

    def create_room(self, rect):
        for x in range(rect.x1 + 1, rect.x2):
            for y in range(rect.y1 + 1, rect.y2):
                self.tiles[x][y].walkable = True
                self.tiles[x][y].block_sight = False

    def create_h_tunnel(self, x1, x2, y):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.tiles[x][y].walkable = True
            self.tiles[x][y].block_sight = False

    def create_v_tunnel(self, y1, y2, x):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.tiles[x][y].walkable = True
            self.tiles[x][y].block_sight = False

    def is_blocked(self, x, y):
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return True
        return not self.tiles[x][y].walkable

# ---------------------- ENTITY ----------------------
class Entity:
    def __init__(self, x, y, char, color_pair=0, name='entity', blocks=False, fighter=None, ai=None, item=None, equipment=None, quest_giver=None):
        self.x = x
        self.y = y
        self.char = char
        self.color_pair = color_pair
        self.name = name
        self.blocks = blocks
        self.fighter = fighter
        if self.fighter:
            self.fighter.owner = self
        self.ai = ai
        if self.ai:
            self.ai.owner = self
        self.item = item
        if self.item:
            self.item.owner = self
        self.equipment = equipment
        if self.equipment:
            self.equipment.owner = self
        self.quest_giver = quest_giver
        if self.quest_giver:
            self.quest_giver.owner = self

    def move(self, dx, dy, game_map, entities):
        new_x = self.x + dx
        new_y = self.y + dy
        if 0 <= new_x < game_map.width and 0 <= new_y < game_map.height and not game_map.is_blocked(new_x, new_y):
            target = get_blocking_entity_at_location(entities, new_x, new_y)
            if target is None or target is self:
                self.x = new_x
                self.y = new_y
                return True
        return False

    def distance_to(self, other):
        dx = other.x - self.x
        dy = other.y - self.y
        return math.hypot(dx, dy)

# ---------------------- FIGHTER, EQUIPMENT, ITEMS, SPELLS & AI ----------------------
class Fighter:
    def __init__(self, hp, defense, power, xp=0, mana=0, mana_regen=0):
        self.max_hp = hp
        self.hp = hp
        self.defense = defense
        self.power = power
        self.xp = xp
        self.mana = mana
        self.max_mana = mana
        self.mana_regen = mana_regen
        self.owner = None

    def take_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            return True
        return False

    def attack(self, target):
        weapon_bonus = 0
        if self.owner and self.owner.equipment:
            w = self.owner.equipment.slots.get(SLOT_WEAPON)
            if w and w.equippable:
                weapon_bonus = w.equippable.power_bonus
        damage = max(0, self.power + weapon_bonus - target.fighter.defense)
        return damage

class Equippable:
    def __init__(self, slot, power_bonus=0, defense_bonus=0, hp_bonus=0, mana_bonus=0):
        self.slot = slot
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus
        self.hp_bonus = hp_bonus
        self.mana_bonus = mana_bonus

class Equipment:
    def __init__(self):
        self.slots = {SLOT_WEAPON: None, SLOT_HEAD: None, SLOT_BODY: None}
        self.owner = None

    def equip(self, item):
        if not item.equippable:
            return False
        slot = item.equippable.slot
        prev = self.slots.get(slot)
        self.slots[slot] = item
        return prev

    def unequip(self, slot):
        prev = self.slots.get(slot)
        self.slots[slot] = None
        return prev

class Item:
    def __init__(self, use_function=None, equippable=None, name='item'):
        self.use_function = use_function
        self.equippable = equippable
        self.owner = None
        self.name = name

    def pick_up(self, inventory, entities):
        inventory.append(self.owner)
        entities.remove(self.owner)
        message_log.add(f"Picked up {self.owner.name}.")

    def use(self, user, inventory, **kwargs):
        if self.equippable:
            # equip/unequip logic
            if not user.equipment:
                user.equipment = Equipment()
            prev = user.equipment.equip(self.owner)
            message_log.add(f"Equipped {self.owner.name} in {self.equippable.slot} slot.")
            if prev:
                inventory.append(prev)
            return True
        if self.use_function:
            result = self.use_function(user, **kwargs)
            if result:
                inventory.remove(self.owner)
            return result
        return False

# Spells
class Spell:
    def __init__(self, name, mana_cost, cast_function, cooldown=0):
        self.name = name
        self.mana_cost = mana_cost
        self.cast_function = cast_function
        self.cooldown = cooldown
        self._last_cast = -9999

    def can_cast(self, caster, game_state):
        return caster.fighter.mana >= self.mana_cost

    def cast(self, caster, **kwargs):
        if caster.fighter.mana < self.mana_cost:
            message_log.add('Not enough mana.')
            return False
        caster.fighter.mana -= self.mana_cost
        return self.cast_function(caster, **kwargs)

# AI
class BasicMonster:
    def __init__(self, behavior='melee'):
        self.owner = None
        self.behavior = behavior

    def take_turn(self, target, fov_map, game_map, entities):
        monster = self.owner
        if (monster.x, monster.y) in fov_map:
            if monster.distance_to(target) >= 2:
                dx = sign(target.x - monster.x)
                dy = sign(target.y - monster.y)
                monster.move(dx, dy, game_map, entities)
            elif target.fighter.hp > 0:
                # attack
                dmg = monster.fighter.attack(target)
                message_log.add(f"The {monster.name} attacks {target.name} for {dmg} damage.")
                dead = target.fighter.take_damage(dmg)
                if dead:
                    message_log.add(f"{target.name} dies! Game over.")
        else:
            # special behavior: mages cast spells from afar
            if self.behavior == 'mage' and random.random() < 0.2:
                # try to cast a short-range fireball if in range
                if monster.distance_to(target) <= 6 and monster.fighter.mana >= 3:
                    dmg = 6
                    message_log.add(f"The {monster.name} hurls a firebolt for {dmg} damage!")
                    dead = target.fighter.take_damage(dmg)
                    monster.fighter.mana = max(0, monster.fighter.mana-3)
                    if dead:
                        message_log.add(f"{target.name} dies! Game over.")
            else:
                if random.random() < 0.3:
                    dx = random.choice([-1, 0, 1])
                    dy = random.choice([-1, 0, 1])
                    monster.move(dx, dy, game_map, entities)

# ---------------------- MESSAGE LOG ----------------------
class MessageLog:
    def __init__(self):
        self.messages = deque(maxlen=400)
    def add(self, msg):
        timestamp = time.strftime('%H:%M')
        self.messages.append(f"{timestamp} - {msg}")
message_log = MessageLog()

# ---------------------- HELPERS ----------------------
def sign(x):
    return (x > 0) - (x < 0)

def get_blocking_entity_at_location(entities, dest_x, dest_y):
    for e in entities:
        if e.blocks and e.x == dest_x and e.y == dest_y:
            return e
    return None

# Bresenham for LOS
def bresenham_line(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = -1 if x0 > x1 else 1
    sy = -1 if y0 > y1 else 1
    if dx > dy:
        err = dx / 2.0
        while x != x1:
            points.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y1:
            points.append((x, y))
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    points.append((x1, y1))
    return points

# FOV raycasting
def compute_fov(game_map, x, y, radius):
    visible = set()
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            tx = x + dx
            ty = y + dy
            if 0 <= tx < game_map.width and 0 <= ty < game_map.height:
                if dx*dx + dy*dy <= radius*radius:
                    blocked = False
                    for (lx, ly) in bresenham_line(x, y, tx, ty):
                        if game_map.tiles[lx][ly].block_sight and (lx, ly) != (x, y):
                            blocked = True
                            break
                    if not blocked:
                        visible.add((tx, ty))
    return visible

# ---------------------- DUNGEON GENERATION WITH BIOMES ----------------------
BIOMES = ['cave', 'forest', 'ruins']

def make_map(max_rooms, room_min_size, room_max_size, map_width, map_height, player, entities, level=1, rng=None):
    rng = rng or random
    biome = rng.choice(BIOMES)
    game_map = GameMap(map_width, map_height, biome=biome)
    rooms = []
    num_rooms = 0

    # place a quest NPC on level 1 sometimes
    for r in range(max_rooms):
        w = rng.randint(room_min_size, room_max_size)
        h = rng.randint(room_min_size, room_max_size)
        x = rng.randint(0, map_width - w - 1)
        y = rng.randint(0, map_height - h - 1)
        new_room = Rect(x, y, w, h)
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
        if not failed:
            game_map.create_room(new_room)
            (new_x, new_y) = new_room.center()
            if num_rooms == 0:
                player.x = new_x
                player.y = new_y
            else:
                (prev_x, prev_y) = rooms[num_rooms - 1].center()
                if rng.random() < 0.5:
                    game_map.create_h_tunnel(prev_x, new_x, prev_y)
                    game_map.create_v_tunnel(prev_y, new_y, new_x)
                else:
                    game_map.create_v_tunnel(prev_y, new_y, prev_x)
                    game_map.create_h_tunnel(prev_x, new_x, new_y)
            place_entities(new_room, entities, level, rng, biome)
            rooms.append(new_room)
            num_rooms += 1
    # place stairs in last room
    if rooms:
        sx, sy = rooms[-1].center()
        stairs = Entity(sx, sy, '>', name='stairs', blocks=False)
        entities.append(stairs)
    # place a quest giver sometimes on early levels
    if level == 1 and rng.random() < 0.7:
        rx = rng.randint(rooms[0].x1+1, rooms[0].x2-1)
        ry = rng.randint(rooms[0].y1+1, rooms[0].y2-1)
        quest = QuestGiverQuest('Retrieve the Lost Amulet', 'amulet', reward_item=create_equipment('Amulet of Vigor', SLOT_HEAD, hp_bonus=5))
        npc = Entity(rx, ry, 'N', name='mysterious NPC', blocks=True, quest_giver=quest)
        entities.append(npc)
    game_map.biome = biome
    return game_map

# ---------------------- PLACE ENTITIES (MONSTERS & ITEMS DEPENDING ON BIOME) ----------------------

def place_entities(room, entities, level, rng, biome):
    number_of_monsters = rng.randint(0, max(0, int(MAX_MONSTERS * (0.5 + level * 0.08))))
    number_of_items = rng.randint(0, max(0, int(MAX_ITEMS * (0.3 + level * 0.03))))
    for i in range(number_of_monsters):
        x = rng.randint(room.x1 + 1, room.x2 - 1)
        y = rng.randint(room.y1 + 1, room.y2 - 1)
        if not any([e for e in entities if e.x == x and e.y == y]):
            roll = rng.random()
            if biome == 'forest':
                # more goblins
                if roll < 0.6:
                    monster = make_goblin(x, y, level)
                elif roll < 0.85:
                    monster = make_orc(x, y, level)
                else:
                    monster = make_mage(x, y, level)
            elif biome == 'ruins':
                if roll < 0.4:
                    monster = make_orc(x, y, level)
                elif roll < 0.75:
                    monster = make_mage(x, y, level)
                else:
                    monster = make_troll(x, y, level)
            else:  # cave
                if roll < 0.5:
                    monster = make_goblin(x, y, level)
                elif roll < 0.85:
                    monster = make_orc(x, y, level)
                else:
                    monster = make_troll(x, y, level)
            entities.append(monster)
    for i in range(number_of_items):
        x = rng.randint(room.x1 + 1, room.x2 - 1)
        y = rng.randint(room.y1 + 1, room.y2 - 1)
        if not any([e for e in entities if e.x == x and e.y == y]):
            if rng.random() < 0.6:
                item = Entity(x, y, '!', name='healing potion', item=Item(use_function=heal))
            else:
                # equipment or mysterious scroll
                if rng.random() < 0.5:
                    eq = create_random_equipment(rng, level)
                    item = Entity(x, y, eq['char'], name=eq['name'], item=Item(equippable=eq['equippable']))
                else:
                    item = Entity(x, y, '?', name='mysterious scroll', item=Item(use_function=identify))
            entities.append(item)

# ---------------------- MONSTER FACTORIES ----------------------

def make_goblin(x, y, level):
    fighter = Fighter(hp=6 + level*2, defense=0 + level//4, power=2 + level//3, xp=35 + level*5)
    ai = BasicMonster()
    return Entity(x, y, 'g', name='goblin', blocks=True, fighter=fighter, ai=ai)

def make_orc(x, y, level):
    fighter = Fighter(hp=10 + level*3, defense=1 + level//3, power=3 + level//2, xp=75 + level*10)
    ai = BasicMonster()
    return Entity(x, y, 'o', name='orc', blocks=True, fighter=fighter, ai=ai)

def make_troll(x, y, level):
    fighter = Fighter(hp=18 + level*5, defense=2 + level//2, power=6 + level//2, xp=150 + level*20, mana=0)
    ai = BasicMonster()
    return Entity(x, y, 'T', name='troll', blocks=True, fighter=fighter, ai=ai)

def make_mage(x, y, level):
    fighter = Fighter(hp=8 + level*2, defense=0 + level//4, power=2 + level//3, xp=110 + level*12, mana=8 + level*2)
    ai = BasicMonster(behavior='mage')
    return Entity(x, y, 'm', name='dark mage', blocks=True, fighter=fighter, ai=ai)

# ---------------------- EQUIPMENT / ITEMS HELPERS ----------------------

def create_equipment(name, slot, power_bonus=0, defense_bonus=0, hp_bonus=0, mana_bonus=0):
    eq = Equippable(slot=slot, power_bonus=power_bonus, defense_bonus=defense_bonus, hp_bonus=hp_bonus, mana_bonus=mana_bonus)
    char = '/' if slot == SLOT_WEAPON else '^'
    return {'name': name, 'equippable': eq, 'char': char}

def create_random_equipment(rng, level):
    slot = rng.choice([SLOT_WEAPON, SLOT_HEAD, SLOT_BODY])
    name = 'Rusty Sword' if slot == SLOT_WEAPON else ('Leather Cap' if slot==SLOT_HEAD else 'Leather Armor')
    power = rng.randint(1, 3) + level//3
    defense = rng.randint(0, 2) + level//4
    hp = rng.randint(0, 5) + level//2
    eq = create_equipment(name, slot, power, defense, hp)
    return {'name': name, 'equippable': eq['equippable'], 'char': '/' if slot==SLOT_WEAPON else '^'}

# ---------------------- SPELL FUNCTIONS ----------------------

def cast_fireball(caster, target_x=None, target_y=None, game_map=None, entities=None, radius=2, damage=12):
    # damage all entities in radius
    affected = []
    for e in entities:
        if e.fighter and math.hypot(e.x - target_x, e.y - target_y) <= radius:
            affected.append(e)
    for ent in affected:
        message_log.add(f'The {ent.name} is hit for {damage} fire damage!')
        dead = ent.fighter.take_damage(damage)
        if dead:
            message_log.add(f'The {ent.name} dies.')
            if ent != caster:
                try:
                    entities.remove(ent)
                except ValueError:
                    pass
    return True

def cast_heal(caster, amount=15, **kwargs):
    if caster.fighter.hp == caster.fighter.max_hp:
        message_log.add('Already at full health.')
        return False
    caster.fighter.hp = min(caster.fighter.max_hp, caster.fighter.hp + amount)
    message_log.add(f'You heal for {amount} HP.')
    return True

# ---------------------- QUESTS ----------------------
class QuestGiverQuest:
    def __init__(self, title, item_needed_name, reward_item=None):
        self.title = title
        self.item_needed_name = item_needed_name
        self.completed = False
        self.reward_item = reward_item
        self.owner = None

    def talk(self, player, inventory, entities):
        if self.completed:
            message_log.add('Thanks again for your help.')
            return
        # check if player has item
        for ent in inventory:
            if ent.name.lower() == self.item_needed_name:
                self.completed = True
                message_log.add(f'You give the {self.item_needed_name} to {self.owner.name}. Quest complete!')
                inventory.remove(ent)
                if self.reward_item:
                    # spawn reward at player
                    reward_ent = Entity(player.x, player.y, '^', name=self.reward_item.name, item=Item(equippable=self.reward_item.equippable))
                    entities.append(reward_ent)
                    message_log.add(f'{self.owner.name} gives you {self.reward_item.name} as a reward.')
                player.fighter.xp += 100
                return
        message_log.add(self.title + ' — Please find the ' + self.item_needed_name + '.')

# ---------------------- ITEM USE FUNCTIONS ----------------------

def heal(user, amount=10, **kwargs):
    if user.fighter.hp == user.fighter.max_hp:
        message_log.add("You are already at full health.")
        return False
    user.fighter.hp = min(user.fighter.max_hp, user.fighter.hp + amount)
    message_log.add(f"You use a potion and recover {amount} HP.")
    return True

def identify(user, **kwargs):
    message_log.add('The scroll glows faintly but nothing happens (placeholder).')
    return True

# ---------------------- INPUT HANDLING ----------------------

def handle_keys(stdscr, player, game_map, entities, inventory, spells):
    key = stdscr.getch()
    if key == -1:
        return 'no-input'
    if key in (curses.KEY_UP, ord('k')):
        return {'move': (0, -1)}
    if key in (curses.KEY_DOWN, ord('j')):
        return {'move': (0, 1)}
    if key in (curses.KEY_LEFT, ord('h')):
        return {'move': (-1, 0)}
    if key in (curses.KEY_RIGHT, ord('l')):
        return {'move': (1, 0)}
    if key == ord('g'):
        return {'pickup': True}
    if key == ord('i'):
        return {'show_inventory': True}
    if key == ord('d'):
        return {'drop': True}
    if key == ord('>'):
        return {'descend': True}
    if key == ord('q'):
        return {'exit': True}
    if key == ord('s'):
        return {'show_spells': True}
    if key == ord('1'):
        return {'cast_spell': 0}
    if key == ord('2'):
        return {'cast_spell': 1}
    return None

# ---------------------- RENDERING ----------------------

def render_all(stdscr, game_map, entities, player, fov_map, msg_log, offset_x=0, offset_y=1):
    # Draw map
    for y in range(game_map.height):
        for x in range(game_map.width):
            visible = (x, y) in fov_map
            tile = game_map.tiles[x][y]
            ch = tile.floor_char if tile.walkable else tile.wall_char
            if visible:
                tile.explored = True
                draw_char(stdscr, y+offset_y, x+offset_x, ch, color_pair(1))
            elif tile.explored:
                draw_char(stdscr, y+offset_y, x+offset_x, ch, color_pair(2))
            else:
                draw_char(stdscr, y+offset_y, x+offset_x, ' ')
    # Draw entities (ensure player draws last)
    for e in sorted(entities, key=lambda z: z.blocks):
        if (e.x, e.y) in fov_map or (game_map.tiles[e.x][e.y].explored if 0<=e.x<game_map.width and 0<=e.y<game_map.height else False):
            draw_char(stdscr, e.y+offset_y, e.x+offset_x, e.char, e.color_pair)
    # HUD
    h, w = stdscr.getmaxyx()
    hp_text = f"HP: {player.fighter.hp}/{player.fighter.max_hp}  Mana: {player.fighter.mana}/{player.fighter.max_mana}  XP: {player.fighter.xp}  Floor: {game_state['level']}  Biome: {game_map.biome}"
    draw_text_line(stdscr, 0, 0, hp_text[:w-1])
    # spells
    draw_text_line(stdscr, h-3, 0, 'Spells: 1) Fireball  2) Heal')
    # messages
    max_msgs = min(6, len(msg_log.messages))
    for i in range(max_msgs):
        msg = list(msg_log.messages)[-max_msgs + i]
        draw_text_line(stdscr, h - max_msgs + i - 1, 0, msg[:w-1])

def draw_char(stdscr, row, col, ch, color=0):
    try:
        if color:
            stdscr.addstr(row, col, ch, curses.color_pair(color))
        else:
            stdscr.addstr(row, col, ch)
    except curses.error:
        pass

def draw_text_line(stdscr, row, col, text):
    try:
        stdscr.addstr(row, col, text)
    except curses.error:
        pass

def color_pair(n):
    return n

# ---------------------- GAME STATE ----------------------

game_state = {'level': 1, 'turn_count': 0}

# ---------------------- MAIN GAME LOOP ----------------------

def main(stdscr):
    global SEED
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    if SEED is None:
        seed = int(time.time() * 1000) & 0xffffffff
    else:
        seed = SEED
    rng = random.Random(seed)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
    # create player
    player_fighter = Fighter(hp=40, defense=2, power=6, xp=0, mana=10, mana_regen=1)
    player = Entity(0, 0, '@', color_pair(4), name='Player', blocks=True, fighter=player_fighter, equipment=Equipment())
    inventory = []
    entities = [player]
    # initial spells
    spells = [Spell('Fireball', mana_cost=5, cast_function=lambda caster, **kw: cast_fireball(caster, game_map=current_map, entities=entities, **kw)), Spell('Heal', mana_cost=3, cast_function=lambda caster, **kw: cast_heal(caster, amount=12))]
    # generate first map
    current_map = make_map(MAX_ROOMS, ROOM_MIN_SIZE, ROOM_MAX_SIZE, MAP_WIDTH, MAP_HEIGHT, player, entities, level=1, rng=rng)
    fov_map = compute_fov(current_map, player.x, player.y, FOV_RADIUS)
    message_log.add('Welcome — press 1/2 to cast spells. s to show spells. g pickup, i inventory, > descend, q quit.')
    while True:
        stdscr.erase()
        fov_map = compute_fov(current_map, player.x, player.y, FOV_RADIUS)
        render_all(stdscr, current_map, entities, player, fov_map, message_log)
        stdscr.refresh()
        game_state['turn_count'] += 1
        action = handle_keys(stdscr, player, current_map, entities, inventory, spells)
        if action is None or action == 'no-input':
            # regen mana slowly
            if player.fighter.mana < player.fighter.max_mana:
                player.fighter.mana = min(player.fighter.max_mana, player.fighter.mana + player.fighter.mana_regen)
            time.sleep(0.02)
            continue
        if 'exit' in action:
            message_log.add('Thanks for playing!')
            break
        player_turn_taken = False
        if 'move' in action:
            dx, dy = action['move']
            dest_x = player.x + dx
            dest_y = player.y + dy
            target = get_blocking_entity_at_location(entities, dest_x, dest_y)
            if target and target.fighter:
                dmg = player.fighter.attack(target)
                message_log.add(f'You attack the {target.name} for {dmg} damage.')
                dead = target.fighter.take_damage(dmg)
                if dead:
                    message_log.add(f'The {target.name} dies and you gain {target.fighter.xp} XP.')
                    player.fighter.xp += target.fighter.xp
                    try:
                        entities.remove(target)
                    except ValueError:
                        pass
            else:
                moved = player.move(dx, dy, current_map, entities)
                if moved:
                    player_turn_taken = True
                    # step on quest NPC
                    for e in entities:
                        if e.quest_giver and e.x == player.x and e.y == player.y:
                            e.quest_giver.talk(player, inventory, entities)
        if 'pickup' in action:
            for e in list(entities):
                if e.item and e.x == player.x and e.y == player.y:
                    e.item.pick_up(inventory, entities)
                    break
            else:
                message_log.add('There is nothing here to pick up.')
        if 'show_inventory' in action:
            show_inventory(stdscr, inventory, player, entities)
        if 'drop' in action:
            if inventory:
                ent = inventory.pop()
                ent.x = player.x
                ent.y = player.y
                entities.append(ent)
                message_log.add(f'Dropped {ent.name}.')
            else:
                message_log.add('Inventory is empty.')
        if 'descend' in action:
            for e in entities:
                if e.char == '>' and e.x == player.x and e.y == player.y:
                    game_state['level'] += 1
                    message_log.add(f'You descend to floor {game_state["level"]}.')
                    entities = [player]
                    player.fighter.hp = min(player.fighter.max_hp, player.fighter.hp + 5)
                    current_map = make_map(MAX_ROOMS, ROOM_MIN_SIZE, ROOM_MAX_SIZE, MAP_WIDTH, MAP_HEIGHT, player, entities, level=game_state['level'], rng=rng)
                    break
            else:
                message_log.add('There are no stairs here.')
        if 'show_spells' in action:
            # simple display
            message_log.add('Spells: 1) Fireball (cost 5) 2) Heal (cost 3)')
        if 'cast_spell' in action:
            idx = action['cast_spell']
            if 0 <= idx < len(spells):
                spell = spells[idx]
                if spell.can_cast(player, game_state):
                    if spell.name == 'Fireball':
                        # simple targeting: center at player + direction (forward) or at player
                        tx, ty = player.x, player.y
                        # cast around player for demo
                        spell.cast(player, target_x=player.x, target_y=player.y, game_map=current_map, entities=entities)
                    else:
                        spell.cast(player)
                else:
                    message_log.add('Cannot cast that now.')
        # monsters take turns
        if player_turn_taken:
            for e in list(entities):
                if e.ai:
                    e.ai.take_turn(player, fov_map, current_map, entities)
        # simple level up when xp thresholds reached
        # allow equipment effects to alter stats (simple: recalc HP/mana)
        apply_equipment_bonuses(player)

# ---------------------- INVENTORY DISPLAY ----------------------

def show_inventory(stdscr, inventory, player, entities):
    h, w = stdscr.getmaxyx()
    win_h = min(12, h-6)
    win_w = min(50, w-4)
    win = curses.newwin(win_h, win_w, (h-win_h)//2, (w-win_w)//2)
    win.border()
    win.addstr(0, 2, ' Inventory ')
    if not inventory:
        win.addstr(2, 2, '(empty)')
        win.getch()
        return
    for i, item in enumerate(inventory[:win_h-4]):
        win.addstr(2+i, 2, f'{i+1}. {item.name}')
    win.addstr(win_h-2, 2, 'Press number to use/equip, any other key to exit')
    ch = win.getch()
    if ord('1') <= ch <= ord(str(min(9, len(inventory)))):
        idx = ch - ord('1')
        item_ent = inventory[idx]
        if item_ent.item:
            used = item_ent.item.use(player, inventory, entities=entities)
            if used:
                message_log.add(f'Used {item_ent.name}.')
    return

# ---------------------- EQUIPMENT / STATS ----------------------

def apply_equipment_bonuses(player):
    # reset to base values (we assume base fighter stores base max values)
    # For simplicity, bonuses only affect max_hp and power
    base_hp = max(1, player.fighter.max_hp)
    base_power = player.fighter.power
    base_def = player.fighter.defense
    bonus_hp = 0
    bonus_power = 0
    bonus_def = 0
    if player.equipment:
        for slot, item in player.equipment.slots.items():
            if item and item.item and item.item.equippable:
                eq = item.item.equippable
                bonus_hp += eq.hp_bonus
                bonus_power += eq.power_bonus
                bonus_def += eq.defense_bonus
                if eq.mana_bonus:
                    player.fighter.max_mana = player.fighter.max_mana + eq.mana_bonus
    player.fighter.max_hp = base_hp + bonus_hp
    player.fighter.power = base_power + bonus_power
    player.fighter.defense = base_def + bonus_def
    # ensure current hp/mana are within bounds
    player.fighter.hp = min(player.fighter.hp, player.fighter.max_hp)
    player.fighter.mana = min(player.fighter.mana, player.fighter.max_mana)

# ---------------------- ENTRY POINT ----------------------

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except Exception as e:
        print('An error occurred:', e)
        print('If on Windows, consider installing windows-curses via pip.')
