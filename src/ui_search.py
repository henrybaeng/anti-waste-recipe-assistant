"""Recherche : envie particuliere, filtres, encadres « realisable » et « meilleur achat », cartes."""
import html

import streamlit as st

from src.catalog import Filters
from src.diets import DIETS
from src.format import coverage, format_duration
from src.generate import LLMError, translate_to_english
from src.matching import STAPLES
from src.ui_localize import localized
from src.ui_pantry import gather_wanted
from src.ui_state import error_text, language, scroll_to, sticky, sticky_options, t
from src.validation import validate_craving
from src.visuals import GLYPHS, cover_html

SHOWN = 12
MAX_SHOWN = 96
SEMANTIC_POOL = 60
COLUMNS = 4
LIGHT_KCAL = 400
FULL_MATCH = 100
# Les recettes sans photo sont masquees tant que les illustrations de repli ne sont pas validees.
REQUIRE_PHOTO = True
TIME_FILTERS = {"any": None, "30": 30, "60": 60}
SHOPPING_FILTERS = {"any": None, "max2": 2, "none": 0}


def _filters(diets: tuple, max_minutes, max_calories) -> Filters:
    return Filters(diets=diets, max_minutes=max_minutes, max_calories=max_calories,
                   with_photo=REQUIRE_PHOTO)


@st.cache_data(show_spinner=False, max_entries=64)
def cached_search(_retriever, wanted, basics, diets, max_minutes, max_calories, max_missing, precision,
                  shown=SHOWN):
    """Mis en cache : changer de fiche ou de page ne relance pas le calcul."""
    staples = STAPLES if basics else frozenset()
    found = _retriever.catalog.search(
        list(wanted),
        staples=staples,
        filters=_filters(diets, max_minutes, max_calories),
        max_missing=max_missing,
        limit=max(SEMANTIC_POOL, shown) if precision else shown,
    )
    if precision:
        found = _retriever.semantic_rank(precision, found)
    return found[:shown]


@st.cache_data(show_spinner=False, max_entries=64)
def cached_opportunities(_retriever, wanted, basics, diets, max_minutes, max_calories):
    staples = STAPLES if basics else frozenset()
    return _retriever.catalog.opportunities(
        list(wanted), staples=staples, filters=_filters(diets, max_minutes, max_calories)
    )


def open_recipe(recipe: dict) -> None:
    st.session_state["selected"] = recipe
    scroll_to("top")


def add_boost(item: str) -> None:
    st.session_state["boost"] = [*st.session_state["boost"], item]


def clear_boost() -> None:
    st.session_state["boost"] = []


def show_more() -> None:
    st.session_state["shown"] = min(st.session_state["shown"] + SHOWN, MAX_SHOWN)


def set_shopping(code: str) -> None:
    """Change le filtre d'achats depuis un bouton : le widget, recree, reprend la preference."""
    st.session_state.update(pref_shopping=code, shown=SHOWN)
    for key in [k for k in st.session_state if str(k).startswith("w_pref_shopping_")]:
        del st.session_state[key]
    scroll_to("cards")


def status_badge(recipe: dict, extra_class: str = "") -> str:
    if recipe["missing"]:
        text, kind, glyph = t("to_buy", n=len(recipe["missing"])), "buy", GLYPHS["plus"]
    else:
        text, kind, glyph = t("ready"), "ok", GLYPHS["check"]
    return f'<span class="badge {kind} {extra_class}">{glyph}{text}</span>'


