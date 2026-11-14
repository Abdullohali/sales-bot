"""Admin panel languages, built on sqladmin's i18n (requires `babel`).

- The visitor picks the language in the top bar (`?lang=uz`), it is kept in a cookie;
  otherwise the browser's Accept-Language decides, otherwise DEFAULT_LANGUAGE.
- sqladmin's own interface texts: its bundled ru/en catalogs + our Uzbek one.
- Our texts (view names, column labels, pages) come from app/i18n via `lazy()` / `pt()`.
"""

from babel.support import LazyProxy, NullTranslations
from sqladmin import i18n as sqladmin_i18n
from sqladmin.i18n import I18nConfig, get_locale

from app.i18n import LANGS, default_lang, normalize, t
from app.i18n.sqladmin_uz import MESSAGES as SQLADMIN_UZ


class _DictTranslations(NullTranslations):
    """In-memory catalog (no .po/.mo build step) with a fallback catalog for missing strings."""

    def __init__(self, messages: dict[str, str], fallback: NullTranslations) -> None:
        super().__init__()
        self._messages = messages
        self.add_fallback(fallback)

    def gettext(self, message: str) -> str:
        return self._messages.get(message) or super().gettext(message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        return self._messages.get(singular if n == 1 else plural) or super().ngettext(singular, plural, n)


def install_locales() -> I18nConfig:
    """Limit sqladmin to our three languages and register the Uzbek catalog.

    sqladmin keeps its locale list and catalogs in module globals (checked by its
    LocaleMiddleware on every request), so they are updated in place.
    """
    sqladmin_i18n.SUPPORTED_LOCALES[:] = list(LANGS)
    sqladmin_i18n.translations["uz"] = _DictTranslations(SQLADMIN_UZ, sqladmin_i18n.translations["en"])
    return I18nConfig(default_locale=default_lang(), language_switcher=list(LANGS))


def panel_lang() -> str:
    """Language of the current admin panel request."""
    return normalize(get_locale()) or default_lang()


def pt(key: str, **kwargs) -> str:
    """Translate into the current panel language."""
    return t(panel_lang(), key, **kwargs)


class _LazyText(LazyProxy):
    """LazyProxy is unhashable, but sqladmin uses column labels as dict keys: hash by the message key."""

    def __hash__(self) -> int:
        return hash(self._args)


def lazy(key: str) -> str:
    """Translation resolved when rendered, for class-level attributes (view names, labels)."""
    return _LazyText(pt, key, enable_cache=False)  # type: ignore[return-value]
