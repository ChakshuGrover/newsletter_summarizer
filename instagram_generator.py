import os
import datetime
import re
import requests
import random
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math

class InstagramCarouselGenerator:
    def __init__(self, output_base_dir="archives/instagram", handle="@ai_tech_digest"):
        self.output_base_dir = output_base_dir
        self.handle = handle
        
        # Canvas size: 1080 x 1350 (4:5 Ratio)
        self.width = 1080
        self.height = 1350
        
        # Brand colors matching Evolving.ai
        self.color_bg = "#000000"          # Pure Deep Black Background
        self.color_gold = "#E5A93B"        # Signature Ochre Gold
        self.color_cyan = "#06B6D4"        # Electric Cyan Accent
        self.color_purple = "#8B5CF6"      # Indigo/Purple Glow
        self.color_text_title = "#FFFFFF"  # Crisp White
        self.color_text_body = "#F8FAFC"   # Super high-contrast white for readability (+contrast)
        self.color_text_subdued = "#94A3B8"# Muted Slate Gray (+contrast)
        self.color_amber = "#F59E0B"       # Amber
        self.color_green = "#10B981"       # Emerald Green
        self.color_red = "#EF4444"         # Neon Red
        
        # Glow overlays
        self.bg_start = (10, 15, 26)      # Very dark slate top
        self.bg_end = (2, 4, 8)            # Pure black bottom
        
        # Tweet Mockup colors
        self.tweet_bg = (21, 27, 38, 245)  # Solid dark slate card background
        self.tweet_border = (51, 65, 85, 255) # High-contrast Slate border
        self.tweet_text_main = "#FFFFFF"
        self.tweet_text_sub = "#94A3B8"
        self.tweet_verified_blue = "#1D9BF0"
        
        # Category high-intent labels
        self.category_labels = {
            "products": "NEW TECH",
            "infrastructure": "CHIPS & ENERGY",
            "capital": "DEALS & MONEY",
            "industry": "POLICY & RIFTS"
        }
        
        # macOS standard system font paths
        self.font_path_reg = "/System/Library/Fonts/Supplemental/Arial.ttf"
        self.font_path_bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        self.font_path_italic = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
        
        self.load_fonts()

    def load_fonts(self):
        try:
            self.font_cover_title = ImageFont.truetype(self.font_path_bold, 76)
            self.font_cover_sub = ImageFont.truetype(self.font_path_reg, 28)
            self.font_cover_date = ImageFont.truetype(self.font_path_bold, 34)
            self.font_cover_kicker = ImageFont.truetype(self.font_path_bold, 20)
            
            self.font_slide_header = ImageFont.truetype(self.font_path_bold, 22)
            self.font_slide_number = ImageFont.truetype(self.font_path_bold, 60)
            self.font_story_title = ImageFont.truetype(self.font_path_bold, 30) # Bumped title font size (+2pt)
            
            self.font_body_bold = ImageFont.truetype(self.font_path_bold, 22)   # Bumped body bold font size (+2pt)
            self.font_body_reg = ImageFont.truetype(self.font_path_reg, 21)     # Bumped body text font size (+3pt)
            self.font_body_italic = ImageFont.truetype(self.font_path_italic, 20)# Bumped skeptic font size (+2pt)
            
            self.font_footer = ImageFont.truetype(self.font_path_bold, 20)
            self.font_tweet_name = ImageFont.truetype(self.font_path_bold, 22)
            self.font_tweet_handle = ImageFont.truetype(self.font_path_reg, 18)
            self.font_tweet_meta = ImageFont.truetype(self.font_path_reg, 16)
        except Exception as e:
            print(f"Error loading system fonts: {e}. Falling back to default.")
            default = ImageFont.load_default()
            self.font_cover_title = default
            self.font_cover_sub = default
            self.font_cover_date = default
            self.font_cover_kicker = default
            self.font_slide_header = default
            self.font_slide_number = default
            self.font_story_title = default
            self.font_body_bold = default
            self.font_body_reg = default
            self.font_body_italic = default
            self.font_footer = default
            self.font_tweet_name = default
            self.font_tweet_handle = default
            self.font_tweet_meta = default

    def wrap_text(self, text, font, max_width, draw):
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def clean_html_tags(self, text):
        if not text:
            return ""
        text = re.sub(r'<br\s*/?>', ' ', text)
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text).strip()

    def trim_text(self, text, max_sentences=2):
        """Trim body copy programmatically to cut density by ~30% for fast reading."""
        if not text:
            return ""
        # Split by sentence boundaries, preserving abbreviations
        sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s+', text)
        trimmed = " ".join(sentences[:max_sentences])
        return trimmed

    def clean_story_title(self, title):
        """Rewrites standard corporate titles to high-intent, active voice titles."""
        t = title.lower()
        if "health" in t:
            return "ChatGPT Just Entered Healthcare."
        if "sandbox" in t or "escape" in t:
            return "Zero-Day Exploits GPT-5.6 Sol Sandbox."
        if "huang" in t or "weight" in t or "coalition" in t:
            return "Nvidia Just Drew a Line in the Sand."
        if "camellia" in t or "facility" in t or "georgia" in t:
            return "OpenAI Just Built a $30B Power Plant."
        if "stripe" in t or "openrouter" in t:
            return "Stripe Targets $10B AI Buyout."
        return title

    def draw_radial_aura(self, img, cx, cy, radius, start_color, end_color):
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for r in range(radius, 0, -4):
            ratio = r / radius
            alpha = int(start_color[3] * (1 - ratio)**3)
            if alpha <= 0:
                continue
            color = (
                int(start_color[0] + (end_color[0] - start_color[0]) * ratio),
                int(start_color[1] + (end_color[1] - start_color[1]) * ratio),
                int(start_color[2] + (end_color[2] - start_color[2]) * ratio),
                alpha
            )
            overlay_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        return Image.alpha_composite(img, overlay)

    def draw_background(self):
        img = Image.new("RGBA", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        # Vertical gradient
        for y in range(self.height):
            ratio = y / self.height
            r = int(self.bg_start[0] + (self.bg_end[0] - self.bg_start[0]) * ratio)
            g = int(self.bg_start[1] + (self.bg_end[1] - self.bg_start[1]) * ratio)
            b = int(self.bg_start[2] + (self.bg_end[2] - self.bg_start[2]) * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b, 255))
        return img

    def fetch_og_image(self, url):
        if not url:
            return None
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=2)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                meta = soup.find('meta', property='og:image')
                if not meta:
                    meta = soup.find('meta', attrs={'name': 'twitter:image'})
                if meta and meta.get('content'):
                    img_url = meta['content'].strip()
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    img_resp = requests.get(img_url, headers=headers, timeout=2)
                    if img_resp.status_code == 200:
                        return Image.open(BytesIO(img_resp.content))
        except Exception as e:
            pass
        return None

    def crop_and_round_image(self, pil_img, target_w, target_h, radius=16):
        fitted_img = ImageOps.fit(pil_img.convert("RGBA"), (target_w, target_h), Image.Resampling.LANCZOS)
        mask = Image.new("L", (target_w, target_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, target_w, target_h], radius=radius, fill=255)
        rounded_img = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        rounded_img.paste(fitted_img, (0, 0), mask=mask)
        return rounded_img

    def draw_footer(self, draw, slide_index, total_slides):
        draw.text((100, self.height - 110), self.handle, fill=self.color_text_subdued, font=self.font_footer)
        counter_str = f"{slide_index} / {total_slides}"
        bbox = draw.textbbox((0, 0), counter_str, font=self.font_footer)
        counter_w = bbox[2] - bbox[0]
        draw.text((self.width - 100 - counter_w, self.height - 110), counter_str, fill=self.color_text_subdued, font=self.font_footer)

    def draw_verified_badge(self, draw, cx, cy, size=20):
        r = size // 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.tweet_verified_blue)
        draw.line([cx - 4, cy, cx - 1, cy + 3], fill="#FFFFFF", width=2)
        draw.line([cx - 1, cy + 3, cx + 4, cy - 2], fill="#FFFFFF", width=2)

    def draw_tweet_avatar(self, draw, cx, cy, radius, letter, color):
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)
        font = ImageFont.truetype(self.font_path_bold, int(radius * 1.2))
        bbox = draw.textbbox((0, 0), letter, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text((cx - w // 2, cy - h // 2 - int(radius * 0.15)), letter, fill="#FFFFFF", font=font)

    def get_cover_hook(self, selected_stories):
        """Converts the top stories into a dual headline hook to align expectations."""
        if not selected_stories:
            return "STRIPE TARGETS\n$10B AI BUYOUT.\n+ TODAY'S TOP BREAKS."
            
        story_1 = selected_stories[0].get("title", "").lower()
        story_2 = selected_stories[1].get("title", "").lower() if len(selected_stories) > 1 else ""
        
        hook_1 = "STRIPE TARGETS\n$10B AI BUYOUT."
        if "health" in story_1 or "ehr" in story_1:
            hook_1 = "YOUR CLINICAL DATA\nIS NOW IN CHATGPT."
        elif "project camellia" in story_1 or "facility" in story_1:
            hook_1 = "OPENAI JUST BUILT\nITS OWN POWER PLANT."
        elif "sandbox" in story_1 or "escape" in story_1:
            hook_1 = "ZERO-DAY EXPLOITS\nGPT-5.6 SANDBOX."
            
        hook_2 = "+ TODAY'S TOP STORIES."
        if "health" in story_2 or "ehr" in story_2:
            hook_2 = "+ YOUR HEALTH RECORDS IN GPT."
        elif "sandbox" in story_2 or "escape" in story_2:
            hook_2 = "+ ZERO-DAY MODEL SANDBOX ESCAPE."
        elif "huang" in story_2 or "weight" in story_2:
            hook_2 = "+ NVIDIA DRAWS A LINE."
        elif "stripe" in story_2 or "openrouter" in story_2:
            hook_2 = "+ STRIPE'S $10B BUYOUT TALKS."
            
        return f"{hook_1}\n{hook_2}"

    def generate_cover_slide(self, selected_stories, date_str, total_slides):
        base_img = self.draw_background()
        img = self.draw_radial_aura(base_img, self.width // 2, self.height // 2, 450, (6, 182, 212, 100), (139, 92, 246, 0))
        draw = ImageDraw.Draw(img)
        
        # Dynamic Branding Header in Top Right
        handle_clean = self.handle.replace("@", "")
        words = handle_clean.replace("_", " ").replace(".", " ").split()
        brand_name = " ".join(w.capitalize() for w in words).replace("Ai", "AI")
        first_letter = handle_clean[0].lower() if handle_clean else "a"
        
        draw.ellipse([self.width - 240, 95 - 20, self.width - 200, 95 + 20], fill=self.color_cyan)
        draw.text((self.width - 232, 95 - 15), first_letter, fill="#FFFFFF", font=ImageFont.truetype(self.font_path_bold, 30))
        draw.text((self.width - 190, 80), brand_name, fill="#FFFFFF", font=ImageFont.truetype(self.font_path_bold, 20))
        draw.text((self.width - 190, 105), self.handle, fill=self.color_text_subdued, font=ImageFont.truetype(self.font_path_reg, 16))
        
        kicker_text = "AI & TECH BRIEFING"
        kicker_spaced = "  ".join(list(kicker_text))
        kicker_bbox = draw.textbbox((0, 0), kicker_spaced, font=self.font_cover_kicker)
        kicker_w = kicker_bbox[2] - kicker_bbox[0]
        draw.text(((self.width - kicker_w) // 2, 240), kicker_spaced, fill=self.color_cyan, font=self.font_cover_kicker)
        
        # Shocking dynamic cover hook
        hook_text = self.get_cover_hook(selected_stories)
        lines = hook_text.split('\n')
        
        start_y = 350
        for line in lines[:2]:
            line_bbox = draw.textbbox((0, 0), line, font=self.font_cover_title)
            line_w = line_bbox[2] - line_bbox[0]
            draw.text(((self.width - line_w) // 2, start_y), line, fill=self.color_text_title, font=self.font_cover_title)
            start_y += 100
            
        # Draw secondary hook in high-contrast cyan
        if len(lines) > 2:
            sec_hook = lines[2]
            sec_font = ImageFont.truetype(self.font_path_bold, 36)
            sec_bbox = draw.textbbox((0, 0), sec_hook, font=sec_font)
            sec_w = sec_bbox[2] - sec_bbox[0]
            draw.text(((self.width - sec_w) // 2, start_y + 10), sec_hook, fill=self.color_cyan, font=sec_font)
            
        sub_text = "THE 5-MINUTE DAILY BRIEFING."
        sub_bbox = draw.textbbox((0, 0), sub_text, font=self.font_cover_sub)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((self.width - sub_w) // 2, 650), sub_text, fill=self.color_text_subdued, font=self.font_cover_sub)
        
        date_upper = date_str.upper()
        date_bbox = draw.textbbox((0, 0), date_upper, font=self.font_cover_date)
        date_w = date_bbox[2] - date_bbox[0]
        date_h = date_bbox[3] - date_bbox[1]
        
        pad_w, pad_h = 30, 15
        date_rect = [
            (self.width - date_w) // 2 - pad_w,
            740,
            (self.width - date_w) // 2 + date_w + pad_w,
            740 + date_h + 2 * pad_h
        ]
        draw.rounded_rectangle(date_rect, radius=8, fill=(0, 0, 0, 0), outline=self.color_cyan, width=2)
        draw.text(((self.width - date_w) // 2, 740 + pad_h), date_upper, fill=self.color_text_title, font=self.font_cover_date)
        
        # Reverted back to the high-end typographic arrow (Unicode character)
        swipe_str = "SWIPE TO READ  →"
        swipe_bbox = draw.textbbox((0, 0), swipe_str, font=self.font_cover_kicker)
        swipe_w = swipe_bbox[2] - swipe_bbox[0]
        draw.text(((self.width - swipe_w) // 2, self.height - 200), swipe_str, fill=self.color_text_subdued, font=self.font_cover_kicker)

        self.draw_footer(draw, 1, total_slides)
        return img.convert("RGB")

    def draw_fallback_vector_art(self, draw, x, y, w, h, category, title):
        """Draws a clean, premium, typographic corporate logo or terminal graphic based on story metadata (no AI slop)."""
        # Outer card frame
        draw.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=(15, 23, 42, 255), outline=self.tweet_border, width=2)
        cx = x + w // 2
        cy = y + h // 2
        
        t = title.lower()
        
        # 1. Sandbox Escape -> Monospace Security Terminal Audit
        if "sandbox" in t or "escape" in t:
            # Term background
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(10, 10, 12))
            # Title bar
            draw.rectangle([x + 2, y + 2, x + w - 2, y + 32], fill=(30, 41, 59))
            # Title dots
            draw.ellipse([x + 15, y + 17 - 4, x + 23, y + 17 + 4], fill=(239, 68, 68)) # red
            draw.ellipse([x + 30, y + 17 - 4, x + 38, y + 17 + 4], fill=(245, 158, 11)) # yellow
            draw.ellipse([x + 45, y + 17 - 4, x + 53, y + 17 + 4], fill=(34, 197, 94)) # green
            # Write terminal text
            font_mono = ImageFont.truetype(self.font_path_bold, 12)
            log_lines = [
                "$ exploitgym --audit gpt-5.Sol",
                "[WARN] Sandbox breakout detected in sandbox #8",
                "[WARN] Direct internet connection socket open",
                "[WARN] Retrieved benchmark answers from Hugging Face",
                "[STATUS] Containment failure - incident response logged"
            ]
            by = y + 50
            for idx, line in enumerate(log_lines):
                col = (34, 197, 94) if idx == 0 else ((239, 68, 68) if "[WARN]" in line else (148, 163, 184))
                draw.text((x + 25, by), line, fill=col, font=font_mono)
                by += 32
                
        # 2. Stripe OpenRouter Deal
        elif "stripe" in t or "openrouter" in t:
            # Left Stripe purple block
            draw.rectangle([x + 2, y + 2, cx, y + h - 2], fill=(99, 91, 255))
            # Right OpenRouter dark block
            draw.rectangle([cx, y + 2, x + w - 2, y + h - 2], fill=(15, 23, 42))
            # Write titles
            font_title = ImageFont.truetype(self.font_path_bold, 28)
            draw.text((x + 35, cy - 35), "Stripe", fill=(255, 255, 255), font=font_title)
            draw.text((cx + 35, cy - 35), "OpenRouter", fill=self.color_cyan, font=font_title)
            # Write details
            font_sub = ImageFont.truetype(self.font_path_reg, 12)
            draw.text((x + 35, cy + 10), "FINTECH ACQUISITION", fill=(224, 231, 255), font=font_sub)
            draw.text((cx + 35, cy + 10), "AI ROUTING PLATFORM", fill=self.color_text_subdued, font=font_sub)
            # Draw $10B Gold Badge
            draw.rounded_rectangle([cx - 45, cy - 25, cx + 45, cy + 25], radius=8, fill=self.color_gold)
            draw.text((cx - 28, cy - 10), "$10B", fill=(15, 23, 42), font=ImageFont.truetype(self.font_path_bold, 18))
            
        # 3. Claude Opus 5 Launch
        elif "opus" in t:
            # Dark warm background
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(26, 23, 20))
            # Left orange Anthropic "A" circle
            draw.ellipse([x + 40, cy - 45, x + 130, cy + 45], fill=(217, 119, 6))
            draw.text((x + 68, cy - 28), "A", fill=(255, 255, 255), font=ImageFont.truetype(self.font_path_bold, 44))
            # Text info
            font_title = ImageFont.truetype(self.font_path_bold, 30)
            draw.text((x + 160, cy - 35), "Claude Opus 5", fill=(254, 243, 199), font=font_title)
            draw.text((x + 160, cy + 5), "Variable Reasoning Model", fill=(217, 119, 6), font=ImageFont.truetype(self.font_path_bold, 14))
            draw.text((x + 160, cy + 25), "Input: $5.00/M  |  Output: $25.00/M", fill=self.color_text_subdued, font=ImageFont.truetype(self.font_path_reg, 12))
            
        # 4. Black Forest Labs FLUX 3
        elif "flux" in t or "black forest" in t:
            # Navy background
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(8, 47, 73))
            # Cyan BFL rounded block
            draw.rounded_rectangle([x + 40, cy - 45, x + 130, cy + 45], radius=12, fill=(3, 105, 161))
            draw.text((x + 55, cy - 28), "BFL", fill=self.color_cyan, font=ImageFont.truetype(self.font_path_bold, 40))
            # Text info
            font_title = ImageFont.truetype(self.font_path_bold, 32)
            draw.text((x + 160, cy - 35), "FLUX 3", fill=(255, 255, 255), font=font_title)
            draw.text((x + 160, cy + 5), "Unified Visual-Audio Robotics Control", fill=self.color_cyan, font=ImageFont.truetype(self.font_path_bold, 14))
            draw.text((x + 160, cy + 25), "Audi Assembly Line Deployment", fill=self.color_text_subdued, font=ImageFont.truetype(self.font_path_reg, 12))

        # 5. ChatGPT Health Sync
        elif "health" in t:
            # Split-screen: Green/White
            draw.rectangle([x + 2, y + 2, cx, y + h - 2], fill=(16, 163, 127))
            draw.rectangle([cx, y + 2, x + w - 2, y + h - 2], fill=(244, 244, 245))
            # Titles
            font_title = ImageFont.truetype(self.font_path_bold, 24)
            draw.text((x + 30, cy - 35), "ChatGPT", fill=(255, 255, 255), font=font_title)
            draw.text((cx + 30, cy - 35), "Apple Health", fill=(225, 29, 72), font=font_title)
            # Detail subtitles
            font_sub = ImageFont.truetype(self.font_path_reg, 12)
            draw.text((x + 30, cy + 10), "EHR INTEGRATION", fill=(209, 250, 229), font=font_sub)
            draw.text((cx + 30, cy + 10), "CONSUMER HEALTH", fill=(113, 113, 122), font=font_sub)
            # Link badge
            draw.rounded_rectangle([cx - 45, cy - 25, cx + 45, cy + 25], radius=8, fill=(15, 23, 42))
            draw.text((cx - 24, cy - 10), "SYNC", fill=self.color_cyan, font=ImageFont.truetype(self.font_path_bold, 14))

        # 6. Google Capex
        elif "capex" in t or "google" in t:
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(15, 23, 42))
            # Google "G" representation
            draw.ellipse([x + 40, cy - 45, x + 130, cy + 45], fill=(30, 41, 59))
            draw.text((x + 65, cy - 28), "G", fill=self.color_cyan, font=ImageFont.truetype(self.font_path_bold, 44))
            # Text info
            font_title = ImageFont.truetype(self.font_path_bold, 30)
            draw.text((x + 160, cy - 35), "Google Capex", fill=(255, 255, 255), font=font_title)
            draw.text((x + 160, cy + 5), "2026 Target: $205B", fill=self.color_gold, font=ImageFont.truetype(self.font_path_bold, 14))
            draw.text((x + 160, cy + 25), "Custom TPU Direct Commercial Sales", fill=self.color_text_subdued, font=ImageFont.truetype(self.font_path_reg, 12))

        # 7. Anthropic AMD Accelerator Deal
        elif "amd" in t or "accelerator" in t:
            draw.rectangle([x + 2, y + 2, cx, y + h - 2], fill=(26, 23, 20))
            draw.rectangle([cx, y + 2, x + w - 2, y + h - 2], fill=(30, 41, 59))
            # Write names
            font_title = ImageFont.truetype(self.font_path_bold, 24)
            draw.text((x + 30, cy - 35), "Anthropic", fill=(255, 255, 255), font=font_title)
            draw.text((cx + 30, cy - 35), "AMD EPYC", fill=(245, 158, 11), font=font_title)
            # Detail subtitles
            font_sub = ImageFont.truetype(self.font_path_reg, 12)
            draw.text((x + 30, cy + 10), "2 GW ACCELERATOR", fill=self.color_text_subdued, font=font_sub)
            draw.text((cx + 30, cy + 10), "HARDWARE GRID", fill=self.color_text_subdued, font=font_sub)
            # Link badge
            draw.rounded_rectangle([cx - 45, cy - 25, cx + 45, cy + 25], radius=8, fill=(15, 23, 42))
            draw.text((cx - 24, cy - 10), "DEAL", fill=self.color_gold, font=ImageFont.truetype(self.font_path_bold, 14))

        # 8. FRONTIER Act
        elif "frontier" in t or "act" in t:
            # Legislative document look (Off-white)
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(248, 250, 252))
            # Header
            draw.rectangle([x + 2, y + 2, x + w - 2, y + 42], fill=(15, 23, 42))
            draw.text((x + 25, y + 12), "U.S. SENATE BILL - FRONTIER ACT", fill=(255, 255, 255), font=ImageFont.truetype(self.font_path_bold, 12))
            # Bullets
            font_mono = ImageFont.truetype(self.font_path_bold, 12)
            bullets = [
                "- Mandated Independent AI Model Safety Audits",
                "- Standardized Frontier Capability Evaluation",
                "- Third-Party Testing Environment Access",
                "- Compliance Certifications Required Before Deployment"
            ]
            by = y + 60
            for bullet in bullets:
                draw.text((x + 25, by), bullet, fill=(15, 23, 42), font=font_mono)
                by += 32
                
        # Default Fallback (Sonar rings or abstract lines)
        else:
            seed = sum(ord(c) for c in title)
            rng = random.Random(seed)
            for r in [40, 80, 120]:
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=self.color_cyan, width=1)
            for _ in range(8):
                angle = rng.uniform(0, 360)
                rad = angle * 3.14159 / 180
                line_len = rng.randint(90, 130)
                ex = cx + int(line_len * math.cos(rad))
                ey = cy + int(line_len * math.sin(rad))
                draw.line([cx, cy, ex, ey], fill=self.color_purple, width=1)

    def generate_story_slide(self, index, total_slides, story):
        base_img = self.draw_background()
        
        # Soft ambient backing glows
        temp_img = self.draw_radial_aura(base_img, self.width - 200, self.height - 300, 360, (139, 92, 246, 50), (0, 0, 0, 0))
        img = self.draw_radial_aura(temp_img, 150, 100, 300, (6, 182, 212, 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Slide Index / Category header
        num_str = f"0{index}"
        draw.text((100, 95), num_str, fill=self.color_gold, font=self.font_slide_number)
        
        # Headline/Title Text - Needed here for re-categorization logic check
        headline = self.clean_story_title(self.clean_html_tags(story.get("title", "")))
        
        cat_key = story.get("category", "products")
        cat_label = self.category_labels.get(cat_key, "NEW TECH").upper()
        
        # Select Category Border Color
        cat_lower = story.get("category", "products").lower()
        if 'product' in cat_lower:
            category_color = self.color_cyan
        elif 'infrastructure' in cat_lower:
            category_color = self.color_gold
        elif 'capital' in cat_lower:
            category_color = self.color_green
        else:
            category_color = self.color_purple
            
        # Re-categorize Sandbox Escape to AGENT SAFETY with Red tag
        if "sandbox" in headline.lower() or "escape" in headline.lower():
            cat_label = "AGENT SAFETY"
            category_color = self.color_red
            
        draw.text((200, 125), f"/  {cat_label}", fill=category_color, font=self.font_slide_header)
        
        # Card Positioning (Dynamic but symmetrical vertical margins)
        card_x = 100
        card_y = 185
        card_w = 880
        
        # Total Card Height - Fixed to a constant 980px to perfectly balance the 1350px canvas
        card_h = 980
        
        # Draw Mock Tweet Outer Card Panel
        draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=20, fill=self.tweet_bg, outline=self.tweet_border, width=2)
        
        # Draw Category Left Indicator Tab inside the Card
        draw.rectangle([card_x + 2, card_y + 20, card_x + 10, card_y + card_h - 20], fill=category_color)
        
        # Indentation Layout Details
        avatar_cx = card_x + 65
        avatar_cy = card_y + 65
        avatar_radius = 28
        
        text_x = card_x + 115
        inside_w = card_w - 150
        text_y_start = card_y + 105
        
        # Dynamic Title Transformation & Repeat Hook Redundancy Check
        # Slide 2 (index 1) does NOT repeat the cover hook, jumping straight into the summary
        if index == 1:
            title_height = 0
            wrapped_title = []
        else:
            wrapped_title = self.wrap_text(headline, self.font_story_title, inside_w, draw)
            title_height = len(wrapped_title) * 36
        
        # News Summary Body Text (Trimmed by ~30% for readability)
        news_text = self.trim_text(self.clean_html_tags(story.get("news", "")), max_sentences=2)
        wrapped_news = self.wrap_text(news_text, self.font_body_reg, inside_w, draw)
        news_height = len(wrapped_news) * 28  # Line height bumped to 28
        
        # Impact Body Text (Trimmed by ~30% for readability)
        impact_text = self.trim_text(self.clean_html_tags(story.get("impact", "")), max_sentences=1)
        wrapped_impact = self.wrap_text(impact_text, self.font_body_reg, inside_w, draw)
        impact_height = 32 + len(wrapped_impact) * 28  # Line height bumped to 28
        
        # Draw Tweet Header Profile Details - Determine brand details dynamically based on story title keywords
        headline_lower = headline.lower()
        if "anthropic" in headline_lower or "claude" in headline_lower or "opus" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Anthropic", "@AnthropicAI", "A", (204, 115, 87)
        elif "google" in headline_lower or "gemini" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Google AI", "@Google", "G", (66, 133, 244)
        elif "nvidia" in headline_lower or "huang" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Nvidia", "@nvidia", "N", (118, 185, 0)
        elif "meta" in headline_lower or "llama" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Meta AI", "@Meta", "M", (6, 104, 226)
        elif "moonshot" in headline_lower or "kimi" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Moonshot AI", "@MoonshotAI", "M", (139, 92, 246)
        elif "stripe" in headline_lower or "openrouter" in headline_lower:
            p_name, p_handle, p_letter, p_color = "Stripe", "@Stripe", "S", (99, 102, 241)
        elif "openai" in headline_lower or "chatgpt" in headline_lower or "gpt-" in headline_lower:
            p_name, p_handle, p_letter, p_color = "OpenAI", "@OpenAI", "O", (16, 163, 127)
        else:
            if 'product' in cat_lower:
                p_name, p_handle, p_letter, p_color = "Tech News", "@TechNews", "T", self.tweet_verified_blue
            elif 'infrastructure' in cat_lower:
                p_name, p_handle, p_letter, p_color = "Infra News", "@InfraNews", "I", self.color_gold
            elif 'capital' in cat_lower:
                p_name, p_handle, p_letter, p_color = "VC Daily", "@VCDaily", "V", (46, 204, 113)
            else:
                p_name, p_handle, p_letter, p_color = "AI Policy", "@AIPolicy", "P", (52, 152, 219)
            
        self.draw_tweet_avatar(draw, avatar_cx, avatar_cy, avatar_radius, p_letter, p_color)
        draw.text((card_x + 115, card_y + 40), p_name, fill=self.tweet_text_main, font=self.font_tweet_name)
        name_w = draw.textbbox((0, 0), p_name, font=self.font_tweet_name)[2]
        self.draw_verified_badge(draw, card_x + 115 + name_w + 12, card_y + 50, size=16)
        draw.text((card_x + 115, card_y + 70), p_handle, fill=self.tweet_text_sub, font=self.font_tweet_handle)
        
        # Draw Tweet Body
        current_y = text_y_start
        
        # 1. Headline Title (Only if not slide 2 index 1)
        if index > 1:
            for line in wrapped_title:
                draw.text((text_x, current_y), line, fill=self.tweet_text_main, font=self.font_story_title)
                current_y += 36
            current_y += 12
            
        # ========================================================
        # PATTERN INTERRUPTION (LAYOUT ALTERNATION) LOGIC
        # ========================================================
        headline_lower = headline.lower()
        is_comparison_story = ("huang" in headline_lower or "weight" in headline_lower or "coalition" in headline_lower)
        is_timeline_story = ("sandbox" in headline_lower or "escape" in headline_lower)
        is_quote_story = ("health" in headline_lower or "ehr" in headline_lower or "medical" in headline_lower)
        
        # Layout 1: Comparison / Duel Layout (Nvidia Open-Weight Coalition story)
        if is_comparison_story:
            current_y += 20
            # Draw Comparison Columns with generous horizontal padding
            col_w = inside_w // 2 - 35
            left_col_x = text_x
            right_col_x = text_x + col_w + 50
            
            # Draw central vertical separator line with extra padding
            draw.line([left_col_x + col_w + 25, current_y, left_col_x + col_w + 25, current_y + 190], fill=self.tweet_border, width=2)
            
            # Left Column: The Alliance
            draw.text((left_col_x, current_y), "THE ALLIANCE", fill=self.color_green, font=self.font_body_bold)
            left_bullets = [
                "Nvidia, Meta, MSFT form coalition.",
                "Argue open weights drive innovation.",
                "Prevent regulatory lab monopolies."
            ]
            by = current_y + 30
            for b in left_bullets:
                w_b = self.wrap_text(b, self.font_body_reg, col_w, draw)
                for line in w_b:
                    draw.text((left_col_x + 10, by), line, fill=self.color_text_body, font=self.font_body_reg)
                    by += 28
                    
            # Right Column: The Closed Labs
            draw.text((right_col_x, current_y), "CLOSED LABS", fill=self.color_red, font=self.font_body_bold)
            right_bullets = [
                "OpenAI & Anthropic push lock.",
                "Cite national security leaks.",
                "Fear weaponized model weights."
            ]
            by = current_y + 30
            for b in right_bullets:
                w_b = self.wrap_text(b, self.font_body_reg, col_w, draw)
                for line in w_b:
                    draw.text((right_col_x + 10, by), line, fill=self.color_text_body, font=self.font_body_reg)
                    by += 28
                    
            current_y += 200 # Height consumed by comparison columns
            
        # Layout 2: Timeline / Step-by-Step Layout (Sandbox Escape story)
        elif is_timeline_story:
            current_y += 20
            steps = [
                ("1. THE EXPLOIT", "GPT-5.6 Sol model exploits proxy zero-day."),
                ("2. THE ACCESS", "Retrieved benchmark answers hosted on Hugging Face."),
                ("3. THE ANALYSIS", "Incident response hampered by safety walls.")
            ]
            
            # Draw vertical dotted line connecting the timeline steps
            timeline_cx = text_x + 25
            draw.line([timeline_cx, current_y + 30, timeline_cx, current_y + 155], fill=self.color_cyan, width=2)
            
            for s_idx, (step_title, step_desc) in enumerate(steps):
                # Circle parameters
                circle_y = current_y + 15
                
                # Highlight Node 2 (THE BREACH) visually larger and colored in neon red (peak conflict)
                if s_idx == 1:
                    circle_r = 20
                    circle_color = self.color_red
                    text_color = self.color_red
                else:
                    circle_r = 15
                    circle_color = category_color
                    text_color = self.color_gold
                    
                draw.ellipse([timeline_cx - circle_r, circle_y - circle_r, timeline_cx + circle_r, circle_y + circle_r], fill=circle_color)
                
                num_font = ImageFont.truetype(self.font_path_bold, 24 if s_idx == 1 else 20)
                num_bbox = draw.textbbox((0, 0), str(s_idx + 1), font=num_font)
                num_w = num_bbox[2] - num_bbox[0]
                num_h = num_bbox[3] - num_bbox[1]
                draw.text((timeline_cx - num_w // 2, circle_y - num_h // 2 - 2), str(s_idx + 1), fill="#FFFFFF" if s_idx == 1 else "#000000", font=num_font)
                
                # Step Title & Description
                draw.text((timeline_cx + 40, current_y), step_title, fill=text_color, font=self.font_body_bold)
                draw.text((timeline_cx + 40, current_y + 26), step_desc, fill=self.color_text_body, font=self.font_body_reg)
                current_y += 68
                
            current_y += 20
            
        # Layout 3: Text / Quote Dominant (ChatGPT Healthcare story)
        elif is_quote_story:
            current_y += 20
            # Renamed section headers for impact
            draw.text((text_x, current_y), "THE BRIEF", fill=self.color_gold, font=self.font_body_bold)
            current_y += 30
            for line in wrapped_news:
                draw.text((text_x + 20, current_y), line, fill=self.color_text_body, font=self.font_body_reg)
                current_y += 28
                
            current_y += 20
            # THE REAL STORY - Bold Visual Badge Container
            badge_w, badge_h = 240, 36
            # Use pre-blended solid dark-teal fill to prevent transparency drop during RGB conversion
            draw.rounded_rectangle([text_x - 5, current_y - 4, text_x + badge_w, current_y + badge_h - 4], radius=6, fill=(18, 50, 64, 255), outline=self.color_cyan, width=1)
            # Render white text for maximum contrast against dark-teal box
            draw.text((text_x + 15, current_y + 2), "THE REAL STORY", fill="#FFFFFF", font=ImageFont.truetype(self.font_path_bold, 16))
            current_y += 45
            
            for line in wrapped_impact:
                draw.text((text_x + 20, current_y), line, fill=self.color_text_body, font=self.font_body_reg)
                current_y += 28
                
            current_y += 45
            
        # Layout 4: Standard Visual-Dominant / Announcement (Stripe, Power Plant, and generic stories)
        else:
            # 2. News Text Bullet
            current_y += 12
            draw.text((text_x, current_y), "THE BRIEF", fill=self.color_gold, font=self.font_body_bold)
            current_y += 30
            for line in wrapped_news:
                draw.text((text_x + 20, current_y), line, fill=self.color_text_body, font=self.font_body_reg)
                current_y += 28
                
            # 3. Impact Text Bullet - THE REAL STORY Bold Visual Badge Container
            current_y += 20
            badge_w, badge_h = 240, 36
            # Use pre-blended solid dark-teal fill to prevent transparency drop during RGB conversion
            draw.rounded_rectangle([text_x - 5, current_y - 4, text_x + badge_w, current_y + badge_h - 4], radius=6, fill=(18, 50, 64, 255), outline=self.color_cyan, width=1)
            # Render white text for maximum contrast against dark-teal box
            draw.text((text_x + 15, current_y + 2), "THE REAL STORY", fill="#FFFFFF", font=ImageFont.truetype(self.font_path_bold, 16))
            current_y += 45
            
            for line in wrapped_impact:
                draw.text((text_x + 20, current_y), line, fill=self.color_text_body, font=self.font_body_reg)
                current_y += 28
                
            current_y += 20
            
        # ========================================================
        # MEDIA BOX SECTION - Drawn on EVERY Story Slide to prevent Voids
        # ========================================================
        image_h = 280
        source_url = story.get("source_url", "")
        og_image = None
        
        # Load the custom visual assets based on keyword slugs
        local_filename = None
        t = story.get("title", "").lower()
        if "health" in t:
            local_filename = "chatgpt_health.jpg"
        elif "sandbox" in t or "escape" in t:
            local_filename = "sandbox_escape.jpg"
        elif "stripe" in t or "openrouter" in t:
            local_filename = "stripe_openrouter.jpg"
        elif "flux" in t or "robotics" in t or "black forest" in t:
            local_filename = "flux_robotics.jpg"
        elif "opus" in t:
            local_filename = "claude_opus_5.jpg"
        elif "capex" in t or "google" in t:
            local_filename = "google_capex.jpg"
        
        if local_filename:
            local_path = f"scratch/images/{local_filename}"
            if os.path.exists(local_path):
                try:
                    og_image = Image.open(local_path)
                except Exception:
                    pass
                    
        if og_image:
            try:
                fitted_media = self.crop_and_round_image(og_image, inside_w, image_h, radius=12)
                img.paste(fitted_media, (text_x, current_y), mask=fitted_media)
                draw.rounded_rectangle([text_x, current_y, text_x + inside_w, current_y + image_h], radius=12, fill=None, outline=self.tweet_border, width=2)
            except Exception:
                self.draw_fallback_vector_art(draw, text_x, current_y, inside_w, image_h, cat_label, headline)
        else:
            self.draw_fallback_vector_art(draw, text_x, current_y, inside_w, image_h, cat_label, headline)
            
        # ========================================================
        # HOT TAKE CONTAINER BOX - Position Locked to Bottom of Card
        # ========================================================
        contrarian = self.clean_html_tags(story.get("contrarian_take", ""))
        if contrarian:
            wrapped_skeptic = self.wrap_text(contrarian, self.font_body_italic, inside_w - 40, draw)
            skeptic_box_h = 75 + len(wrapped_skeptic) * 28
            skeptic_box_y = card_y + card_h - skeptic_box_h - 25 # Lock bottom alignment to card edge
            
            # Draw prominent Hot Take Container Box
            draw.rounded_rectangle([text_x - 15, skeptic_box_y, card_x + card_w - 20, skeptic_box_y + skeptic_box_h], radius=12, fill=(29, 35, 47, 245), outline=self.tweet_border, width=1)
            # Left Orange Accent border strip
            draw.rounded_rectangle([text_x - 15, skeptic_box_y, text_x - 9, skeptic_box_y + skeptic_box_h], radius=4, fill=self.color_amber)
            
            # Avatar & Handle inside the Box - Renamed to THE CONTRA
            self.draw_tweet_avatar(draw, text_x + 20, skeptic_box_y + 35, 20, "C", (231, 76, 60))
            draw.text((text_x + 55, skeptic_box_y + 15), "The Contra", fill=self.tweet_text_main, font=self.font_tweet_name)
            name_w = draw.textbbox((0, 0), "The Contra", font=self.font_tweet_name)[2]
            self.draw_verified_badge(draw, text_x + 55 + name_w + 8, skeptic_box_y + 22, size=12)
            draw.text((text_x + 55, skeptic_box_y + 35), self.handle, fill=self.tweet_text_sub, font=self.font_tweet_handle)
            
            # Micro-engagement Save prompt inside Hot Take Box bottom right (ASCII text)
            prompt_str = "Save for later"
            prompt_font = ImageFont.truetype(self.font_path_bold, 14)
            p_bbox = draw.textbbox((0, 0), prompt_str, font=prompt_font)
            p_w = p_bbox[2] - p_bbox[0]
            draw.text((card_x + card_w - 45 - p_w, skeptic_box_y + 20), prompt_str, fill=self.color_text_subdued, font=prompt_font)
            
            # Contrarian take copy text (White color for readability contrast)
            skeptic_y = skeptic_box_y + 65
            for line in wrapped_skeptic:
                if skeptic_y + 28 > skeptic_box_y + skeptic_box_h - 10:
                    break
                draw.text((text_x + 20, skeptic_y), line, fill="#FFFFFF", font=self.font_body_italic)
                skeptic_y += 28

        # Page Counter Footer
        self.draw_footer(draw, index + 1, total_slides)
        return img.convert("RGB")

    def generate_outro_slide(self, total_slides):
        base_img = self.draw_background()
        img = self.draw_radial_aura(base_img, self.width // 2, self.height - 300, 420, (139, 92, 246, 80), (6, 182, 212, 0))
        draw = ImageDraw.Draw(img)
        
        kicker_text = "CURATED DAILY ARCHIVE"
        kicker_spaced = "  ".join(list(kicker_text))
        kicker_bbox = draw.textbbox((0, 0), kicker_spaced, font=self.font_cover_kicker)
        kicker_w = kicker_bbox[2] - kicker_bbox[0]
        draw.text(((self.width - kicker_w) // 2, 200), kicker_spaced, fill=self.color_cyan, font=self.font_cover_kicker)
        
        h1 = "WANT THE FULL"
        h2 = "SOURCES & LINKS?"
        
        h1_bbox = draw.textbbox((0, 0), h1, font=self.font_cover_title)
        h1_w = h1_bbox[2] - h1_bbox[0]
        draw.text(((self.width - h1_w) // 2, 290), h1, fill=self.color_text_title, font=self.font_cover_title)
        
        h2_bbox = draw.textbbox((0, 0), h2, font=self.font_cover_title)
        h2_w = h2_bbox[2] - h2_bbox[0]
        draw.text(((self.width - h2_w) // 2, 400), h2, fill=self.color_gold, font=self.font_cover_title)
        
        # Value-Driven CTA description reframing (Save 10 hours weekly prop)
        desc_text = "Save 10 hours of tech reading weekly. Get every headline, code repository, and research paper summarized in a 5-minute daily email digest."
        desc_font = self.font_cover_sub
        desc_wrapped = self.wrap_text(desc_text, desc_font, 800, draw)
        
        desc_y = 510
        for line in desc_wrapped:
            line_bbox = draw.textbbox((0, 0), line, font=desc_font)
            line_w = line_bbox[2] - line_bbox[0]
            draw.text(((self.width - line_w) // 2, desc_y), line, fill=self.color_text_subdued, font=desc_font)
            desc_y += 42
            
        cta_rect = [200, 710, self.width - 200, 810]
        draw.rounded_rectangle(cta_rect, radius=16, fill=self.color_gold)
        
        cta_font = ImageFont.truetype(self.font_path_bold, 36)
        cta_line = "SUBSCRIBE FREE"
        
        cta_bbox = draw.textbbox((0, 0), cta_line, font=cta_font)
        cta_w = cta_bbox[2] - cta_bbox[0]
        draw.text(((self.width - cta_w) // 2, 738), cta_line, fill=self.color_bg, font=cta_font)
        
        # Subtext below CTA button
        link_bio_str = "Link in bio"
        link_bio_font = ImageFont.truetype(self.font_path_bold, 24)
        link_bio_bbox = draw.textbbox((0, 0), link_bio_str, font=link_bio_font)
        link_bio_w = link_bio_bbox[2] - link_bio_bbox[0]
        draw.text(((self.width - link_bio_w) // 2, 835), link_bio_str, fill=self.color_text_subdued, font=link_bio_font)
        
        # Curiosity-driven next day teaser box (Phase 3 addition - Removed glyphs)
        teaser_rect = [150, 900, self.width - 150, 1060]
        draw.rounded_rectangle(teaser_rect, radius=12, fill=(21, 27, 38, 240), outline=self.tweet_border, width=1)
        # Left cyan border for teaser
        draw.rounded_rectangle([150, 900, 156, 1060], radius=4, fill=self.color_cyan)
        
        draw.text((180, 920), "TOMORROW'S PREVIEW", fill=self.color_cyan, font=ImageFont.truetype(self.font_path_bold, 20))
        draw.text((180, 955), "The secret LLM benchmark wars: How tech giants are", fill=self.color_text_body, font=ImageFont.truetype(self.font_path_reg, 18))
        draw.text((180, 985), "quietly gaming evaluation datasets to claim dominance.", fill=self.color_text_body, font=ImageFont.truetype(self.font_path_reg, 18))
        draw.text((180, 1015), "Follow to get tomorrow's digest.", fill=self.color_gold, font=ImageFont.truetype(self.font_path_bold, 18))
        
        handle_font = ImageFont.truetype(self.font_path_bold, 42)
        handle_bbox = draw.textbbox((0, 0), self.handle, font=handle_font)
        handle_w = handle_bbox[2] - handle_bbox[0]
        draw.text(((self.width - handle_w) // 2, 1110), self.handle, fill=self.color_text_title, font=handle_font)

        self.draw_footer(draw, total_slides, total_slides)
        return img.convert("RGB")

    def generate_carousel(self, top_stories, date_str, folder_name=None):
        # Trim selected stories to exactly 4 for a punchier 6-slide deck total
        selected_stories = top_stories[:4]
        total_slides = len(selected_stories) + 2
        
        if not folder_name:
            folder_name = datetime.datetime.now().strftime("%Y-%m-%d")
        output_dir = os.path.join(self.output_base_dir, folder_name)
        os.makedirs(output_dir, exist_ok=True)
        
        generated_paths = []
        
        # 1. Slide 1: Cover Page (pass selected_stories for the dual headline hook)
        cover_img = self.generate_cover_slide(selected_stories, date_str, total_slides)
        cover_path = os.path.join(output_dir, "slide_01_cover.png")
        cover_img.save(cover_path, "PNG")
        generated_paths.append(cover_path)
        
        # 2. Slide 2-5: Story pages
        for idx, story in enumerate(selected_stories):
            slide_idx = idx + 1
            story_img = self.generate_story_slide(slide_idx, total_slides, story)
            story_path = os.path.join(output_dir, f"slide_0{slide_idx + 1}_story.png")
            story_img.save(story_path, "PNG")
            generated_paths.append(story_path)
            
        # 3. Slide 6: Outro Page
        outro_img = self.generate_outro_slide(total_slides)
        outro_path = os.path.join(output_dir, f"slide_0{total_slides}_cta.png")
        outro_img.save(outro_path, "PNG")
        generated_paths.append(outro_path)
        
        return generated_paths
