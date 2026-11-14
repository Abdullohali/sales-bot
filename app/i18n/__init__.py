"""Localization: Uzbek (uz), Russian (ru), English (en).

All user-facing text of the bot, Excel files and the admin panel lives in the
catalogs `uz.py`, `ru.py`, `en.py` (same keys in each, checked by tests).
Placeholders use str.format syntax: "Накладная №{id}".

Business data (client/product names, units) is never translated.
"""

from functools import lru_cache

from app.i18n import en, ru, uz

LANGS: tuple[str, ...] = ("uz", "ru", "en")
FALLBACK = "ru"  # the original language of the project; used when a key is missing

CATALOGS: dict[str, dict[str, str]] = {"uz": uz.MESSAGES, "ru": ru.MESSAGES, "en": en.MESSAGES}

# Shown in language pickers; each name is written in its own language.
LANG_NAMES: dict[str, str] = {"uz": "🇺🇿 Oʻzbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


def default_lang() -> str:
    from app.config import get_settings

    lang = get_settings().DEFAULT_LANGUAGE
    return lang if lang in LANGS else FALLBACK


def normalize(code: str | None) -> str | None:
    """'uz', 'ru-RU', 'en_US' -> supported code, otherwise None."""
    if not code:
        return None
    base = code.replace("_", "-").split("-")[0].strip().lower()
    return base if base in LANGS else None


def resolve(code: str | None) -> str:
    return normalize(code) or default_lang()


def t(lang: str | None, key: str, **kwargs) -> str:
    """Translate `key` into `lang` (unknown/None lang -> default language)."""
    catalog = CATALOGS.get(lang or "") or CATALOGS[default_lang()]
    text = catalog.get(key)
    if text is None:
        text = CATALOGS[FALLBACK].get(key, key)
    return text.format(**kwargs) if kwargs else text


@lru_cache
def variants(key: str) -> frozenset[str]:
    """The text of `key` in every language. Used to match reply-keyboard buttons."""
    return frozenset(CATALOGS[lang][key] for lang in LANGS if key in CATALOGS[lang])
