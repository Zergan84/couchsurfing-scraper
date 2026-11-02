"""
gender_classifier.py - Высокоточный классификатор пола и состава хостов.
"""

import re
from typing import Tuple

try:
    import gender_guesser.detector as gender_detector
    _GD = gender_detector.Detector(case_sensitive=False)
except ImportError:
    _GD = None

JP_MALE_NAMES = {
    "ryu", "hiro", "takumi", "hikaru", "naoya", "hayase", "koji", "yamamoto", "kenya",
    "yujiro", "taka", "rintaro", "ryuhei", "toshihiro", "ryuichi", "seiya", "taro",
    "daiki", "shota", "kenta", "kazuki", "yusuke", "kenji", "shinji", "masashi",
    "sho", "ren", "sota", "haruto", "yuto", "soma", "minato", "atsushi", "keisuke",
    "tomoya", "kosuke", "yuya", "daisuke", "jun", "taiki", "satoshi", "akira", "takashi",
    "ken", "shin", "hidenori", "takeshi", "makoto", "yuji", "kohei", "kazuma", "kazuhiko",
    "masahiro", "yoshiki", "ryota", "sosuke", "kazuya", "shun", "yuuki", "yukihiro",
    "dec", "decdec", "mamad", "horacio", "karthik", "prag78m", "andreas", "arnaud",
    "alessandro", "hiroshi", "hirochan", "riota", "ryo", "rikushi", "tomofumi",
    "nobu", "ryuya", "yosh", "tsuyoshi", "essakhan", "hau", "song", "wei", "shitetsu",
    "masakazu", "ryosuke", "boyi", "homare", "marki", "essahunza", "kentaro", "yukihiro"
}

JP_FEMALE_NAMES = {
    "nozomi", "sakura", "yui", "aoi", "hina", "rin", "mio", "mei", "yuna", "akari",
    "koharu", "hana", "ayaka", "asuka", "nanami", "rina", "yuka", "misaki",
    "erika", "kana", "sayaka", "mai", "chika", "mika", "tomomi", "ayumi", "megumi",
    "shiori", "haruka", "marion", "sophie", "julia", "elena", "maria", "emma", "sarah",
    "charlotte", "laura", "anna", "tessa", "alice", "chihiro", "reiko", "keiko",
    "yoko", "kumiko", "midori", "naoko", "mariko", "tomoko", "junko", "noriko",
    "ayami", "eimi", "yuko", "cha", "robyn", "ojo", "rie", "saki", "urara", "yara",
    "arina", "rita", "cintia"
}

COUPLE_TEXT_PATTERNS = [
    r"\bmy\s+wife\s+and\s+i\b",
    r"\bmy\s+husband\s+and\s+i\b",
    r"\bmy\s+partner\s+and\s+i\b",
    r"\bwith\s+my\s+boyfriend\b",
    r"\bwith\s+my\s+girlfriend\b",
    r"\bwith\s+my\s+wife\b",
    r"\bwith\s+my\s+husband\b",
    r"\bwith\s+my\s+partner\b",
    r"\bwe\s+are\s+a\s+couple\b",
    r"\bour\s+(?:flat|apartment|house|home|place)\b",
    r"\bwe\s+live\s+together\b",
    r"\bwe\s+both\b",
    r"\bhusband\s+and\s+wife\b",
    r"\bme\s+and\s+my\s+(?:wife|husband|partner|boyfriend|girlfriend)\b",
]

SELF_FEMALE_PATTERNS = [
    r"\b(?:i\s*am|i['’]?m)\s+(?:a\s+)?(?:girl|woman|lady|female)\b",
    r"\b(?:female\s+solo\s+trave[l]+er)\b",
    r"\b(?:she/her|her/she)\b",
    r"\bactress\b",
]

SELF_MALE_PATTERNS = [
    r"\b(?:i\s*am|i['’]?m)\s+(?:a\s+)?(?:guy|dude|boy|man)\b",
    r"\b(?:he/him|him/he)\b",
    r"\bactor\b",
    r"\bmr\.\b",
]


def classify_host(name: str, about_text: str = "", username: str = "") -> Tuple[str, str]:
    """
    Определяет пол (Male, Female, Couple, Unknown) и тип размещения (solo, couple).
    Возвращает (estimated_gender, host_type).
    """
    about = (about_text or "").lower()
    about = about.replace("’", "'").replace("`", "'")

    clean_name = re.sub(r"[\s\.,_-]+[A-Za-z]\.?$", "", name).strip()
    
    # 1. Проверка на Couple в имени
    if re.search(r"(&|\band\b|\bet\b|\+|\/)", clean_name, re.I):
        return "Couple", "couple"

    # Проверка на Couple в тексте
    for pat in COUPLE_TEXT_PATTERNS:
        if re.search(pat, about, re.I):
            return "Couple", "couple"

    host_type = "solo"

    # 2. Анализ имени и токенов
    tokens = re.split(r"[\s&,+/._-]+", clean_name.lower())
    first_name = tokens[0] if tokens else ""

    # Проверка на японские иероглифы/кану
    if "ユウコ" in name or "ゆうこ" in name or "さくら" in name or "ゆき" in name:
        return "Female", host_type

    # Прямое совпадение по проверенным словарям
    if first_name in JP_FEMALE_NAMES:
        return "Female", host_type
    if first_name in JP_MALE_NAMES:
        return "Male", host_type

    # Проверка username (например, kentaro-shibamoto, ryosukekimura)
    u_tokens = re.split(r"[\s&,+/._-]+", (username or "").lower())
    for ut in u_tokens:
        if ut in JP_FEMALE_NAMES:
            return "Female", host_type
        if ut in JP_MALE_NAMES:
            return "Male", host_type
        for m_name in JP_MALE_NAMES:
            if len(m_name) >= 4 and ut.startswith(m_name):
                return "Male", host_type
        for f_name in JP_FEMALE_NAMES:
            if len(f_name) >= 4 and ut.startswith(f_name):
                return "Female", host_type

    # Морфологические паттерны японских имен в ромадзи
    if len(first_name) >= 4:
        if any(first_name.endswith(sfx) for sfx in ("suke", "taro", "hiko", "ichi", "kazu", "hei", "shi", "ro", "to", "ji")):
            return "Male", host_type
        if any(first_name.endswith(sfx) for sfx in ("ko", "ka", "na")):
            return "Female", host_type

    # 3. Самоопределение в тексте ("I am a guy", "I am a girl", pronouns)
    for pat in SELF_FEMALE_PATTERNS:
        if re.search(pat, about, re.I):
            return "Female", host_type

    for pat in SELF_MALE_PATTERNS:
        if re.search(pat, about, re.I):
            return "Male", host_type

    # 4. Проверка через gender-guesser
    if _GD and first_name:
        res = _GD.get_gender(first_name)
        if res in ("female", "mostly_female"):
            return "Female", host_type
        if res in ("male", "mostly_male"):
            return "Male", host_type

    return "Unknown", host_type