def card_html(recipe: dict, wanted_count: int, title: str, lang: str, label: str = "",
              delay_ms: int = 0) -> str:
    """Carte d'une recette (le titre vient du jeu de donnees : echappe). `label` (« Jour 2 »)
    s'affiche en haut a gauche et pousse le badge d'achats a droite."""
    badges = status_badge(recipe, "right" if label else "")
    if label:
        badges = f'<span class="badge day">{html.escape(label)}</span>{badges}'
    time = ""
    if recipe.get("minutes"):
        time = f'<span class="rc-time">{GLYPHS["clock"]}{format_duration(recipe["minutes"], lang)}</span>'
    pct = coverage(recipe)
    meta = [t("used_of", have=len(recipe["have"]), wanted=wanted_count)]
    if recipe.get("calories"):
        meta.append(f'{GLYPHS["flame"]}{recipe["calories"]:.0f} kcal')
    if recipe.get("rating"):
        meta.append(f'{GLYPHS["star"]}{recipe["rating"]:.1f}')
    return (
        f'<div class="rc" style="animation-delay:{delay_ms}ms"><div class="rc-media">'
        f"{cover_html(recipe, 190)}{badges}{time}</div><div class=\"rc-body\">"
        f'<div class="rc-title">{html.escape(title)}</div>'
        f'<div class="rc-match"><div class="rc-bar"><i class="{"full" if pct == FULL_MATCH else ""}" '
        f'style="width:{pct}%"></i></div><span>{t("match", pct=pct)}</span></div>'
        f'<div class="rc-meta">{"".join(f"<span>{m}</span>" for m in meta)}</div></div></div>'
    )


def render_card(key: str, recipe: dict, wanted_count: int, title: str, label: str = "",
                delay_ms: int = 0) -> None:
    """Toute la carte est cliquable : le bouton, invisible, la recouvre (voir ui_style)."""
    with st.container(key=f"card_{key}"):
        st.markdown(card_html(recipe, wanted_count, title, language(), label, delay_ms),
                    unsafe_allow_html=True)
        st.button(t("open_recipe"), key=f"open_{key}", on_click=open_recipe, args=(recipe,))


def render_results(results: list[dict], wanted_count: int, names: dict) -> None:
    for start in range(0, len(results), COLUMNS):
        columns = st.columns(COLUMNS, gap="medium")
        for offset, column in enumerate(columns):
            index = start + offset
            if index < len(results):
                with column:
                    recipe = results[index]
                    render_card(str(index), recipe, wanted_count,
                                names.get(recipe["title"], recipe["title"]),
                                delay_ms=index % SHOWN * 60)


def render_filters() -> None:
    with st.expander(t("filters_h"), icon=":material/tune:"):
        first, second = st.columns(2)
        with first:
            sticky(st.checkbox, t("basics_label"), "pref_basics", value=st.session_state["pref_basics"])
            sticky_options(st.multiselect, t("diet_label"), "pref_diets", list(DIETS),
                           lambda d: t(f"diet_{d}"), multi=True, placeholder=t("none_option"))
        with second:
            sticky_options(st.radio, t("shopping_label"), "pref_shopping", list(SHOPPING_FILTERS),
                           lambda c: t(f"shop_{c}"), horizontal=True)
            sticky_options(st.radio, t("time_label"), "pref_time", list(TIME_FILTERS),
                           lambda c: t("time_any") if c == "any" else t(f"time_{c}"), horizontal=True)
            sticky(st.checkbox, t("light_label", kcal=LIGHT_KCAL), "pref_light",
                   value=st.session_state["pref_light"])


def ready_html(cookable: int) -> str:
    if not cookable:
        return f'<div class="insight zero"><div class="label">{t("cookable_zero")}</div></div>'
    return (
        f'<div class="insight ready"><div class="big">{cookable}</div>'
        f'<div class="label">{t("cookable_label")}</div></div>'
    )


def best_buy_html(purchase: dict, names: dict) -> str:
    examples = ", ".join(html.escape(names[e]) for e in purchase["examples"])
    return (
        f'<div class="insight best"><div class="kicker">{GLYPHS["bolt"]}{t("best_label")}</div>'
        f'<div class="item">{html.escape(names[purchase["item"]])}</div>'
        f'<div class="unlocks">{t("best_unlocks", count=purchase["count"])}</div>'
        f'<div class="examples">{t("best_examples", examples=examples)}</div></div>'
    )


