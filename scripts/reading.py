"""Count rendered prose once at build time and annotate reading-depth blocks.

Words are Unicode letter/number sequences, optionally joined by an internal
apostrophe or hyphen. Underscores separate words. Numbers count as words.
The reading speed is a product estimate, not a measured reading ability.
"""

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import math
import re
import unicodedata


DEFAULT_WORDS_PER_MINUTE = 200
WORD = re.compile(r"[^\W_]+(?:[-‐‑'’][^\W_]+)*", re.UNICODE)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BOUNDARIES = {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "section", "table", "td", "th", "tr", "ul"}
EXCLUDED_TAGS = {"pre", "code", "kbd", "script", "style", "button", "input", "select", "textarea", "output", "nav", "svg"}
EXCLUDED_CLASSES = {"mermaid", "headerlink", "level-control", "reading-meta", "reading-summary", "reading-totals"}
GENERATED_BADGE = re.compile(
    r"<p\b(?=[^>]*\bdata-docs-kit-reading=(?:\"true\"|'true'))[^>]*>.*?</p>",
    re.IGNORECASE | re.DOTALL,
)
READING_ATTRIBUTE = re.compile(r"\sdata-reading-(?:words|minutes|wpm)\s*=\s*(?:\"[^\"]*\"|'[^']*')", re.IGNORECASE)


def count_words(text):
    """Count the agreed prose tokens, without interpreting markup."""
    return len(WORD.findall(unicodedata.normalize("NFC", text)))


def validate_speed(words_per_minute):
    if type(words_per_minute) is not int or not 40 <= words_per_minute <= 1000:
        raise ValueError("site.reading_words_per_minute must be an integer from 40 to 1000")
    return words_per_minute


def word_label(words):
    if words % 10 == 1 and words % 100 != 11:
        return "слово"
    if words % 10 in {2, 3, 4} and words % 100 not in {12, 13, 14}:
        return "слова"
    return "слов"


def minute_label(minutes):
    if minutes == 0:
        return "менее 1 минуты"
    noun = "минута" if minutes % 10 == 1 and minutes % 100 != 11 else (
        "минуты" if minutes % 10 in {2, 3, 4} and minutes % 100 not in {12, 13, 14} else "минут"
    )
    return f"≈ {minutes} {noun} чтения"


@dataclass
class ReadingBlock:
    start: int
    start_end: int
    tag: str
    text: list = field(default_factory=list)
    heading_end: int | None = None
    heading_seen: bool = False


class _ProseParser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.offsets = [0]
        self.offsets.extend(match.end() for match in re.finditer("\n", source))
        self.stack = []
        self.active = []
        self.blocks = []

    def absolute_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def separator(self):
        for block in self.active:
            block.text.append(" ")

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set((attrs.get("class") or "").split())
        inherited_skip = bool(self.stack and self.stack[-1][1])
        skip = inherited_skip or tag in EXCLUDED_TAGS or bool(classes & EXCLUDED_CLASSES)
        if tag in BOUNDARIES or skip:
            self.separator()
        started = None
        if "lvl" in classes and not skip:
            start = self.absolute_offset()
            started = ReadingBlock(start, start + len(self.get_starttag_text()), self.get_starttag_text())
            self.active.append(started)
            self.blocks.append(started)
        headings = []
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and not skip:
            for block in self.active:
                if not block.heading_seen:
                    block.heading_seen = True
                    headings.append(block)
        if tag not in VOID:
            self.stack.append((tag, skip, started, headings))

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        matching = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if matching is None:
            return
        frames = self.stack[matching:]
        del self.stack[matching:]
        for frame_tag, skipped, started, headings in reversed(frames):
            if frame_tag in BOUNDARIES or skipped:
                self.separator()
            if frame_tag == tag:
                end = self.source.find(">", self.absolute_offset()) + 1
                for block in headings:
                    block.heading_end = end
            if started is not None:
                self.active.remove(started)

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            return
        for block in self.active:
            block.text.append(data)

    def handle_entityref(self, name):
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name):
        self.handle_data(unescape(f"&#{name};"))


def block_metrics(source, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Return prose metrics for each .lvl block, in authored order.

    Minutes are rounded up for estimates >= one minute. A shorter block has
    minutes=0 and the visible label 'less than one minute', avoiding false
    precision. Future checks can call this same function.
    """
    validate_speed(words_per_minute)
    parser = _ProseParser(source)
    parser.feed(source)
    parser.close()
    result = []
    for block in parser.blocks:
        words = count_words("".join(block.text))
        minutes = math.ceil(words / words_per_minute) if words >= words_per_minute else 0
        result.append({"block": block, "words": words, "minutes": minutes})
    return result


def annotate_html(source, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Add static reading labels while retaining original heading IDs/markup.

    Generated labels are replaceable and excluded from prose. Reprocessing
    an already annotated page therefore preserves counts and output bytes.
    """
    validate_speed(words_per_minute)
    source = GENERATED_BADGE.sub("", source)
    edits = []
    for item in block_metrics(source, words_per_minute):
        block, words, minutes = item["block"], item["words"], item["minutes"]
        clean_tag = READING_ATTRIBUTE.sub("", block.tag)
        marked_tag = clean_tag[:-1] + (
            f' data-reading-words="{words}" data-reading-minutes="{minutes}"'
            f' data-reading-wpm="{words_per_minute}">'
        )
        edits.append((block.start, block.start_end, marked_tag))
        badge = (
            f'<p class="reading-meta" data-docs-kit-reading="true"'
            f' data-reading-words="{words}" data-reading-minutes="{minutes}">'
            f'{words} {word_label(words)} · {minute_label(minutes)}</p>'
        )
        position = block.heading_end if block.heading_end is not None else block.start_end
        edits.append((position, position, badge))
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source
