import asyncio
import json
import os
import random
import string
import time
import uuid
from datetime import datetime


from nio import AsyncClient, RoomMessageText
from openai import AsyncOpenAI

HOMESERVER = "https://matrix.org"
USER_ID = "your useless alt account"
PASSWORD_FILE = "password.txt"
SCORES_FILE = "scores.json"

# Hugging Face Inference Router configuration
with open("hf_key.txt", "r", encoding="utf-8") as f:
    HF_TOKEN = f.read().strip()

ai = AsyncOpenAI(
    api_key=HF_TOKEN,
    base_url="https://router.huggingface.co/v1",
)
AI_MODEL = "Qwen/Qwen3-0.6B:featherless-ai"
TARGET_USER = "@zacino:unredacted.org"
ai_history = {}

START_TIME = time.time()
client = None
scores = {}
number_games = {}
wordle_games = {}
scramble_games = {}
blackjack_games = {}
trivia_games = {}
duels = {}
polls = {}
races = {}
bomb_games = {}

WORDS = [
    "apple", "brick", "cloud", "dream", "flame", "ghost", "grape",
    "heart", "house", "lemon", "light", "magic", "music", "night",
    "ocean", "pizza", "plant", "robot", "smile", "storm", "tiger",
    "train", "water", "world", "zebra"
]

TRIVIA = [
    ("What planet is known as the Red Planet?", ["mars", "Mars"]),
    ("How many sides does a hexagon have?", ["6", "six"]),
    ("What is the largest ocean on Earth?", ["pacific", "pacific ocean"]),
    ("What is 12 × 8?", ["96"]),
    ("Which animal is known as the king of the jungle?", ["lion", "a lion"]),
    ("What is the chemical symbol for gold?", ["au"]),
    ("How many bits are in one byte?", ["8", "eight"]),
    ("What is the capital of Japan?", ["tokyo"]),
    ("Which gas do plants absorb from the atmosphere?", ["carbon dioxide", "co2"]),
    ("How many players are on a football/soccer team on the field?", ["11", "eleven"]),
]

JOKES = [
    "Why did the computer get cold? It left its Windows open.",
    "Why was the math book sad? It had too many problems.",
    "I told my computer I needed a break. It said: 'No problem, I'll go to sleep.'",
    "Why did the gamer bring a ladder? To reach the next level.",
]
FACTS = [
    "Octopuses have three hearts.",
    "A day on Venus is longer than its year.",
    "Bananas are berries, botanically speaking.",
    "Honey can remain edible for a very long time when properly sealed.",
]
COMPLIMENTS = ["You're a certified legend.", "Your brain has good ping today.", "You have main-character energy."]
INSULTS = ["Your Wi-Fi has more stability than your plans.", "You play like your mouse has input delay.", "Your luck needs a patch update."]
EMOJIS = {"happy": "😄", "sad": "😢", "fire": "🔥", "love": "❤️", "skull": "💀", "laugh": "😂", "cool": "😎"}

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

BANS_FILE = "bans.json"
banned_users = set(load_json(BANS_FILE, []))

def save_bans():
    save_json(BANS_FILE, sorted(banned_users))

scores = load_json(SCORES_FILE, {})

def user_name(event):
    return getattr(event, "sender", "unknown")

def add_points(user, amount=1):
    scores[user] = int(scores.get(user, 0)) + amount
    save_json(SCORES_FILE, scores)

async def reply(room_id, message):
    await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": str(message)},
    )