def render_opportunities(info: dict) -> None:
    purchases = info["purchases"]
    columns = st.columns(2 if purchases else 1, gap="medium")
    columns[0].markdown(ready_html(info["cookable"]), unsafe_allow_html=True)
    # Le classement met en avant les recettes qui utilisent le plus d'aliments, meme avec un
    # achat : ce bouton mene aux recettes pretes que l'encadre annonce.
    if st.session_state["pref_shopping"] == "none":
        columns[0].button(t("see_all"), on_click=set_shopping, args=("any",), icon=":material/list:")
    elif info["cookable"]:
        columns[0].button(t("see_ready"), on_click=set_shopping, args=("none",),
                          icon=":material/check_circle:")
    if purchases:
        texts = [p["item"] for p in purchases] + [e for p in purchases for e in p["examples"]]
        names = localized(texts)
        top = purchases[0]
        with columns[1]:
            st.markdown(best_buy_html(top, names), unsafe_allow_html=True)
            st.button(t("what_if", item=names[top["item"]]), on_click=add_boost, args=(top["item"],),
                      icon=":material/auto_awesome:")
            others = [f"{names[p['item']]} ({p['count']})" for p in purchases[1:]]
            if others:
                st.caption(t("other_purchases", items=", ".join(others)))
    if st.session_state["boost"]:
        boost = localized(st.session_state["boost"])
        st.caption(t("simulated", items=", ".join(boost[b] for b in st.session_state["boost"])))
        st.button(t("cancel_simulated"), on_click=clear_boost, icon=":material/undo:")


def run_search(ingredients_wanted: list[str], craving: str) -> None:
    craving = validate_craving(craving)
    st.session_state.update(
        searched=True,
        wanted=ingredients_wanted,
        boost=[],
        precision_query=translate_to_english(craving) if craving else "",
        selected=None,
        last_precision=craving,
        shown=SHOWN,
    )


def render_search_tab(retriever) -> None:
    craving = ""
    with st.container(key="panel_search"):
        if retriever.semantic_available:
            field, action = st.columns([4, 1.4], vertical_alignment="bottom")
            craving = field.text_input(
                t("craving_label"),
                value=st.session_state["last_precision"],
                placeholder=t("craving_placeholder"),
                key="s_prec",
            )
        else:
            action = st.container()
        clicked = action.button(t("search_button"), type="primary", icon=":material/search:")
    if clicked:
        try:
            with st.spinner(t("searching")):
                run_search(gather_wanted(), craving)
        except (ValueError, LLMError) as err:
            st.error(error_text(err))
            return
    if st.session_state["searched"]:
        render_results_section(retriever)


def render_results_section(retriever) -> None:
    state = st.session_state
    state["translation_failed"] = False
    st.markdown(f'<div class="results-head" id="results"><span class="title">{t("results_h")}</span></div>',
                unsafe_allow_html=True)
    render_filters()
    wanted = tuple(state["wanted"] + state["boost"])
    diets = tuple(state["pref_diets"])
    max_minutes = TIME_FILTERS[state["pref_time"]]
    max_calories = LIGHT_KCAL if state["pref_light"] else None
    render_opportunities(
        cached_opportunities(retriever, wanted, state["pref_basics"], diets, max_minutes, max_calories)
    )
    results = cached_search(
        retriever, wanted, state["pref_basics"], diets, max_minutes, max_calories,
        SHOPPING_FILTERS[state["pref_shopping"]], state["precision_query"], state["shown"],
    )
    if not results:
        st.info(t("no_results"))
        return
    # Une traduction par page de 12 : « Afficher plus » ne retraduit pas les titres deja vus.
    names = {}
    for start in range(0, len(results), SHOWN):
        names.update(localized([r["title"] for r in results[start:start + SHOWN]]))
    ready = sum(1 for r in results if not r["missing"])
    st.markdown(
        f'<div class="results-head" id="cards"><span class="count">'
        f'{t("results_count", n=len(results), ready=ready)}'
        "</span></div>",
        unsafe_allow_html=True,
    )
    if state["translation_failed"]:
        st.caption(t("translation_unavailable"))
    render_results(results, len(wanted), names)
    if len(results) == state["shown"] and state["shown"] < MAX_SHOWN:
        st.button(t("show_more", n=SHOWN), on_click=show_more, key="show_more", icon=":material/expand_more:")
