"""Builds a .pptx presentation from AI-written slide text using the bundled designs."""
import os
import random
import re
from datetime import datetime

from pptx import Presentation

from backend.core.config import ROOT_DIR

DESIGNS_DIR = os.path.join(ROOT_DIR, "backend", "modules", "Powerpointer", "Designs")
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "JARVIS Presentations")

SLIDE_PROMPT = """Write a presentation about the user's topic. Answer ONLY with the presentation in exactly this format:

#Title: TITLE OF THE PRESENTATION

#Slide: 1
#Header: Table of Contents
#Content: 1. FIRST TOPIC
2. SECOND TOPIC
3. THIRD TOPIC

#Slide: 2
#Header: SHORT SLIDE TITLE
#Content: SLIDE TEXT (at most 250 characters, short bullet lines are fine)

(... more slides ...)

#Slide: N
#Header: Summary
#Content: SUMMARY TEXT

#Slide: END

Rules: 8 to 10 slides, very short headers, easy to understand, in English, include a table of contents and a summary."""


def parse_slides(text: str):
    """Returns (title, [(header, content), ...]) from the #Title/#Slide/#Header/#Content format."""
    title, slides = "", []
    header, content, in_slide, in_content = "", [], False, False

    def flush():
        if in_slide and (header or content):
            slides.append((header.strip(), "\n".join(content).strip()))

    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("#title:"):
            title = line.split(":", 1)[1].strip()
            in_content = False
        elif line.lower().startswith("#slide:"):
            flush()
            header, content, in_slide, in_content = "", [], True, False
            if line.split(":", 1)[1].strip().upper() == "END":
                in_slide = False
        elif re.match(r"#headers?:", line, re.I):
            header = line.split(":", 1)[1].strip()
            in_content = False
        elif line.lower().startswith("#content:"):
            content = [line.split(":", 1)[1].strip()]
            in_content = True
        elif in_content and line and not line.startswith("#"):
            content.append(line)
    flush()
    return title, slides


def build_pptx(topic: str, slide_text: str, design_number: int = None) -> str:
    title, slides = parse_slides(slide_text)
    if not slides:
        raise ValueError("The AI did not return any slides.")
    if design_number is None:
        design_number = random.randint(1, 7)
    prs = Presentation(os.path.join(DESIGNS_DIR, f"Design-{design_number}.pptx"))

    first = prs.slides.add_slide(prs.slide_layouts[0])
    first.shapes.title.text = title or topic.title()
    try:
        first.placeholders[1].text = datetime.now().strftime("%d %B %Y")
    except KeyError:
        pass

    for header, content in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = header
        slide.placeholders[1].text_frame.text = content

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", title or topic).strip()[:60] or "Presentation"
    path = os.path.join(OUTPUT_DIR, f"{safe} {datetime.now():%Y-%m-%d %H%M%S}.pptx")
    prs.save(path)
    return path
