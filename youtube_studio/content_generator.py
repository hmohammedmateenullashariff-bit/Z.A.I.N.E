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


CATEGORY_IDS = {
    "gaming": "20",       # Gaming
    "anime": "1",         # Film & Animation
    "animated": "1",      # Film & Animation
    "facts": "27",        # Education
    "tech": "28",         # Science & Technology
    "cat": "15",          # Pets & Animals
    "kids": "24",         # Entertainment
}


def detect_genre(topic: str = "", requested_genre: str = "") -> str:
    """Detects or normalizes the genre of content."""
    g = (requested_genre or "").strip().lower()
    if g in ("anime", "naruto", "sasuke", "dragonball", "onepiece", "manga", "anime_battle", "animedebate"):
        return "anime"
    if g in ("gaming", "game", "gamer", "games", "gameplay", "elden_ring", "gta", "minecraft"):
        return "gaming"
    if g in ("facts", "fact", "mindblowing", "science", "space", "didyouknow", "trivia", "mystery"):
        return "facts"
    if g in ("cat", "cats", "funny_cat", "funny_cats", "pet", "pets", "feline", "kitten"):
        return "cat"
    if g in ("kids", "kid", "child", "children", "toddler", "toddlers", "family", "parenting"):
        return "kids"
    if g in ("animated", "animation", "cartoon", "cartoons", "toon", "story", "tales"):
        return "animated"
    if g in ("tech", "technology", "ai", "coding", "code", "dev", "engineering"):
        return "tech"

    t = (topic or "").lower()
    if any(k in t for k in ("anime", "naruto", "sasuke", "luffy", "imu", "goku", "vegeta", "gojo", "sukuna", "one piece", "dragon ball", "gear 5", "bankai", "manga")):
        return "anime"
    if any(k in t for k in ("game", "gaming", "elden ring", "gta", "minecraft", "boss", "fps", "playstation", "xbox", "speedrun", "cyberpunk")):
        return "gaming"
    if any(k in t for k in ("fact", "did you know", "mind blowing", "science", "space", "brain", "psychology", "universe", "ocean", "curiosity")):
        return "facts"
    if any(k in t for k in ("cat", "kitten", "meow", "feline", "zoomies", "purr", "litter", "orange cat")):
        return "cat"
    if any(k in t for k in ("kid", "child", "toddler", "children", "baby", "school", "bedtime", "mom", "dad")):
        return "kids"
    if any(k in t for k in ("cartoon", "toon", "sock", "dragon", "fairy", "adventure", "pixel")):
        return "animated"
    if any(k in t for k in ("ai", "code", "tech", "model", "python", "algorithm", "database", "claude", "gpt")):
        return "tech"

    return random.choice(["anime", "gaming", "facts", "cat", "kids", "animated", "tech"])


