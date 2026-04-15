import discord
from discord.ext import commands
import asyncio
import os
import json
import uuid
import random
from dotenv import load_dotenv
from typecast import Typecast
from typecast.models import TTSRequest

# =====================
# 환경 설정
# =====================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TYPECAST_API_KEY = os.getenv("TYPECAST_API_KEY")

TEXT_CHANNEL_ID = 1490313438683992194
VOICE_CHANNEL_ID = 1488184603314225263

FFMPEG_PATH = r"C:\Users\USER\Desktop\metabot\메타봇 pro\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe"

client = Typecast(api_key=TYPECAST_API_KEY)

# =====================
# Discord
# =====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =====================
# JSON 로드/저장
# =====================
VOICE_FILE = "voices.json"
PROFILE_FILE = "profiles.json"

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

voices = load_json(VOICE_FILE)
profiles = load_json(PROFILE_FILE)

# =====================
# 프로필
# =====================
def get_profile(user_id):
    user_id = str(user_id)

    if user_id not in profiles:
        profiles[user_id] = {
            "voice": random.choice(list(voices.keys())) if voices else None
        }
        save_json(PROFILE_FILE, profiles)

    return profiles[user_id]

def save_profiles():
    save_json(PROFILE_FILE, profiles)

def get_voice_id(profile):
    return voices.get(profile.get("voice"))

# =====================
# TTS 생성
# =====================
async def make_tts(text, voice_id):
    filename = f"tts_{uuid.uuid4().hex}.wav"

    try:
        response = client.text_to_speech(
            TTSRequest(
                text=text,
                model="ssfm-v30",
                voice_id=voice_id
            )
        )

        with open(filename, "wb") as f:
            f.write(response.audio_data)

        return filename

    except Exception as e:
        print("TTS 실패:", e)
        return None

# =====================
# 음성 연결
# =====================
vc_lock = asyncio.Lock()

async def ensure_voice():
    async with vc_lock:
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)

        if vc and vc.is_connected():
            return vc

        return await channel.connect()

# =====================
# 큐 시스템
# =====================
queue = asyncio.Queue()

async def worker():
    while True:
        message, vc, profile = await queue.get()

        try:
            voice_id = get_voice_id(profile)

            if not voice_id:
                print("voice 없음")
                continue

            file = await make_tts(message.content, voice_id)

            if file:
                vc.play(discord.FFmpegPCMAudio(file, executable=FFMPEG_PATH))

                while vc.is_playing():
                    await asyncio.sleep(0.2)

                os.remove(file)

        except Exception as e:
            print("worker error:", e)

        queue.task_done()

# =====================
# 목록 포맷
# =====================
def range_text(arr):
    return f"{arr[0]} ~ {arr[-1]}" if arr else "없음"

def list_block():
    man = sorted([k for k in voices if k.startswith("man")])
    woman = sorted([k for k in voices if k.startswith("woman")])
    boy = sorted([k for k in voices if k.startswith("boy")])
    girl = sorted([k for k in voices if k.startswith("girl")])
    grandpa = sorted([k for k in voices if k.startswith("grandpa")])
    grandma = sorted([k for k in voices if k.startswith("grandma")])
    etc = sorted([k for k in voices if k.startswith("etc")])

    return "\n".join([
        "🎤 보이스 목록",
        "",
        f"👨 남자 ({range_text(man)})",
        f"👩 여자 ({range_text(woman)})",
        f"🧒 남자아이 ({range_text(boy)})",
        f"👧 여자아이 ({range_text(girl)})",
        f"👴 할아버지 ({range_text(grandpa)})",
        f"👵 할머니 ({range_text(grandma)})",
        f"🤖 기타 ({range_text(etc)})"
    ])

# =====================
# 명령어
# =====================
def handle_cmd(message):
    profile = get_profile(message.author.id)
    content = message.content.strip()

    # =====================
    # !tts
    # =====================
    if content == "!tts":
        return "\n".join([
            "🎤 TTS 사용법",
            "",
            "👉 !tts 설정 (voice)",
            "",
            list_block()
        ])


    # =====================
    # !tts 설정
    # =====================
    if content.startswith("!tts 설정"):
        key = content.replace("!tts 설정", "").strip()

        if key in voices:
            profile["voice"] = key
            save_profiles()
            return f"변경 완료: {key}"

        return "없는 보이스입니다"

    return None

# =====================
# 메시지 처리
# =====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != TEXT_CHANNEL_ID:
        return

    if message.content.startswith("!tts"):
        res = handle_cmd(message)
        if res:
            await message.channel.send("✅ " + res)
        return

    vc = await ensure_voice()
    if not vc:
        return

    profile = get_profile(message.author.id)

    await queue.put((message, vc, profile))

# =====================
# 시작
# =====================
@bot.event
async def on_ready():
    print("봇 로그인 완료")
    bot.loop.create_task(worker())

bot.run(TOKEN)