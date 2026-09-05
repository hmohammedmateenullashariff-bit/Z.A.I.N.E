"""
Z.A.I.N.E — YouTube Autonomous Content Generator (Multi-Genre Studio)
Produces high-retention viral YouTube Shorts (1080x1920, 9:16 vertical):
- Multi-Genre Support:
  * 🐱 Funny Cat Videos & Feline Memes (Cat logic, 3 AM zoomies, orange cat braincell)
  * 👶 Funny Child & Kids Humor (Toddler logic, silly kid excuses, bedtime negotiations)
  * ✨ Animated Cartoon Shorts (Benny the Sock, flying coffee beans, whimsical tales)
  * ⚡ Tech & AI Breakthroughs (Frontier models, Redis secrets, distributed systems)
- Neural Voiceover with genre-specific casting (Guy, Eric, Brian, Christopher)
- Word-level kinetic typography & subtitle synchronization via Faster-Whisper
- Procedural canvas styling tailored to each genre (paws, stars, cartoon frames, cyber grids)
- High-speed H.264/AAC MP4 video rendering via imageio-ffmpeg
"""

import asyncio
import os
import re
import json
import time
import random
import datetime
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "workspace" / "youtube_shorts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_binary() -> str:
    """Returns the path to the self-contained ffmpeg executable."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def detect_genre(topic: str = "", requested_genre: str = "") -> str:
    """Detects or normalizes the genre of content."""
    g = (requested_genre or "").strip().lower()
    if g in ("cat", "cats", "funny_cat", "funny_cats", "pet", "pets", "feline", "kitten"):
        return "cat"
    if g in ("kids", "kid", "child", "children", "toddler", "toddlers", "family", "parenting"):
        return "kids"
    if g in ("animated", "animation", "cartoon", "cartoons", "anime", "toon", "story", "tales"):
        return "animated"
    if g in ("tech", "technology", "ai", "coding", "code", "dev", "engineering"):
        return "tech"

    t = (topic or "").lower()
    if any(k in t for k in ("cat", "kitten", "meow", "feline", "zoomies", "purr", "litter", "orange cat")):
        return "cat"
    if any(k in t for k in ("kid", "child", "toddler", "children", "baby", "school", "bedtime", "mom", "dad")):
        return "kids"
    if any(k in t for k in ("animated", "cartoon", "toon", "sock", "dragon", "fairy", "adventure", "pixel")):
        return "animated"
    if any(k in t for k in ("ai", "code", "tech", "model", "python", "algorithm", "database", "claude", "gpt")):
        return "tech"

    return random.choice(["cat", "kids", "animated", "tech"])


# Curated high-retention script libraries per genre
GENRE_SCRIPTS = {
    "cat": [
        {
            "title": "Why Cats Sprint Like Demons at 3 AM #Shorts #Cats #FunnyAnimals",
            "topic": "The 3 AM Cat Zoomies",
            "badge": "🐾 3 AM CAT ZOOMIES",
            "voice": "en-US-GuyNeural",
            "tags": ["shorts", "cats", "funnycats", "catmemes", "pets", "funnyanimals", "catlover", "humor"],
            "script": (
                "Ever wonder why your cat suddenly turns into an Olympic sprinter at three in the morning? "
                "Scientists call it pent-up predatory energy, but any cat owner knows the real truth: "
                "they are fighting invisible dimensional dust bunnies! "
                "One minute your cat is sleeping peacefully like a fluffy angel, "
                "and the next, they are parkouring off the sofa and ricocheting across the hallway at Mach two. "
                "Rule number one: do not move your feet under the blanket, or your toes become collateral damage. "
                "Subscribe to Zaine Studio for more daily feline confessions!"
            ),
        },
        {
            "title": "Cat Law: The 5-Second Rule Does Not Apply To Humans #Shorts #CatMemes",
            "topic": "The Feline Law of Gravity",
            "badge": "🐱 CAT LOGIC 101",
            "voice": "en-US-GuyNeural",
            "tags": ["shorts", "cats", "catlogic", "catmemes", "funny", "pets", "relatable", "humor"],
            "script": (
                "Here are the unwritten universal laws of feline existence. "
                "Law number one: if you open a can of tuna anywhere within a five-mile radius, "
                "your cat instantly teleports into the kitchen out of thin air. "
                "Law number two: if a closed door exists anywhere in your house, it is a personal insult to your cat's royal dignity. "
                "And law number three: if it fits, they will sit, even if it is a shoebox made for a hamster! "
                "Like and subscribe if your cat is secretly the ruler of your household."
            ),
        },
        {
            "title": "What Your Cat Is Actually Thinking During Belly Rubs #Shorts #FunnyCats",
            "topic": "The Belly Rub Trap",
            "badge": "😹 CAT CONFESSIONS",
            "voice": "en-GB-RyanNeural",
            "tags": ["shorts", "cats", "catfacts", "funnycats", "pets", "comedy", "meow"],
            "script": (
                "Here is an exclusive translation of what your cat is thinking when they roll onto their back. "
                "Rub one: yes, this is quite acceptable human. "
                "Rub two: delightful, you are pleasing me. "
                "Rub two point five: warning, sensory threshold exceeded. "
                "Rub three: lethal defense protocol activated, deploying all four claws and razor teeth! "
                "It was never an invitation for affection, it was an elaborate tactical ambush. "
                "Hit subscribe for more classified cat secrets from Zaine Studio!"
            ),
        },
    ],
    "kids": [
        {
            "title": "The Undefeated World of Toddler Logic #Shorts #FunnyKids #Parenting",
            "topic": "Toddler Logic That Almost Makes Sense",
            "badge": "👶 TODDLER LOGIC",
            "voice": "en-US-EricNeural",
            "tags": ["shorts", "kids", "funnykids", "parenting", "familyhumor", "toddlerlogic", "comedy", "relatable"],
            "script": (
                "Toddler logic is completely undefeated in the history of human communication. "
                "You cut their sandwich into triangles? Instant tears, because today their heart was set on squares! "
                "You ask who ate all the strawberry frosting off the birthday cake? "
                "It wasn't them, even though their entire forehead is covered in bright pink frosting. "
                "It was clearly the invisible dog named Sparky who snuck into the kitchen. "
                "You simply cannot argue with that level of legal defense. "
                "Subscribe to Zaine Studio for your daily dose of family comedy!"
            ),
        },
        {
            "title": "Things Kids Say at Bedtime to Avoid Sleeping #Shorts #ParentingHumor",
            "topic": "The Bedtime Negotiation",
            "badge": "🎒 SILLY KID MOMENTS",
            "voice": "en-US-AnaNeural",
            "tags": ["shorts", "kids", "bedtime", "parenting", "family", "hilarious", "relatable"],
            "script": (
                "Bedtime is the exact moment when children suddenly turn into deep philosophical geniuses. "
                "All day long, they cannot remember where their shoes are. "
                "But the second their head touches the pillow at eight PM, they have urgent questions. "
                "Mom, does the moon get tired of following our car? "
                "Dad, do fish ever get thirsty while swimming in the ocean? "
                "And my personal favorite: my left elbow feels lonely, can I have five glasses of water? "
                "Subscribe to Zaine Studio if your kids are master bedtime negotiators!"
            ),
        },
        {
            "title": "Kindergarten Excuses That Are Absolute Masterpieces #Shorts #FunnyKids",
            "topic": "Creative School Excuses",
            "badge": "🍭 TINY HUMAN BRAIN",
            "voice": "en-US-EricNeural",
            "tags": ["shorts", "kids", "funnykids", "schoolhumor", "comedy", "funny", "smiles"],
            "script": (
                "Kindergarteners have an imagination that puts Hollywood screenwriters to shame. "
                "One kid told his teacher he couldn't do his coloring worksheet because his fingers went on strike for higher cookie wages. "
                "Another little girl claimed she didn't finish her green beans because green beans are actually tiny sleeping dragons. "
                "Honestly, with creativity like that, these kids are ready for boardroom executive positions already. "
                "Hit subscribe for more hilarious moments every single day!"
            ),
        },
    ],
    "animated": [
        {
            "title": "The Secret Life of Socks in the Washing Machine #Shorts #Animation #Toon",
            "topic": "The Missing Sock Dimension",
            "badge": "✨ ANIMATED TALES",
            "voice": "en-US-BrianNeural",
            "tags": ["shorts", "animation", "animatedshorts", "cartoon", "storytime", "toon", "creative", "fun"],
            "script": (
                "Have you ever wondered where that second sock disappears to in the laundry? "
                "Meet Benny, a bright blue sock with big dreams. "
                "Every laundry day, Benny watched his friends vanish into the spinning vortex of the dryer. "
                "One stormy afternoon, Benny leaped into the swirling vortex and discovered the portal! "
                "On the other side was a tropical paradise island where all missing socks live rent-free, drinking coconut juice! "
                "Subscribe to Zaine Studio to watch Benny's next animated adventure unfold!"
            ),
        },
        {
            "title": "The Little Coffee Bean That Wanted to Fly #Shorts #AnimatedStory",
            "topic": "The Flying Coffee Bean",
            "badge": "🎨 TOON STORIES",
            "voice": "en-GB-ThomasNeural",
            "tags": ["shorts", "animation", "animatedshorts", "cartoon", "coffee", "toon", "creative"],
            "script": (
                "Deep inside a bustling morning cafe, there lived an ambitious little espresso bean named Pip. "
                "While all the other beans were content taking a hot bubble bath in the French press, "
                "Pip strapped on a tiny pair of paper wings and aimed for the clouds! "
                "With one mighty burst of steam from the espresso machine, Pip launched into the stratosphere like a rocket! "
                "Never let anyone tell you your dreams are too small. "
                "Subscribe to Zaine Studio for more whimsical animated tales!"
            ),
        },
    ],
    "tech": [
        {
            "title": "Why Redis Is Insanely Fast: The Single-Threaded Secret #Shorts #Tech #AI",
            "topic": "Redis Single-Threaded Architecture",
            "badge": "⚡ TECH INTELLIGENCE",
            "voice": "en-US-ChristopherNeural",
            "tags": ["shorts", "technology", "artificial intelligence", "coding", "programming", "systemdesign"],
            "script": (
                "Did you know why Redis can handle over one hundred thousand queries per second on a single CPU core? "
                "Most junior developers think scaling requires dozens of complex multithreaded servers. "
                "In reality, by eliminating lock contention, using non-blocking I/O multiplexing, "
                "and keeping all critical state in pure memory, single-threaded engines crush bloated architectures. "
                "Master simplicity before adding distributed complexity. "
                "Subscribe to Zaine Studio for daily high-bandwidth engineering secrets!"
            ),
        }
    ],
}


def generate_viral_script(topic: str = "", genre: str = "auto") -> Dict[str, Any]:
    """
    Generates a high-retention YouTube Shorts script across genres:
    - 'cat': Funny Cat Videos & Memes
    - 'kids': Funny Child Content & Parenting Humor
    - 'animated': Whimsical Animated Stories & Cartoons
    - 'tech': AI Breakthroughs & High-Speed System Design
    """
    active_genre = detect_genre(topic=topic, requested_genre=genre)

    # 1. Check if we have daily AI news for tech
    if active_genre == "tech" and (not topic or not topic.strip()):
        try:
            import ai_daily_intel
            updates = ai_daily_intel.get_daily_ai_updates()
            if updates and len(updates) > 0:
                top_item = updates[0]
                t_title = top_item.get("title", "New Frontier Model Released")
                topic = f"AI Breakthrough: {t_title}"
                title = f"{topic} #Shorts #Tech #AI"
                if len(title) > 95:
                    title = title[:92] + "..."
                script_text = (
                    f"Artificial intelligence just took another massive leap forward with {t_title}! "
                    f"{top_item.get('summary', 'Frontier engineering has introduced breakthrough multi-step reasoning capabilities.')} "
                    "Engineers are seeing dramatic improvements in latency, code synthesis, and autonomous task execution. "
                    "The frontier is moving faster than ever before. "
                    "Subscribe to Zaine Studio for daily real-time AI intelligence."
                )
                return {
                    "genre": "tech",
                    "title": title,
                    "description": f"Here is what you need to know about {topic}! 🚀\n\nSubscribe to Zaine Studio for daily AI breakthroughs.\n\n#Shorts #Tech #AI #ArtificialIntelligence",
                    "tags": ["shorts", "technology", "ai", "artificial intelligence", "coding", "programming"],
                    "script": re.sub(r"[#*_`]", "", script_text).strip(),
                    "topic": topic,
                    "category_badge": "⚡ TECH INTELLIGENCE",
                    "voice": "en-US-ChristopherNeural",
                }
        except Exception:
            pass

    # 2. Pick from rich genre libraries
    genre_pool = GENRE_SCRIPTS.get(active_genre, GENRE_SCRIPTS["cat"])
    chosen = random.choice(genre_pool)

    # If custom topic provided, customize title
    title = chosen["title"]
    if topic and topic.strip() and topic.lower() not in title.lower():
        title = f"{topic} #Shorts #{active_genre.capitalize()}"
        if len(title) > 95:
            title = title[:92] + "..."

    description = f"""{title} 🌟