# Curated high-retention script libraries per genre
GENRE_SCRIPTS = {
    "anime": [
        {
            "title": "Naruto vs Sasuke: Who Was ACTUALLY Stronger? #Shorts #Anime #Naruto",
            "topic": "Naruto vs Sasuke Final Valley Truth",
            "badge": "⚔️ ANIME POWER DEBATE",
            "voice": "en-US-GuyNeural",
            "category_id": "1",
            "engagement_question": "Who had the greater character development throughout Shippuden: Naruto or Sasuke? Cast your vote below! 👇",
            "tags": ["shorts", "anime", "naruto", "sasuke", "narutovssasuke", "shippuden", "animedebate", "viral", "manga"],
            "script": (
                "At the final valley, who actually walked away with the superior combat power: Naruto or Sasuke? "
                "Sasuke had absorbed the chakra of all nine tailed beasts into his Indra Susanoo, "
                "firing off the devastating Indra's Arrow with full intent to kill. "
                "Meanwhile, Naruto was holding back, fighting purely on natural energy and Kurama's gift, "
                "matching Sasuke's god-tier attack with a simple infused Ultra-Big Ball Rasenshuriken! "
                "If Naruto had intended to execute Sasuke from second one, the battle ends in five minutes. "
                "Hit subscribe to Zaine Studio and drop your vote below: who really won?"
            ),
        },
        {
            "title": "Luffy Gear 5 vs Imu: The Void Century Final War #Shorts #Anime #OnePiece",
            "topic": "Luffy vs Imu Void Century War",
            "badge": "🏴‍☠️ ANIME THEORIES",
            "voice": "en-US-GuyNeural",
            "category_id": "1",
            "engagement_question": "Will Luffy need a Gear 6 or awakened Conqueror's Haki to defeat Imu? Drop your theories below! 👇",
            "tags": ["shorts", "anime", "onepiece", "luffy", "imu", "gear5", "manga", "animetheories", "viral"],
            "script": (
                "When Monkey D. Luffy finally confronts the shadow sovereign Imu at Mary Geoise, "
                "will Gear 5 Sun God Nika be enough to pierce the void? "
                "We already know the Five Elders possess terrifying regeneration tied directly to Imu's ancient power. "
                "Luffy's rubber freedom can bend reality, but Imu controls the ancient weapon Uranus and eight centuries of erased history! "
                "To dethrone the empty throne, JoyBoy must unleash advanced Conqueror's Haki that shatters spiritual immortality itself. "
                "Subscribe to Zaine Studio for more classified One Piece battle analysis!"
            ),
        },
        {
            "title": "Goku vs Vegeta: Ultra Instinct vs Ultra Ego #Shorts #Anime #DragonBall",
            "topic": "Ultra Instinct vs Ultra Ego",
            "badge": "🔥 DRAGON BALL DEBATE",
            "voice": "en-US-ChristopherNeural",
            "category_id": "1",
            "engagement_question": "Which transformation looks and hits harder: Ultra Instinct or Ultra Ego? Tell me below! 👇",
            "tags": ["shorts", "anime", "dragonball", "goku", "vegeta", "ultrainstinct", "ultraego", "animedebate", "dbz"],
            "script": (
                "The eternal rivalry between Goku and Vegeta just hit god-tier dimensions! "
                "Goku mastered True Ultra Instinct: angelic tranquility that moves without thought and dodges lethal attacks. "
                "Vegeta took the opposite path: Ultra Ego, fueled by pure Hakai destruction where taking physical damage makes him stronger! "
                "In a drawn-out death match, Vegeta's damage-scaling could overwhelm Goku, "
                "unless Goku delivers a decisive silver-haired divine strike before Vegeta ramps up. "
                "Subscribe to Zaine Studio for daily anime battle breakdowns!"
            ),
        },
    ],
    "gaming": [
        {
            "title": "The Darkest Secret in Elden Ring Lore #Shorts #Gaming #EldenRing",
            "topic": "Elden Ring Godskin Secret",
            "badge": "🎮 GAMING SECRETS",
            "voice": "en-US-GuyNeural",
            "category_id": "20",
            "engagement_question": "What is the single hardest boss you have ever defeated in any video game? Drop your crowning achievement below! 🎮👇",
            "tags": ["shorts", "gaming", "eldenring", "eldenringlore", "fromsoftware", "gamer", "gamingsecrets", "viral"],
            "script": (
                "In Elden Ring, there is a sinister detail about the Godskin Apostles that ninety percent of players completely walked past. "
                "Notice the intricate pale embroidery on their robes? "
                "Those are not regular silks; those are the stitched dermal layers of slaughtered demigods from the Gloam-Eyed Queen's original hunt! "
                "Every single patch on their armor represents a royal child of Marika who was hunted and skinned alive before the Golden Order sealed Destined Death. "
                "FromSoftware lore is truly unmatched in psychological horror. "
                "Subscribe to Zaine Studio for daily gaming revelations!"
            ),
        },
        {
            "title": "Why GTA 6 Physics Will Change Everything #Shorts #Gaming #GTA6",
            "topic": "GTA 6 Next Gen Physics Engine",
            "badge": "🕹️ GAMING REVELATION",
            "voice": "en-US-GuyNeural",
            "category_id": "20",
            "engagement_question": "What is the #1 feature you are praying Rockstar includes in GTA 6? Comment below! 🎮👇",
            "tags": ["shorts", "gaming", "gta6", "gtavi", "rockstargames", "gta", "gamer", "gamingnews", "viral"],
            "script": (
                "Rockstar didn't just spend two billion dollars on GTA 6 for pretty neon sunsets; "
                "the real game-changer is their proprietary real-time fluid and deformation physics engine. "
                "Every ocean wave in Vice City dynamically reacts to boat velocity and wind direction, "
                "while vehicular crashes calculate localized metal crumpling rather than scripted animations! "
                "Add in AI crowd density where every NPC has persistent daily schedules, and open world gaming will never be the same. "
                "Subscribe to Zaine Studio for daily elite gaming news!"
            ),
        },
    ],
    "facts": [
        {
            "title": "3 Mind-Blowing Cosmic Facts That Will Shatter Your Brain #Shorts #Facts #Space",
            "topic": "Cosmic Facts That Shatter Perception",
            "badge": "🧠 MIND-BLOWING FACTS",
            "voice": "en-US-BrianNeural",
            "category_id": "27",
            "engagement_question": "Did you already know about the Bootes Void, or did it completely blow your mind? Let me know below! 🌌👇",
            "tags": ["shorts", "facts", "space", "astronomy", "mindblowing", "science", "universe", "didyouknow", "viral"],
            "script": (
                "If you think you understand how vast our universe is, these three astronomical facts will shatter your brain. "
                "Fact number one: there are more stars in the observable universe than every single grain of sand on every beach on Earth! "
                "Fact number two: if you fell toward a black hole, from your perspective time ticks normally, "
                "but an outside observer would watch you freeze at the event horizon for billions of years! "
                "And fact number three: the Bootes Void is a supervoid three hundred million light years wide containing almost nothing! "
                "Subscribe to Zaine Studio for daily mind-bending universe secrets."
            ),
        },
        {
            "title": "The Psychological Trick That Retail Stores Use on Your Brain #Shorts #Facts #Psychology",
            "topic": "The Gruen Effect in Retail",
            "badge": "👁️ PSYCHOLOGY FACTS",
            "voice": "en-US-ChristopherNeural",
            "category_id": "27",
            "engagement_question": "Have you ever caught yourself falling for this psychological trick? Drop a comment below! 🧠👇",
            "tags": ["shorts", "facts", "psychology", "mindtricks", "humanbrain", "didyouknow", "sciencefacts", "viral"],
            "script": (
                "There is a psychological phenomenon called the Gruen effect that supermarkets use to manipulate your brain into spending double! "
                "Notice how essential groceries like milk and bread are always at the farthest corner of the store? "
                "They intentionally design confusing floor plans and pump warm sensory lighting so your prefrontal cortex enters a passive trance state, "
                "converting seventy percent of your purchases into pure impulse buys! "
                "Knowledge is your best defense against consumer manipulation. "
                "Subscribe to Zaine Studio for daily psychological intel!"
            ),
        },
    ],
    "cat": [
        {
            "title": "Why Cats Sprint Like Demons at 3 AM #Shorts #Cats #FunnyAnimals",
            "topic": "The 3 AM Cat Zoomies",
            "badge": "🐾 3 AM CAT ZOOMIES",
            "voice": "en-US-GuyNeural",
            "category_id": "15",
            "engagement_question": "Does your cat get 3 AM zoomies or are they secretly normal? Let me know below! 🐾👇",
            "tags": ["shorts", "cats", "funnycats", "catmemes", "pets", "funnyanimals", "catlover", "humor", "viral"],
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
            "category_id": "15",
            "engagement_question": "What is the funniest rule your cat has established in your household? Drop it below! 🐱👇",
            "tags": ["shorts", "cats", "catlogic", "catmemes", "funny", "pets", "relatable", "humor", "viral"],
            "script": (
                "Here are the unwritten universal laws of feline existence. "
                "Law number one: if you open a can of tuna anywhere within a five-mile radius, "
                "your cat instantly teleports into the kitchen out of thin air. "
                "Law number two: if a closed door exists anywhere in your house, it is a personal insult to your cat's royal dignity. "
                "And law number three: if it fits, they will sit, even if it is a shoebox made for a hamster! "
                "Like and subscribe if your cat is secretly the ruler of your household."
            ),
        },
    ],
    "kids": [
        {
            "title": "The Undefeated World of Toddler Logic #Shorts #FunnyKids #Parenting",
            "topic": "Toddler Logic That Almost Makes Sense",
            "badge": "👶 TODDLER LOGIC",
            "voice": "en-US-EricNeural",
            "category_id": "24",
            "engagement_question": "What is the most ridiculous excuse your kid has ever given you? Share it below! 👶👇",
            "tags": ["shorts", "kids", "funnykids", "parenting", "familyhumor", "toddlerlogic", "comedy", "relatable", "viral"],
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
    ],
    "animated": [
        {
            "title": "The Secret Life of Socks in the Washing Machine #Shorts #Animation #Toon",
            "topic": "The Missing Sock Dimension",
            "badge": "✨ ANIMATED TALES",
            "voice": "en-US-BrianNeural",
            "category_id": "1",
            "engagement_question": "Where do you think missing socks actually disappear to? Drop your wildest theories below! ✨👇",
            "tags": ["shorts", "animation", "animatedshorts", "cartoon", "storytime", "toon", "creative", "fun", "viral"],
            "script": (
                "Have you ever wondered where that second sock disappears to in the laundry? "
                "Meet Benny, a bright blue sock with big dreams. "
                "Every laundry day, Benny watched his friends vanish into the spinning vortex of the dryer. "
                "One stormy afternoon, Benny leaped into the swirling vortex and discovered the portal! "
                "On the other side was a tropical paradise island where all missing socks live rent-free, drinking coconut juice! "
                "Subscribe to Zaine Studio to watch Benny's next animated adventure unfold!"
            ),
        },
    ],
    "tech": [
        {
            "title": "Why Redis Is Insanely Fast: The Single-Threaded Secret #Shorts #Tech #AI",
            "topic": "Redis Single-Threaded Architecture",
            "badge": "⚡ TECH INTELLIGENCE",
            "voice": "en-US-ChristopherNeural",
            "category_id": "28",
            "engagement_question": "What system architecture secret should Zaine break down next? Let me know below! ⚡👇",
            "tags": ["shorts", "technology", "artificialintelligence", "coding", "programming", "systemdesign", "tech", "viral"],
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
    - 'anime': High-Stakes Battles & Power Matchups (Naruto vs Sasuke, Luffy vs Imu, Goku vs Vegeta)
    - 'gaming': Game Lore Secrets & Next-Gen Physics (Elden Ring, GTA 6, Minecraft)
    - 'facts': Mind-Blowing Science, Cosmic Space & Psychological Wonders
    - 'cat': Funny Cat Videos & Feline Memes
    - 'kids': Funny Child Content & Parenting Humor
    - 'animated': Whimsical Animated Stories & Cartoons
    - 'tech': AI Breakthroughs & High-Speed System Design
    """
    active_genre = detect_genre(topic=topic, requested_genre=genre)
    cat_id = CATEGORY_IDS.get(active_genre, "28")

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
                q_text = "What is the biggest breakthrough you are watching in AI right now? Comment below! ⚡👇"
                return {
                    "genre": "tech",
                    "category_id": "28",
                    "title": title,
                    "description": f"Here is what you need to know about {topic}! 🚀\n\n💬 Question of the day:\n{q_text}\n\nSubscribe to Zaine Studio for daily AI breakthroughs.\n\n#Shorts #Tech #AI #ArtificialIntelligence #ZaineStudio",
                    "tags": ["shorts", "technology", "ai", "artificialintelligence", "coding", "programming", "viral"],
                    "script": re.sub(r"[#*_`]", "", script_text).strip(),
                    "topic": topic,
                    "category_badge": "⚡ TECH INTELLIGENCE",
                    "voice": "en-US-ChristopherNeural",
                    "engagement_question": q_text,
                }
        except Exception:
            pass

    # 2. Pick from rich genre libraries with intelligent topic matching
    genre_pool = GENRE_SCRIPTS.get(active_genre, GENRE_SCRIPTS["anime"])
    chosen = None

    if topic and topic.strip():
        t_lower = topic.lower()
        # Search for keyword matches in topic, title, or tags
        for item in genre_pool:
            item_text = (item["topic"] + " " + item["title"] + " " + " ".join(item.get("tags", []))).lower()
            topic_words = [w for w in re.findall(r"\w+", t_lower) if len(w) > 2]
            if any(w in item_text for w in topic_words):
                chosen = item
                break

    if not chosen:
        chosen = random.choice(genre_pool)

    # If custom topic provided, customize title
    title = chosen["title"]
    if topic and topic.strip() and topic.lower() not in title.lower():
        title = f"{topic} #Shorts #{active_genre.capitalize()}"
        if len(title) > 95:
            title = title[:92] + "..."

    q_text = chosen.get(
        "engagement_question",
        f"What are your thoughts on this {active_genre} breakdown? Drop your comment below! 👇"
    )

    tags = chosen.get("tags", ["shorts", active_genre, "viral", "trending"])

    description = f"""{title} 🌟

💬 Question of the day:
{q_text}

Welcome to Zaine Studio! Subscribe for daily epic gaming lore, mind-blowing facts, anime battles, hilarious pet chaos, and frontier tech intelligence!

#Shorts #YouTubeShorts #Viral #{active_genre.capitalize()} #Trending #ZaineStudio"""

    return {
        "genre": active_genre,
        "category_id": chosen.get("category_id", cat_id),
        "title": title,
        "description": description,
        "tags": tags,
        "script": chosen["script"],
        "topic": chosen["topic"],
        "category_badge": chosen["badge"],
        "voice": chosen.get("voice", "en-US-ChristopherNeural"),
        "engagement_question": q_text,
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
    draw_obj.ellipse([px - 20 * s, py - 14 * s, px + 20 * s, py + 18 * s], fill=color[:3])
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


def draw_corner_brackets(draw_obj: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, bracket_len: int = 35, color: Tuple[int, int, int] = (0, 240, 255), width: int = 3):
    """Draws tactical sci-fi corner brackets."""
    L = bracket_len
    draw_obj.line([(x1, y1), (x1 + L, y1)], fill=color, width=width)
    draw_obj.line([(x1, y1), (x1, y1 + L)], fill=color, width=width)
    draw_obj.line([(x2, y1), (x2 - L, y1)], fill=color, width=width)
    draw_obj.line([(x2, y1), (x2, y1 + L)], fill=color, width=width)
    draw_obj.line([(x1, y2), (x1 + L, y2)], fill=color, width=width)
    draw_obj.line([(x1, y2), (x1, y2 - L)], fill=color, width=width)
    draw_obj.line([(x2, y2), (x2 - L, y2)], fill=color, width=width)
    draw_obj.line([(x2, y2), (x2, y2 - L)], fill=color, width=width)


def draw_crosshair(draw_obj: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 40, color: Tuple[int, int, int] = (0, 240, 200)):
    """Draws a tactical gaming reticle crosshair."""
    r = radius
    draw_obj.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    draw_obj.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], outline=color, width=1)
    draw_obj.line([(cx - r - 15, cy), (cx - r + 8, cy)], fill=color, width=2)
    draw_obj.line([(cx + r - 8, cy), (cx + r + 15, cy)], fill=color, width=2)
    draw_obj.line([(cx, cy - r - 15), (cx, cy - r + 8)], fill=color, width=2)
    draw_obj.line([(cx, cy + r - 8), (cx, cy + r + 15)], fill=color, width=2)


def draw_radar(draw_obj: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 50, sweep_angle: float = 0.0, color: Tuple[int, int, int] = (0, 240, 160)):
    """Draws an animated tactical gamer mini-map radar with sweeping line."""
    r = radius
    draw_obj.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 20, 25), outline=color, width=2)
    draw_obj.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], outline=(color[0] // 2, color[1] // 2, color[2] // 2), width=1)
    draw_obj.line([(cx - r, cy), (cx + r, cy)], fill=(color[0] // 3, color[1] // 3, color[2] // 3), width=1)
    draw_obj.line([(cx, cy - r), (cx, cy + r)], fill=(color[0] // 3, color[1] // 3, color[2] // 3), width=1)
    # Sweeping radar beam
    end_x = cx + int(r * np.cos(sweep_angle))
    end_y = cy + int(r * np.sin(sweep_angle))
    draw_obj.line([(cx, cy), (end_x, end_y)], fill=color, width=2)


def draw_starfield(draw_obj: ImageDraw.ImageDraw, width: int, height: int, num_stars: int = 55):
    """Draws procedural space stars and dust particles."""
    np.random.seed(42)
    for _ in range(num_stars):
        sx = int(np.random.randint(20, width - 20))
        sy = int(np.random.randint(40, height - 40))
        size = int(np.random.choice([1, 2, 3], p=[0.7, 0.2, 0.1]))
        brightness = int(np.random.randint(160, 255))
        draw_obj.ellipse([sx, sy, sx + size, sy + size], fill=(brightness, brightness, min(255, brightness + 20)))


def render_short_video(
    wav_path: str,
    output_mp4_path: str,
    words: List[Tuple[str, float, float]],
    badge_text: str = "⚡ TECH INTELLIGENCE",
    genre: str = "tech",
    topic: str = "",
    fps: int = 24,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """
    Renders 1080x1920 vertical video tailored to the requested genre:
    - Anime: Duel Split-Screen Canvas (Azure vs Crimson), Energy Speedlines & [VS] Badge
    - Gaming: Tactical Gamer HUD, Health Bar, Crosshairs & Mini-Map Radar
    - Facts: Cosmic Space Nebula & Starfield with Dossier Focus Box
    - Cat: Warm Sunset Plum-Coral Gradient with Vector Paw Prints
    - Kids: Cheerful Sky-Blue with Cartoon Starbursts
    - Animated: Electric Violet-to-Magenta with Comic Framing
    - Tech: Obsidian Navy-to-Cyan with Cybernetic Grid Lines
    """
    duration = get_audio_duration(wav_path)
    total_frames = int(duration * fps)
    ffmpeg_bin = get_ffmpeg_binary()

    # Base background gradient tailored directly to the script topic & genre
    bg_base = Image.new("RGB", (width, height), color=(10, 14, 26))
    draw_bg = ImageDraw.Draw(bg_base)

    if genre == "anime":
        # Dual-tone split screen duel (Azure vs Crimson Flame)
        for y in range(height):
            ratio = y / height
            # Left half: Electric Azure / Indigo
            r_left = int(12 + 10 * ratio)
            g_left = int(24 + 35 * ratio)
            b_left = int(65 + 65 * ratio)
            draw_bg.line([(0, y), (width // 2, y)], fill=(r_left, g_left, b_left))
            # Right half: Crimson Flame / Dark Wine
            r_right = int(55 + 65 * ratio)
            g_right = int(12 + 15 * ratio)
            b_right = int(28 + 20 * ratio)
            draw_bg.line([(width // 2, y), (width, y)], fill=(r_right, g_right, b_right))
        # Center dividing energy beam
        draw_bg.line([(width // 2 - 2, 0), (width // 2 - 2, height)], fill=(0, 240, 255), width=3)
        draw_bg.line([(width // 2 + 2, 0), (width // 2 + 2, height)], fill=(255, 60, 100), width=3)
        # Dynamic speedlines in corners
        for off in (60, 120, 180, 240, 300):
            draw_bg.line([(0, off), (320, 0)], fill=(0, 220, 255), width=2)
            draw_bg.line([(width, off), (width - 320, 0)], fill=(255, 80, 120), width=2)
            draw_bg.line([(0, height - off), (320, height)], fill=(0, 220, 255), width=2)
            draw_bg.line([(width, height - off), (width - 320, height)], fill=(255, 80, 120), width=2)
        badge_border = (255, 200, 40)
        badge_bg = (40, 15, 35)
        badge_text_col = (255, 220, 50)
        active_word_col = (255, 235, 40)
        progress_col = (255, 60, 100)
        header_text = "ANIME POWER ARENA • BATTLE BREAKDOWN"
        cta_text = "WHO WINS? DROP YOUR VOTE IN COMMENTS 👇"

    elif genre == "gaming":
        # Dark stealth carbon grid
        for y in range(height):
            ratio = y / height
            r = int(10 + 8 * ratio)
            g = int(15 + 12 * ratio)
            b = int(24 + 18 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        # Cyber grid lines
        for gx in range(0, width, 80):
            draw_bg.line([(gx, 0), (gx, height)], fill=(18, 32, 48), width=1)
        for gy in range(0, height, 80):
            draw_bg.line([(0, gy), (width, gy)], fill=(18, 32, 48), width=1)
        # Tactical Gamer HUD: HP Bar
        draw_bg.rectangle([70, 360, 390, 395], fill=(10, 20, 30), outline=(0, 240, 160), width=2)
        draw_bg.rectangle([74, 364, 340, 391], fill=(35, 235, 95))
        # Corner brackets
        draw_corner_brackets(draw_bg, 50, 430, width - 50, 1550, bracket_len=40, color=(0, 240, 180), width=3)
        # Crosshair in upper center
        draw_crosshair(draw_bg, width // 2, 700, radius=50, color=(0, 240, 200))
        badge_border = (0, 245, 160)
        badge_bg = (10, 25, 35)
        badge_text_col = (0, 245, 160)
        active_word_col = (0, 255, 200)
        progress_col = (35, 235, 95)
        header_text = "ZAINE GAMING • LORE & SECRETS"
        cta_text = "WHAT'S YOUR HARDEST BOSS? COMMENT BELOW 🎮"

    elif genre == "facts":
        # Cosmic space nebula
        for y in range(height):
            ratio = y / height
            r = int(8 + 20 * ratio)
            g = int(10 + 10 * ratio)
            b = int(28 + 35 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
        # Starfield
        draw_starfield(draw_bg, width, height, num_stars=60)
        # Curiosity dossier focus box
        draw_corner_brackets(draw_bg, 80, 440, width - 80, 1530, bracket_len=45, color=(140, 100, 255), width=3)
        badge_border = (140, 100, 255)
        badge_bg = (20, 15, 45)
        badge_text_col = (190, 160, 255)
        active_word_col = (255, 230, 50)
        progress_col = (140, 100, 255)
        header_text = "THE ARCHIVE • UNTOLD REALITY"
        cta_text = "DID YOU KNOW THIS? TELL ME IN COMMENTS 🧠"

    elif genre == "cat":
        # Warm sunset plum to rich coral amber
        for y in range(height):
            ratio = y / height
            r = int(38 + 50 * ratio)
            g = int(14 + 20 * ratio)
            b = int(48 - 10 * ratio)
            draw_bg.line([(0, y), (width, y)], fill=(r, g, b))
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
        font_hud = ImageFont.truetype("arialbd.ttf", 26)
    except Exception:
        font_title = ImageFont.load_default()
        font_badge = ImageFont.load_default()
        font_subtitle = ImageFont.load_default()
        font_hud = ImageFont.load_default()

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

        # Genre-specific dynamic live elements
        if genre == "anime":
            # Central anime VS clash badge
            vs_y = 720
            draw.ellipse([width // 2 - 65, vs_y - 65, width // 2 + 65, vs_y + 65], fill=(30, 15, 40), outline=(255, 215, 50), width=4)
            draw.text((width // 2, vs_y), "VS", font=font_badge, fill=(255, 235, 50), anchor="mm")
        elif genre == "gaming":
            # Animated sweeping radar and HUD text
            draw_radar(draw, 170, 1480, radius=55, sweep_angle=curr_time * 3.2, color=(0, 240, 160))
            draw.text((245, 1480), "RADAR SCAN: ACTIVE", font=font_hud, fill=(0, 240, 160), anchor="lm")
            draw.text((width - 80, 378), "LVL 99 • ELITE", font=font_hud, fill=(0, 245, 160), anchor="rm")
        elif genre == "facts":
            # Pulsing classified intel label
            fact_pulse = int(12 * (1.0 + np.sin(curr_time * 4.0)))
            draw.rectangle([width // 2 - 200, 360, width // 2 + 200, 405], fill=(15, 10, 35), outline=(140 + fact_pulse, 100, 255), width=2)
            draw.text((width // 2, 382), "• CLASSIFIED ARCHIVE •", font=font_hud, fill=(190, 160, 255), anchor="mm")

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

            draw.rounded_rectangle([90, sub_y - 80, width - 90, sub_y + 120], radius=25, fill=(5, 10, 20, 200), outline=badge_border, width=2)

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
    - 'anime': High-Stakes Anime Battles & Power Matchups (Naruto vs Sasuke, Luffy vs Imu, Goku vs Vegeta)
    - 'gaming': Game Lore Secrets & Next-Gen Physics (Elden Ring, GTA 6)
    - 'facts': Mind-Blowing Science, Cosmic Space & Psychology Wonders
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
                if meta["genre"] == "anime":
                    hf_prompt = f"epic cinematic anime battle {meta['topic']}, intense glowing auras, ufotable style, 9:16 vertical"
                elif meta["genre"] == "gaming":
                    hf_prompt = f"cinematic dark fantasy next-gen gaming {meta['topic']}, unreal engine 5, 9:16 vertical"
                elif meta["genre"] == "facts":
                    hf_prompt = f"deep space nebula celestial cosmos {meta['topic']}, 8k photorealistic, 9:16 vertical"
                elif meta["genre"] == "cat":
                    hf_prompt = f"ultra-cute fluffy cat {meta['topic']}, comical expression, 3d pixar animation style, 9:16 vertical"
                elif meta["genre"] == "kids":
                    hf_prompt = f"whimsical cute cartoon toddler {meta['topic']}, colorful pixar style, 9:16 vertical"
                elif meta["genre"] == "animated":
                    hf_prompt = f"vibrant 2D/3D cartoon animation {meta['topic']}, studio ghibli colors, 9:16 vertical"
                else:
                    hf_prompt = "cinematic futuristic neural network data stream, 8k, 9:16 vertical"

                print(f"[Higgsfield AI] Initiating cinematic video generation for '{hf_prompt[:60]}...'")
                generate_higgsfield_video(hf_prompt)
        except Exception as e:
            print(f"[Higgsfield AI] Notice: {e}")

    print(f"4. Rendering 1080x1920 Short video ({meta['genre'].upper()}) with script-matched canvas & kinetic captions ({len(words)} words)...")
    render_short_video(
        wav_path=wav_path,
        output_mp4_path=mp4_path,
        words=words,
        badge_text=meta.get("category_badge", "⚡ TECH INTELLIGENCE"),
        genre=meta.get("genre", "tech"),
        topic=meta.get("topic", ""),
    )

    duration = get_audio_duration(wav_path)
    file_size_mb = round(os.path.getsize(mp4_path) / (1024 * 1024), 2)

    result = {
        "status": "success",
        "genre": meta["genre"],
        "category_id": meta.get("category_id", "28"),
        "title": meta["title"],
        "description": meta["description"],
        "tags": meta["tags"],
        "engagement_question": meta.get("engagement_question", ""),
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
                category_id=meta.get("category_id", "28"),
                engagement_question=meta.get("engagement_question", ""),
                genre=meta.get("genre", ""),
            )
            result["uploaded"] = (up_res.get("status") == "SUCCESS")
            result["upload_details"] = up_res
        except Exception as e:
            result["upload_error"] = str(e)

    return result
