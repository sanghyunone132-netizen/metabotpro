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
# ENV
# =====================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TYPECAST_API_KEY = os.getenv("TYPECAST_API_KEY")

TEXT_CHANNEL_ID = 1490313438683992194
VOICE_CHANNEL_ID = 1488184603314225263

# Railway / Linux 대응 (로컬 경로 제거)
FFMPEG_PATH = "ffmpeg"

client = Typecast(api_key=TYPECAST_API_KEY)

# =====================
# Discord
# =====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =====================
# JSON
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
# PROFILE
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
# TTS
# =====================
async def make_tts(text, voice_id):
    filename = f"tts_{uuid.uuid4().hex}.wav"

    try:
        print("TTS 요청:", text)

        response = client.text_to_speech(
            TTSRequest(
                text=text,
                model="ssfm-v30",
                voice_id=voice_id
            )
        )

        if not response.audio_data:
            print("❌ TTS 실패: audio_data 없음")
            return None

        with open(filename, "wb") as f:
            f.write(response.audio_data)

        print("✅ TTS 생성:", filename)
        return filename

    except Exception as e:
        print("❌ TTS ERROR:", e)
        return None

# =====================
# VOICE
# =====================
vc_lock = asyncio.Lock()

async def ensure_voice():
    async with vc_lock:
        channel = bot.get_channel(VOICE_CHANNEL_ID)

        if not channel:
            print("❌ voice channel 없음")
            return None

        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)

        if vc and vc.is_connected():
            return vc

        vc = await channel.connect()
        print("🔊 voice connect 완료")

        return vc

# =====================
# QUEUE
# =====================
queue = asyncio.Queue()

async def worker():
    print("🟢 worker 시작됨")

    while True:
        message, vc, profile = await queue.get()

        try:
            print("📥 queue 받음:", message.content)

            voice_id = get_voice_id(profile)
            print("🎤 voice_id:", voice_id)

            if not voice_id:
                print("❌ voice 없음")
                queue.task_done()
                continue

            file = await make_tts(message.content, voice_id)

            if file and vc and vc.is_connected():

                print("▶ 재생 시작:", file)

                audio = discord.FFmpegPCMAudio(file, executable=FFMPEG_PATH)

                def after(err):
                    if err:
                        print("❌ PLAY ERROR:", err)
                    else:
                        print("✅ 재생 완료")

                vc.play(audio, after=after)

                while vc.is_playing():
                    await asyncio.sleep(0.2)

                os.remove(file)

            else:
                print("❌ play 실패 (file or vc 문제)")

        except Exception as e:
            print("❌ worker error:", e)

        queue.task_done()

# =====================
# CMD
# =====================
def handle_cmd(message):
    profile = get_profile(message.author.id)
    content = message.content.strip()

    if content == "!tts":
        return "🎤 !tts 설정 (voice)\n\n보이스 목록은 voices.json"

    if content.startswith("!tts 설정"):
        key = content.replace("!tts 설정", "").strip()

        if key in voices:
            profile["voice"] = key
            save_profiles()
            return f"변경 완료: {key}"

        return "없는 보이스"

    return None

# =====================
# MESSAGE
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
# START
# =====================
@bot.event
async def on_ready():
    print("봇 로그인 완료")
    bot.loop.create_task(worker())

bot.run(TOKEN)
