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

FFMPEG_PATH = "ffmpeg"

client = Typecast(api_key=TYPECAST_API_KEY)

# =====================
# BOT
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
        print("🟡 TTS 요청:", text)

        response = client.text_to_speech(
            TTSRequest(
                text=text,
                model="ssfm-v30",
                voice_id=voice_id
            )
        )

        if not response.audio_data:
            print("❌ TTS 실패 (audio 없음)")
            return None

        with open(filename, "wb") as f:
            f.write(response.audio_data)

        print("🟢 TTS 생성 완료:", filename)
        return filename

    except Exception as e:
        print("❌ TTS ERROR:", e)
        return None

# =====================
# VOICE (핵심 안정화)
# =====================
vc_lock = asyncio.Lock()

async def ensure_voice():
    async with vc_lock:
        channel = bot.get_channel(VOICE_CHANNEL_ID)

        if not channel:
            print("❌ voice channel 없음")
            return None

        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)

        # ❗ 죽은 vc 제거
        if vc:
            if not vc.is_connected():
                try:
                    await vc.disconnect()
                except:
                    pass
                vc = None

        if vc is None:
            vc = await channel.connect()
            print("🔊 voice 새 연결")

        return vc

# =====================
# QUEUE
# =====================
queue = asyncio.Queue()

async def worker():
    print("🟢 worker 시작")

    while True:
        message, profile = await queue.get()

        try:
            print("📥 메시지:", message.content)

            voice_id = get_voice_id(profile)
            if not voice_id:
                print("❌ voice 없음")
                queue.task_done()
                continue

            file = await make_tts(message.content, voice_id)

            if not file:
                queue.task_done()
                continue

            vc = await ensure_voice()

            if not vc or not vc.is_connected():
                print("❌ voice 연결 실패")
                queue.task_done()
                continue

            # 🔥 중요: 재생 전 죽은 상태 체크
            if vc.is_playing():
                vc.stop()

            print("▶ 재생 시작")

            audio = discord.FFmpegPCMAudio(file, executable=FFMPEG_PATH)

            def after(err):
                if err:
                    print("❌ PLAY ERROR:", err)
                else:
                    print("✅ 재생 완료")

            vc.play(audio, after=after)

            while vc.is_playing():
                await asyncio.sleep(0.2)

            try:
                os.remove(file)
            except:
                pass

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
        return "🎤 !tts 설정 (voice)"

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

    profile = get_profile(message.author.id)

    await queue.put((message, profile))

# =====================
# START
# =====================
@bot.event
async def on_ready():
    print("봇 로그인 완료")
    bot.loop.create_task(worker())

bot.run(TOKEN)
