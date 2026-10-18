"""Etat de session Streamlit partage entre les onglets."""
import copy
import os

import streamlit as st

from src.generate import LLMError
from src.i18n import DEFAULT_LANGUAGE, describe, translate
from src.pantry import CATEGORIES

# Protege la cle Groq d'une demo publique ; un rechargement de page remet le compteur a zero.
MAX_LLM_CALLS = int(os.getenv("MAX_LLM_CALLS_PER_SESSION", "60"))

DEFAULTS = {
    "llm_calls": 0,
    "language": DEFAULT_LANGUAGE,
    "view": "search",
    "chef_pending": "",
    "scroll_to": "",
    "shown": 12,
    "scroll_count": 0,
    "searched": False,
    "wanted": [],
    "boost": [],
    "precision_query": "",
    "last_precision": "",
    "other_text": "",
    "selected": None,
    "translations": {},
    "chats": {},
    "plan": None,
    "vision_error": "",
    "vision_done": "",
    "translation_failed": False,
    "show_original": False,
    "pref_basics": True,
    "pref_shopping": "any",
    "pref_diets": [],
    "pref_time": "any",
    "pref_light": False,
    "plan_diets": [],
}


def pantry_key(category_key: str) -> str:
    return f"pantry_{category_key}"


def init_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, copy.deepcopy(value))
    for category in CATEGORIES:
        st.session_state.setdefault(pantry_key(category.key), [])


def count_llm_call() -> None:
    if st.session_state.get("llm_calls", 0) >= MAX_LLM_CALLS:
        raise LLMError("err_llm_quota", max=MAX_LLM_CALLS)
    st.session_state["llm_calls"] = st.session_state.get("llm_calls", 0) + 1


def language() -> str:
    return st.session_state["language"]


def t(key: str, **params) -> str:
    return translate(key, language(), **params)


def error_text(error: Exception) -> str:
    return describe(error, language())


def scroll_to(target: str) -> None:
    """Demande un defilement au prochain affichage : "top", ou l'id d'un element de la page."""
    st.session_state["scroll_to"] = target
    st.session_state["scroll_count"] += 1


def sticky(widget, label: str, pref: str, **kwargs):
    """Streamlit oublie un widget quand il n'est pas affiche (fiche ouverte) : on recopie
    sa valeur dans `pref` a chaque changement, et on s'en sert comme valeur initiale."""
    widget_key = f"w_{pref}"
    if widget_key in st.session_state:
        # Streamlit signale un conflit entre valeur par defaut et valeur deja enregistree.
        for name in ("default", "value", "index"):
            kwargs.pop(name, None)

    def save() -> None:
        st.session_state[pref] = st.session_state[widget_key]

    return widget(label, key=widget_key, on_change=save, **kwargs)


def sticky_options(widget, label: str, pref: str, codes: list, labeler, *, multi: bool = False, **kwargs):
    """Widget a choix dont les libelles changent avec la langue (radio, multiselect).

    Les options sont les libelles eux-memes, sans format_func : Streamlit melange sinon le
    libelle affiche et la valeur interne quand la langue change. La cle contient la langue,
    donc changer de langue cree un widget neuf initialise depuis `pref`, qui garde les codes.
    """
    labels = [labeler(code) for code in codes]
    widget_key = f"w_{pref}_{language()}"
    if widget_key not in st.session_state:
        if multi:
            kwargs["default"] = [labels[codes.index(c)] for c in st.session_state[pref] if c in codes]
        else:
            kwargs["index"] = codes.index(st.session_state[pref])

    def save() -> None:
        chosen = st.session_state[widget_key]
        st.session_state[pref] = (
            [codes[labels.index(v)] for v in chosen] if multi else codes[labels.index(chosen)]
        )

    return widget(label, labels, key=widget_key, on_change=save, **kwargs)