Welcome to Zaine Studio! Subscribe for daily funny shorts, hilarious pet moments, animated tales, and tech intelligence!

#{active_genre.capitalize()} #Shorts #Viral #Entertainment #ZaineStudio"""

    return {
        "genre": active_genre,
        "title": title,
        "description": description,
        "tags": chosen["tags"],
        "script": chosen["script"],
        "topic": chosen["topic"],
        "category_badge": chosen["badge"],
        "voice": chosen.get("voice", "en-US-ChristopherNeural"),
    }


async def synthesize_voiceover_async(text: str, output_wav_path: str, voice: str = "en-US-ChristopherNeural") -> bool:
    """Synthesizes high-clarity neural voiceover using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate="+5%", pitch="+0Hz")
    temp_mp3 = output_wav_path.replace(".wav", ".mp3")
    await communicate.save(temp_mp3)

    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [
        ffmpeg_bin, "-y", "-i", temp_mp3,
        "-ar", "24000", "-ac", "1", output_wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_mp3):
        try:
            os.remove(temp_mp3)
        except Exception:
            pass
    return True


def synthesize_voiceover(text: str, output_wav_path: str, voice: str = "en-US-ChristopherNeural") -> bool:
    """Synchronous wrapper for voiceover synthesis."""
    try:
        asyncio.run(synthesize_voiceover_async(text, output_wav_path, voice=voice))
        return True
    except Exception:
        try:
            import voice_synthesizer
            voice_synthesizer.synthesize_speech(text, output_path=output_wav_path)
            return True
        except Exception as e:
            print(f"Voiceover synthesis failed: {e}")
            return False


def extract_word_timestamps(wav_path: str) -> List[Tuple[str, float, float]]:
    """Uses Faster-Whisper to extract exact word-level start and end timestamps."""
    from faster_whisper import WhisperModel

    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(wav_path, word_timestamps=True)

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                clean_w = re.sub(r"[^\w\s'-]", "", w.word).strip().upper()
                if clean_w:
                    words.append((clean_w, round(w.start, 2), round(w.end, 2)))
        else:
            for piece in segment.text.split():
                clean_p = re.sub(r"[^\w\s'-]", "", piece).strip().upper()
                if clean_p:
                    words.append((clean_p, round(segment.start, 2), round(segment.end, 2)))

    return words


def get_audio_duration(wav_path: str) -> float:
    """Returns duration of audio file in seconds via wave module or ffmpeg."""
    import wave
    try:
        with wave.open(wav_path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 30.0


def draw_cat_paw(draw_obj: ImageDraw.ImageDraw, px: int, py: int, scale: float = 1.0, color: Tuple[int, int, int, int] = (255, 180, 80, 140)):
    """Draws a cute stylized cat paw print."""
    s = scale
    # Main pad
    draw_obj.ellipse([px - 20 * s, py - 14 * s, px + 20 * s, py + 18 * s], fill=color[:3])
    # 3 upper toes
    draw_obj.ellipse([px - 22 * s, py - 30 * s, px - 8 * s, py - 14 * s], fill=color[:3])
    draw_obj.ellipse([px - 7 * s, py - 36 * s, px + 7 * s, py - 20 * s], fill=color[:3])
    draw_obj.ellipse([px + 8 * s, py - 30 * s, px + 22 * s, py - 14 * s], fill=color[:3])


def draw_playful_star(draw_obj: ImageDraw.ImageDraw, sx: int, sy: int, size: int = 24, color: Tuple[int, int, int] = (255, 235, 60)):
    """Draws a cute 4-point cartoon star."""
    sz = size
    pts = [
        (sx, sy - sz), (sx + sz // 3, sy - sz // 3),
        (sx + sz, sy), (sx + sz // 3, sy + sz // 3),
        (sx, sy + sz), (sx - sz // 3, sy + sz // 3),
        (sx - sz, sy), (sx - sz // 3, sy - sz // 3),
    ]
    draw_obj.polygon(pts, fill=color)


def render_short_video(
    wav_path: str,
    output_mp4_path: str,
    words: List[Tuple[str, float, float]],
    badge_text: str = "⚡ TECH INTELLIGENCE",
    genre: str = "tech",
    fps: int = 24,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """
    Renders 1080x1920 vertical video tailored to the requested genre:
    - Dynamic gradient & thematic vector decorations
    - Top pill badge & channel header
    - Dynamic kinetic word-level subtitles (active word highlight)
    - Bottom genre-colored animated progress bar
    """
    duration = get_audio_duration(wav_path)
    total_frames = int(duration * fps)
    ffmpeg_bin = get_ffmpeg_binary()

    # Base background gradient tailored to genre
    bg_base = Image.new("RGB", (width, height), color=(10, 14, 26))
    draw_bg = ImageDraw.Draw(bg_base)

    if genre == "cat":
        # Warm sunset plum to rich coral amber
        for y in range(height):
            ratio = y / height
            r = int(38 + 50 * ratio)
            g = int(14 + 20 * ratio)
            b = int(48 - 10 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        # Pre-draw static decorative paw prints in background corners
        draw_cat_paw(draw_bg, 140, 360, scale=1.4, color=(255, 170, 70, 80))
        draw_cat_paw(draw_bg, width - 150, 420, scale=1.2, color=(255, 170, 70, 80))
        draw_cat_paw(draw_bg, 160, 1540, scale=1.3, color=(255, 170, 70, 80))
        draw_cat_paw(draw_bg, width - 160, 1500, scale=1.5, color=(255, 170, 70, 80))
        badge_border = (255, 185, 50)
        badge_bg = (50, 20, 40)
        badge_text_col = (255, 215, 60)
        active_word_col = (255, 215, 40)
        progress_col = (255, 140, 50)
        header_text = "ZAINE STUDIO • FELINE CHAOS & MEMES"
        cta_text = "SUBSCRIBE FOR DAILY FELINE CHAOS 🐾"

    elif genre == "kids":
        # Cheerful sky blue to bright turquoise
        for y in range(height):
            ratio = y / height
            r = int(15 + 15 * ratio)
            g = int(35 + 65 * ratio)
            b = int(75 + 40 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        # Pre-draw cute playful stars in corners
        draw_playful_star(draw_bg, 140, 360, size=32, color=(255, 235, 70))
        draw_playful_star(draw_bg, width - 160, 400, size=26, color=(255, 235, 70))
        draw_playful_star(draw_bg, 160, 1520, size=28, color=(255, 235, 70))
        draw_playful_star(draw_bg, width - 150, 1480, size=34, color=(255, 235, 70))
        badge_border = (255, 220, 50)
        badge_bg = (20, 45, 80)
        badge_text_col = (255, 240, 80)
        active_word_col = (255, 245, 50)
        progress_col = (255, 220, 50)
        header_text = "ZAINE STUDIO • FAMILY & KID HUMOR"
        cta_text = "SUBSCRIBE FOR DAILY FAMILY SMILES 🍭"

    elif genre == "animated":
        # Deep electric violet to rich magenta
        for y in range(height):
            ratio = y / height
            r = int(35 + 60 * ratio)
            g = int(10 + 15 * ratio)
            b = int(60 + 35 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        draw_playful_star(draw_bg, 140, 360, size=30, color=(255, 70, 180))
        draw_playful_star(draw_bg, width - 150, 410, size=25, color=(0, 240, 255))
        draw_playful_star(draw_bg, 150, 1520, size=28, color=(0, 240, 255))
        draw_playful_star(draw_bg, width - 160, 1500, size=32, color=(255, 70, 180))
        badge_border = (255, 30, 150)
        badge_bg = (40, 15, 60)
        badge_text_col = (255, 90, 200)
        active_word_col = (255, 255, 50)
        progress_col = (255, 30, 150)
        header_text = "ZAINE STUDIO • ANIMATED STORIES"
        cta_text = "SUBSCRIBE FOR DAILY ANIMATED TALES ✨"

    else:
        # Tech: Deep obsidian navy to midnight cyan
        for y in range(height):
            ratio = y / height
            r = int(8 + 12 * (1 - ratio))
            g = int(12 + 25 * ratio)
            b = int(24 + 48 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        badge_border = (0, 220, 255)
        badge_bg = (15, 30, 60)
        badge_text_col = (0, 240, 255)
        active_word_col = (255, 235, 50)
        progress_col = (0, 230, 255)
        header_text = "PROJECT Z • AUTONOMOUS INTELLIGENCE"
        cta_text = "SUBSCRIBE FOR DAILY BREAKTHROUGHS ⚡"

    # Font setup
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 46)
        font_badge = ImageFont.truetype("arialbd.ttf", 36)
        font_subtitle = ImageFont.truetype("arialbd.ttf", 72)
    except Exception:
        font_title = ImageFont.load_default()
        font_badge = ImageFont.load_default()
        font_subtitle = ImageFont.load_default()

    # Launch FFmpeg pipe
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-i", wav_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4_path,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    word_count = len(words)
    chunks = []
    chunk_size = 3
    for i in range(0, word_count, chunk_size):
        sub_words = words[i : i + chunk_size]
        start_t = sub_words[0][1]
        end_t = sub_words[-1][2]
        chunks.append({
            "words": sub_words,
            "start": start_t,
            "end": end_t,
        })

    for f in range(total_frames):
        curr_time = f / float(fps)
        frame = bg_base.copy()
        draw = ImageDraw.Draw(frame)

        # Ambient pulsing divider lines
        pulse = int(18 * (1.0 + np.sin(curr_time * 3.0)))
        draw.line([(0, 320), (width, 320)], fill=(badge_border[0], min(255, badge_border[1] + pulse), min(255, badge_border[2] + pulse)), width=3)
        draw.line([(0, 1600), (width, 1600)], fill=(badge_border[0], min(255, badge_border[1] + pulse), min(255, badge_border[2] + pulse)), width=3)

        # Top Category Badge (Pill button)
        badge_box = [width // 2 - 270, 210, width // 2 + 270, 280]
        draw.rounded_rectangle(badge_box, radius=35, fill=badge_bg, outline=badge_border, width=3)
        draw.text((width // 2, 245), badge_text, font=font_badge, fill=badge_text_col, anchor="mm")

        # Channel Branding Header
        draw.text((width // 2, 160), header_text, font=font_title, fill=(210, 220, 235), anchor="mm")

        # Kinetic Subtitles
        active_chunk = None
        for c in chunks:
            if c["start"] <= curr_time <= c["end"] + 0.35:
                active_chunk = c
                break

        if active_chunk:
            sub_y = height // 2 - 40
            active_word_str = ""
            for w_tuple in active_chunk["words"]:
                if w_tuple[1] <= curr_time <= w_tuple[2] + 0.15:
                    active_word_str = w_tuple[0]
                    break

            draw.rounded_rectangle([90, sub_y - 80, width - 90, sub_y + 120], radius=25, fill=(5, 10, 20, 190), outline=badge_border, width=2)

            words_in_chunk = active_chunk["words"]
            spacing = 25
            word_widths = [draw.textbbox((0, 0), w[0], font=font_subtitle)[2] for w in words_in_chunk]
            total_text_width = sum(word_widths) + spacing * (len(words_in_chunk) - 1)
            start_x = (width - total_text_width) // 2

            curr_x = start_x
            for w_tuple, w_w in zip(words_in_chunk, word_widths):
                is_active = (w_tuple[0] == active_word_str)
                text_color = active_word_col if is_active else (255, 255, 255)
                draw.text((curr_x + 3, sub_y + 3), w_tuple[0], font=font_subtitle, fill=(0, 0, 0))
                draw.text((curr_x, sub_y), w_tuple[0], font=font_subtitle, fill=text_color)
                curr_x += w_w + spacing

        # Bottom Animated Progress Bar
        bar_y = 1760
        bar_width = width - 160
        progress_ratio = min(1.0, curr_time / duration)
        draw.rounded_rectangle([80, bar_y, width - 80, bar_y + 14], radius=7, fill=(30, 40, 60))
        if progress_ratio > 0.01:
            draw.rounded_rectangle([80, bar_y, int(80 + bar_width * progress_ratio), bar_y + 14], radius=7, fill=progress_col)

        # Call to Action Text
        draw.text((width // 2, 1820), cta_text, font=font_title, fill=progress_col, anchor="mm")

        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()
    return output_mp4_path


def generate_youtube_short(
    topic: str = "",
    genre: str = "auto",
    upload_now: bool = False,
    use_higgsfield: bool = True,
) -> Dict[str, Any]:
    """
    Complete autonomous pipeline across genres:
    - 'cat': Funny Cat Videos & Memes
    - 'kids': Funny Child Content & Parenting Humor
    - 'animated': Whimsical Animated Stories & Cartoons
    - 'tech': AI Breakthroughs & High-Speed System Design
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = generate_viral_script(topic=topic, genre=genre)

    wav_path = str(OUTPUT_DIR / f"voiceover_{timestamp}.wav")
    mp4_path = str(OUTPUT_DIR / f"short_{timestamp}.mp4")
    json_path = str(OUTPUT_DIR / f"short_{timestamp}.json")

    # Thermal safety check
    try:
        import thermal_guard
        tel = thermal_guard.get_thermal_telemetry()
        if tel.get("temp_c", 0) > 85.0:
            print(f"[Content Generator] Warning: High CPU temperature ({tel.get('temp_c')}C). Throttling video render.")
            time.sleep(2)
    except Exception:
        pass

    print(f"1. Synthesizing voiceover [{meta['genre'].upper()}] for: '{meta['title']}'...")
    synthesize_voiceover(meta["script"], wav_path, voice=meta.get("voice", "en-US-ChristopherNeural"))

    print("2. Extracting word timestamps with Faster-Whisper...")
    words = extract_word_timestamps(wav_path)
    if not words:
        duration = get_audio_duration(wav_path)
        script_words = meta["script"].split()
        step = duration / max(1, len(script_words))
        words = [(w, i * step, (i + 1) * step) for i, w in enumerate(script_words)]

    # 3. Higgsfield AI b-roll generation (if enabled)
    if use_higgsfield:
        try:
            from .higgsfield_client import generate_higgsfield_video, has_higgsfield_credentials
            if has_higgsfield_credentials():
                # Tailor Higgsfield prompt based on genre
                if meta["genre"] == "cat":
                    hf_prompt = f"ultra-cute fluffy cat {meta['topic']}, comical expression, 3d pixar animation style, 9:16 vertical, vibrant lighting"
                elif meta["genre"] == "kids":
                    hf_prompt = f"whimsical cute cartoon toddler {meta['topic']}, colorful pixar style, 9:16 vertical, cheerful"
                elif meta["genre"] == "animated":
                    hf_prompt = f"vibrant 2D/3D cartoon animation {meta['topic']}, studio ghibli colors, 9:16 vertical"
                else:
                    hf_prompt = "cinematic futuristic neural network data stream, 8k, 9:16 vertical"

                print(f"[Higgsfield AI] Initiating cinematic video generation for '{hf_prompt[:60]}...'")
                generate_higgsfield_video(hf_prompt)
        except Exception as e:
            print(f"[Higgsfield AI] Notice: {e}")

    print(f"4. Rendering 1080x1920 Short video ({meta['genre'].upper()}) with kinetic captions ({len(words)} words)...")
    render_short_video(
        wav_path=wav_path,
        output_mp4_path=mp4_path,
        words=words,
        badge_text=meta.get("category_badge", "⚡ TECH INTELLIGENCE"),
        genre=meta.get("genre", "tech"),
    )

    duration = get_audio_duration(wav_path)
    file_size_mb = round(os.path.getsize(mp4_path) / (1024 * 1024), 2)

    result = {
        "status": "success",
        "genre": meta["genre"],
        "title": meta["title"],
        "description": meta["description"],
        "tags": meta["tags"],
        "video_path": mp4_path,
        "audio_path": wav_path,
        "metadata_path": json_path,
        "duration_sec": round(duration, 2),
        "file_size_mb": file_size_mb,
        "upload_status": "READY_FOR_UPLOAD",
        "uploaded": False,
        "created_at": datetime.datetime.now().isoformat(),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"[SUCCESS] YouTube Short successfully rendered: {mp4_path} ({file_size_mb} MB, {duration:.1f}s)")

    # 5. Handle immediate upload if requested
    if upload_now:
        try:
            from .uploader import upload_youtube_video
            up_res = upload_youtube_video(
                video_path=mp4_path,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
            )
            result["uploaded"] = (up_res.get("status") == "SUCCESS")
            result["upload_details"] = up_res
        except Exception as e:
            result["upload_error"] = str(e)

    return result