def card():
    return random.choice(["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])

def hand_value(hand):
    total = 0
    aces = 0
    for c in hand:
        if c == "A":
            total += 11
            aces += 1
        elif c in ("J", "Q", "K"):
            total += 10
        else:
            total += int(c)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

HELP = """Commands:
Basic: !help !ping !uptime !coin !dice [sides] !roll [max] !flip !random [min] [max] !choose a | b
Fun: !8ball question !rate thing !ship name1 | name2 !joke !fact !compliment !insult
Text: !reverse text !upper text !lower text !mock text !clap text !spoiler text !count text !vowels text !length text !repeat n | text !emojify text
Math/tools: !sqrt n !percent x | y !table n !binary text !unbinary bits !hex text !unhex hex !uuid !password [length]
Scores: !points !leaderboard
Games: !guess [1-100] !number [1-100] !rps rock/paper/scissors
!wordle, !wguess WORD, !scramble, !unscramble WORD
!blackjack, !hit, !stand
!trivia, !answer ANSWER
!duel @user:matrix.org, !accept, !decline
!poll question | option 1 | option 2, !vote NUMBER
!race, !joinrace, !startrace
!bomb, !defuse CODE, !cancelgame
(!ban and !unban for admins)"""

async def on_message(room, event):
    if not isinstance(event, RoomMessageText):
        return
    if event.sender == USER_ID:
        return
    if getattr(event, "server_timestamp", 0) < START_TIME * 1000:
        return

    body = event.body.strip()
    if not body:
        return

    # Normal messages go to Hugging Face only while TARGET_USER is offline.
    # Messages beginning with ! continue to the existing command handler.
    if not body.startswith("!"):
        try:
            presence = await client.get_presence(TARGET_USER)
            if getattr(presence, "presence", None) == "offline":
                history = ai_history.setdefault(room.room_id, [])
                history.append({
                    "role": "user",
                    "content": f"{event.sender}: {body}",
                })
                history[:] = history[-10:]

                response = await ai.chat.completions.create(
                    model=AI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an AI assistant in a Matrix group chat. "
                                "Reply naturally and concisely. You are not the human "
                                "account that is currently offline. The text before each "
                                "message identifies its sender."
                            ),
                        },
                        *history,
                    ],
                    max_tokens=250,
                )

                answer = response.choices[0].message.content or ""
                if answer.strip():
                    await reply(room.room_id, answer.strip())
                    history.append({"role": "assistant", "content": answer.strip()})
                    history[:] = history[-10:]
        except Exception as exc:
            print(f"AI response error: {exc}")
        return

    parts = body.split()
    command = parts[0].lower()
    args = parts[1:]
    room_id = room.room_id
    user = event.sender
    lower = body.lower()

    # Users allowed to ban others
    # Admins and banned users
    ADMINS = {
        "@zacino:unredacted.org",
        "@zacino:matrix.org",
        "@zacino:newthe30s.ftp.sh",
    }

    # Ban command
    if command == "!ban":
        target = args[0] if args else ""

        if user not in ADMINS:
            await reply(room_id, "You are not authorized to use this command.")
        elif not target.startswith("@") or ":" not in target:
            await reply(room_id, "Usage: !ban @user:homeserver")
        else:
            banned_users.add(target)
            save_bans()
            await reply(room_id, f"{target} can no longer use !unhex or !unbinary and other commands such as upper that leds to the bot saying bad stuff.")
        return

    # Unban command
    if command == "!unban":
        target = args[0] if args else ""

        if user not in ADMINS:
            await reply(room_id, "You are not authorized to use this command.")
        elif not target.startswith("@") or ":" not in target:
            await reply(room_id, "Usage: !unban @user:homeserver")
        elif target in banned_users:
            banned_users.remove(target)
            save_bans()
            await reply(room_id, f"{target} has been unbanned.")
        else:
            await reply(room_id, f"{target} is not banned.")
        return

    # Restrict banned users
    if user in banned_users and command in ("!unhex", "!unbinary", "!mock", "!upper", "!lower", "!spoiler", "!clap", "!repeat", "!emojify"):
        await reply(room_id, "You are banned from using this command.")
        return

    try:
        if command == "!help":
            await reply(room_id, HELP)
        elif command == "!ping":
            await reply(room_id, "Pong!")
        elif command == "!uptime":
            seconds = int(time.time() - START_TIME)
            await reply(room_id, f"Uptime: {seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s")
        elif command == "!coin":
            await reply(room_id, random.choice(["Heads", "Tails"]))
        elif command == "!dice":
            sides = max(2, min(1000, int(args[0]))) if args else 6
            await reply(room_id, f"🎲 {random.randint(1, sides)} (d{sides})")
        elif command == "!roll":
            maximum = max(1, min(1_000_000, int(args[0]))) if args else 100
            await reply(room_id, str(random.randint(1, maximum)))
        elif command == "!flip":
            await reply(room_id, random.choice(["(╯°□°）╯︵ ┻━┻", "┬─┬ノ( º _ ºノ)"]))
        elif command == "!random":
            low, high = (int(args[0]), int(args[1])) if len(args) >= 2 else (1, 100)
            await reply(room_id, str(random.randint(min(low, high), max(low, high))))
        elif command == "!choose":
            options = body[len(command):].strip().split("|")
            options = [x.strip() for x in options if x.strip()]
            await reply(room_id, random.choice(options) if options else "Use: !choose option 1 | option 2")
        elif command == "!8ball":
            await reply(room_id, random.choice(["Yes.", "No.", "Maybe.", "Absolutely.", "Ask again later.", "Probably not.", "The odds look good."]))
        elif command == "!rate":
            await reply(room_id, f"{random.randint(0, 100)}/100")
        elif command == "!ship":
            names = [x.strip() for x in body[len(command):].split("|") if x.strip()]
            await reply(room_id, f"Compatibility: {random.randint(0, 100)}%" if len(names) >= 2 else "Use: !ship name1 | name2")
        elif command == "!joke":
            await reply(room_id, random.choice(JOKES))
        elif command == "!fact":
            await reply(room_id, random.choice(FACTS))
        elif command == "!trivia":
            q, answers = random.choice(TRIVIA)
            trivia_games[room_id] = {"answers": [a.lower() for a in answers], "user": user}
            await reply(room_id, f"Trivia: {q}\nReply with !answer YOUR ANSWER. First correct answer gets 3 points.")
        elif command == "!answer":
            game = trivia_games.get(room_id)
            answer = " ".join(args).strip().lower()
            if game and answer in game["answers"]:
                add_points(user, 3)
                trivia_games.pop(room_id, None)
                await reply(room_id, f"Correct, {user}! +3 points.")
            elif game:
                await reply(room_id, "Not quite. Try again.")
            else:
                await reply(room_id, "No trivia question is active. Use !trivia.")
        elif command == "!rps":
            choice = args[0].lower() if args else ""
            if choice not in ("rock", "paper", "scissors"):
                await reply(room_id, "Use: !rps rock, !rps paper, or !rps scissors")
            else:
                bot = random.choice(["rock", "paper", "scissors"])
                if choice == bot:
                    result = "Draw."
                elif (choice, bot) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
                    add_points(user, 2)
                    result = "You win! +2 points."
                else:
                    result = "You lose."
                await reply(room_id, f"You: {choice} | Bot: {bot}. {result}")
        elif command in ("!guess", "!number"):
            if len(args) >= 1:
                try:
                    guess = int(args[0])
                except ValueError:
                    guess = -1
                game = number_games.get(room_id)
                if not game:
                    await reply(room_id, "No number game active. Start one with !guess.")
                elif not 1 <= guess <= 100:
                    await reply(room_id, "Guess a number from 1 to 100.")
                elif guess == game["number"]:
                    add_points(user, 5)
                    number_games.pop(room_id, None)
                    await reply(room_id, f"Correct! {user} gets 5 points.")
                else:
                    await reply(room_id, "Too low." if guess < game["number"] else "Too high.")
            else:
                number_games[room_id] = {"number": random.randint(1, 100)}
                await reply(room_id, "Number game started. Guess 1–100 with !guess NUMBER.")
        elif command == "!wordle":
            wordle_games[room_id] = {"word": random.choice(WORDS), "tries": 6, "user": user}
            await reply(room_id, "Wordle started: guess the 5-letter word in 6 tries using !wguess WORD.")
        elif command == "!wguess":
            game = wordle_games.get(room_id)
            guess = args[0].lower() if args else ""
            if not game:
                await reply(room_id, "Start a game with !wordle.")
            elif len(guess) != 5 or not guess.isalpha():
                await reply(room_id, "Enter one 5-letter word: !wguess WORD")
            else:
                word = game["word"]
                if guess == word:
                    add_points(user, 5)
                    wordle_games.pop(room_id, None)
                    await reply(room_id, f"Correct! The word was {word}. +5 points.")
                else:
                    game["tries"] -= 1
                    marks = " ".join(c + ("✓" if c == word[i] else "•" if c in word else "×") for i, c in enumerate(guess))
                    if game["tries"] <= 0:
                        wordle_games.pop(room_id, None)
                        await reply(room_id, f"No tries left. The word was {word}.")
                    else:
                        await reply(room_id, f"{marks}\n{game['tries']} tries left. ✓ correct spot, • wrong spot, × not in word.")
        elif command == "!scramble":
            word = random.choice(WORDS)
            mixed = word
            while mixed == word:
                mixed = "".join(random.sample(word, len(word)))
            scramble_games[room_id] = {"word": word, "user": user}
            await reply(room_id, f"Unscramble this: {mixed}. Answer with !unscramble WORD.")
        elif command == "!unscramble":
            game = scramble_games.get(room_id)
            answer = args[0].lower() if args else ""
            if game and answer == game["word"]:
                add_points(user, 3)
                scramble_games.pop(room_id, None)
                await reply(room_id, f"Correct! +3 points, {user}.")
            elif game:
                await reply(room_id, "Wrong—try again.")
            else:
                await reply(room_id, "Start with !scramble.")
        elif command == "!blackjack":
            blackjack_games[room_id] = {"hand": [card(), card()], "dealer": [card(), card()]}
            g = blackjack_games[room_id]
            await reply(room_id, f"Your hand: {g['hand']} ({hand_value(g['hand'])}). Dealer shows {g['dealer'][0]}. Use !hit or !stand.")
        elif command == "!hit":
            g = blackjack_games.get(room_id)
            if not g:
                await reply(room_id, "Start with !blackjack.")
            else:
                g["hand"].append(card())
                value = hand_value(g["hand"])
                if value > 21:
                    blackjack_games.pop(room_id, None)
                    await reply(room_id, f"You drew {g['hand'][-1]}. Total {value}: bust.")
                else:
                    await reply(room_id, f"You drew {g['hand'][-1]}. Hand: {g['hand']} ({value}). !hit or !stand.")
        elif command == "!stand":
            g = blackjack_games.pop(room_id, None)
            if not g:
                await reply(room_id, "Start with !blackjack.")
            else:
                while hand_value(g["dealer"]) < 17:
                    g["dealer"].append(card())
                player, dealer = hand_value(g["hand"]), hand_value(g["dealer"])
                if dealer > 21 or player > dealer:
                    add_points(user, 3)
                    result = "You win! +3 points."
                elif player == dealer:
                    result = "Draw."
                else:
                    result = "Dealer wins."
                await reply(room_id, f"Your hand {g['hand']} = {player}; dealer {g['dealer']} = {dealer}. {result}")
        elif command == "!duel":
            target = args[0] if args else ""
            if (
                not target.startswith("@")
                or ":" not in target
                or not target.split(":", 1)[1]
            ):
                await reply(room_id, "Use: !duel @user:homeserver")
            elif target == user:
                await reply(room_id, "You cannot duel yourself.")
            else:
                duels[room_id] = {"from": user, "to": target}
                await reply(
                    room_id,
                    f"{target}: {user} challenges you! Use !accept or !decline."
                )
        elif command == "!accept":
            g = duels.get(room_id)
            if g and user == g["to"]:
                winner = random.choice([g["from"], g["to"]])
                loser = g["to"] if winner == g["from"] else g["from"]
                add_points(winner, 5)
                duels.pop(room_id, None)
                await reply(room_id, f"Duel result: {winner} wins 5 points. {loser} loses.")
            else:
                await reply(room_id, "No duel addressed to you is waiting.")
        elif command == "!decline":
            g = duels.get(room_id)
            if g and user == g["to"]:
                duels.pop(room_id, None)
                await reply(room_id, "Duel declined.")
            else:
                await reply(room_id, "No duel addressed to you is waiting.")
        elif command == "!poll":
            options = [x.strip() for x in body[len(command):].split("|") if x.strip()]
            if len(options) < 3:
                await reply(room_id, "Use: !poll question | option 1 | option 2")
            else:
                question, choices = options[0], options[1:10]
                polls[room_id] = {"question": question, "choices": choices, "votes": {}}
                await reply(room_id, "Poll: " + question + "\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(choices)) + "\nVote with !vote NUMBER.")
        elif command == "!vote":
            poll = polls.get(room_id)
            if not poll:
                await reply(room_id, "No active poll. Start one with !poll.")
            else:
                try:
                    index = int(args[0]) - 1
                    if not 0 <= index < len(poll["choices"]):
                        raise ValueError
                    poll["votes"][user] = index
                    counts = [list(poll["votes"].values()).count(i) for i in range(len(poll["choices"]))]
                    await reply(room_id, "Vote recorded. " + " | ".join(f"{i+1}: {n}" for i, n in enumerate(counts)))
                except (ValueError, IndexError):
                    await reply(room_id, "Use !vote NUMBER from the listed options.")
        elif command == "!race":
            races[room_id] = {"players": [], "started": False}
            await reply(room_id, "Race lobby opened! Use !joinrace, then !startrace.")
        elif command == "!joinrace":
            g = races.get(room_id)
            if not g or g["started"]:
                await reply(room_id, "No open race. Use !race.")
            elif user in g["players"]:
                await reply(room_id, "You're already in.")
            else:
                g["players"].append(user)
                await reply(room_id, f"{user} joined the race ({len(g['players'])} players).")
        elif command == "!startrace":
            g = races.get(room_id)
            if not g or g["started"]:
                await reply(room_id, "No race lobby. Use !race.")
            elif len(g["players"]) < 2:
                await reply(room_id, "Need at least 2 players. Use !joinrace.")
            else:
                g["started"] = True
                winner = random.choice(g["players"])
                add_points(winner, 5)
                races.pop(room_id, None)
                await reply(room_id, f"Race finished! Winner: {winner} (+5 points).")
        elif command == "!bomb":
            code = f"{random.randint(0, 9999):04d}"
            bomb_games[room_id] = {"code": code, "tries": 8}
            await reply(room_id, "Bomb-code game started! Guess the 4-digit code with !defuse CODE. You have 8 tries.")
        elif command == "!defuse":
            g = bomb_games.get(room_id)
            code = args[0] if args else ""
            if not g:
                await reply(room_id, "Start with !bomb.")
            elif len(code) != 4 or not code.isdigit():
                await reply(room_id, "Use a 4-digit code: !defuse 1234")
            elif code == g["code"]:
                add_points(user, 5)
                bomb_games.pop(room_id, None)
                await reply(room_id, f"Defused! {user} gets 5 points.")
            else:
                g["tries"] -= 1
                correct_digits = sum(a == b for a, b in zip(code, g["code"]))
                if g["tries"] <= 0:
                    bomb_games.pop(room_id, None)
                    await reply(room_id, f"Out of tries. Code was {g['code']}.")
                else:
                    await reply(room_id, f"{correct_digits} digit(s) in the correct position. {g['tries']} tries left.")
        elif command == "!cancelgame":
            removed = False
            for collection in (number_games, wordle_games, scramble_games, blackjack_games, trivia_games, duels, polls, races, bomb_games):
                if room_id in collection:
                    collection.pop(room_id, None)
                    removed = True
            await reply(room_id, "Active room game cancelled." if removed else "No active game to cancel.")
        elif command == "!password":
            length = max(4, min(128, int(args[0]))) if args else 16
            await reply(room_id, "".join(random.SystemRandom().choice(string.ascii_letters + string.digits + "!@#$%^&*") for _ in range(length)))
        elif command == "!uuid":
            await reply(room_id, str(uuid.uuid4()))
        elif command == "!reverse":
            await reply(room_id, body[len(command):].strip()[::-1])
        elif command == "!upper":
            await reply(room_id, body[len(command):].strip().upper())
        elif command == "!lower":
            await reply(room_id, body[len(command):].strip().lower())
        elif command == "!mock":
            text = body[len(command):].strip()
            await reply(room_id, "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text)))
        elif command == "!clap":
            await reply(room_id, " 👏 ".join(body[len(command):].strip().split()))
        elif command == "!spoiler":
            await reply(room_id, f"||{body[len(command):].strip()}||")
        elif command == "!count":
            await reply(room_id, f"Words: {len(body[len(command):].split())}")
        elif command == "!vowels":
            text = body[len(command):].strip()
            await reply(room_id, f"Vowels: {sum(c.lower() in 'aeiou' for c in text)}")
        elif command == "!length":
            await reply(room_id, f"Length: {len(body[len(command):].strip())}")
        elif command == "!repeat":
            data = body[len(command):].strip().split("|", 1)
            if len(data) == 2:
                n = max(1, min(10, int(data[0].strip())))
                await reply(room_id, "\n".join([data[1].strip()] * n))
            else:
                await reply(room_id, "Use: !repeat 3 | text")
        elif command == "!emojify":
            text = body[len(command):].strip()
            for word, emoji in EMOJIS.items():
                text = text.replace(word, emoji).replace(word.capitalize(), emoji)
            await reply(room_id, text)
        elif command == "!sqrt":
            await reply(room_id, str(round(float(args[0]) ** 0.5, 6)))
        elif command == "!percent":
            data = body[len(command):].strip().split("|")
            if len(data) >= 2:
                x, y = float(data[0]), float(data[1])
                await reply(room_id, "Undefined (division by zero)." if y == 0 else f"{x / y * 100:.2f}%")
            else:
                await reply(room_id, "Use: !percent x | y")
        elif command == "!table":
            n = int(args[0])
            await reply(room_id, "\n".join(f"{n} × {i} = {n*i}" for i in range(1, 13)))
        elif command == "!binary":
            await reply(room_id, " ".join(format(b, "08b") for b in body[len(command):].strip().encode()))
        elif command == "!unbinary":
            bits = "".join(args)
            await reply(room_id, bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8)).decode(errors="replace"))
        elif command == "!hex":
            await reply(room_id, body[len(command):].strip().encode().hex())
        elif command == "!unhex":
            await reply(room_id, bytes.fromhex("".join(args)).decode(errors="replace"))
        elif command == "!compliment":
            await reply(room_id, random.choice(COMPLIMENTS))
        elif command == "!insult":
            await reply(room_id, random.choice(INSULTS))
        elif command == "!points":
            await reply(room_id, f"{user}: {scores.get(user, 0)} points")
        elif command == "!leaderboard":
            top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]
            await reply(room_id, "Leaderboard:\n" + ("\n".join(f"{i+1}. {name.lstrip('@')}: {points}" for i, (name, points) in enumerate(top)) if top else "No points yet."))
        else:
            return

        if command not in ("!points", "!leaderboard", "!help", "!cancelgame"):
            add_points(user, 1)

    except (ValueError, IndexError, OverflowError):
        await reply(room_id, "Invalid input. Use !help to see command formats.")
    except Exception as exc:
        print(f"Command error ({command}): {exc}")

async def main():
    global client
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
            password = f.read().strip()
    except FileNotFoundError:
        raise RuntimeError("password.txt is missing. Create it and put your Matrix password inside.")
    if not password:
        raise RuntimeError("password.txt is empty.")

    client = AsyncClient(HOMESERVER, USER_ID)
    response = await client.login(password)
    if not hasattr(response, "access_token"):
        print(f"Login failed: {response}")
        await client.close()
        return

    print(f"Logged in as {USER_ID}")
    client.add_event_callback(on_message, RoomMessageText)
    try:
        await client.sync(timeout=30000)
        print("Sync complete; listening for commands.")
        await client.sync_forever(timeout=30000, full_state=True)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
