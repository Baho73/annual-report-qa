"""M-UI: демонстрация ассистента."""

# FILE: app.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: показать работу ассистента вживую: вопрос, ответ со ссылками на страницы, источник и режим поиска.
#   SCOPE: поле ввода, выбор режима, вывод ответа, раскрывающийся блок источников, флаги непроверенных чисел.
#   DEPENDS: M-ANSWER, M-ROUTER, M-PARSE
#   LINKS: M-UI, V-M-UI
#   ROLE: SCRIPT
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   main - страница Streamlit целиком
#   SAMPLES - вопросы задания для быстрого запуска на защите
# END_MODULE_MAP

import streamlit as st

from report_qa import config
from report_qa.answer import ask
from report_qa.parse import load_sections
from report_qa.router import route

SAMPLES = [
    "Какая была выручка компании в 2025 году?",
    "Какие направления бизнеса росли быстрее остальных? Подтвердите цифрами.",
    "Какие основные риски компания выделяет для бизнеса?",
    "Почему чистая прибыль выросла сильнее выручки?",
    "Стоит ли инвестировать в эту компанию?",
    "Сколько сотрудников компании работает в Германии?",
]


def main():
    st.set_page_config(page_title="Ассистент по годовому отчёту", layout="wide")
    st.title("Ассистент по годовому отчёту")
    st.caption("Годовой отчёт МКПАО «Яндекс» за 2025 год, 201 страница. "
               "Каждое число сопровождается страницей источника.")

    with st.sidebar:
        st.subheader("Режим поиска")
        mode = st.radio(
            "Как выбираются данные для ответа",
            ["router", "full"],
            format_func=lambda m: {
                "router": "Роутер по разделам (дёшево)",
                "full": "Весь документ (дорого)",
            }[m],
        )
        st.caption(
            "Роутер читает оглавление и выбирает разделы: 7-30 тысяч токенов "
            "вместо 180 тысяч. Полный контекст ничего не теряет, но платит за это."
        )
        st.divider()
        st.caption(f"Модель ответа: `{config.MODELS['answer']}`")
        st.caption(f"Модель роутера: `{config.MODELS['router']}`")

    question = st.text_input("Вопрос", value=SAMPLES[0])
    st.caption("Примеры: " + " · ".join(f"«{s[:38]}…»" for s in SAMPLES[1:4]))

    if not st.button("Спросить", type="primary"):
        return

    sections, section_ids, effective = load_sections(), None, mode
    with st.spinner("Выбираю разделы…" if mode == "router" else "Читаю документ…"):
        if mode == "router":
            decision = route(question, sections)
            section_ids, effective = decision.section_ids, decision.mode
            if decision.need_full:
                st.info("Вопрос охватывает весь документ — отвечаю по полному контексту.")

    with st.spinner("Отвечаю…"):
        answer = ask(question, mode=effective, section_ids=section_ids)

    st.markdown(answer.text)

    if answer.unverified_numbers:
        # Числа без подтверждения не замалчиваются: это главный флаг доверия.
        st.warning("Числа, которых нет в поданном контексте: "
                   + ", ".join(answer.unverified_numbers))

    columns = st.columns(4)
    columns[0].metric("Токенов", f"{answer.prompt_tokens:,}".replace(",", " "))
    columns[1].metric("Задержка", f"{answer.latency_s} с")
    columns[2].metric("Цена", f"${answer.cost_usd}")
    columns[3].metric("Страниц в ответе", len(answer.cited_pages))

    with st.expander("Источник"):
        st.write(f"**Режим:** `{answer.mode}`")
        st.write(f"**Страницы в ответе:** {answer.cited_pages or 'не указаны'}")
        titles = {s["id"]: s for s in sections}
        st.write("**Поданные разделы:**")
        for sid in answer.section_ids:
            section = titles.get(sid)
            if section:
                st.write(f"- {section['title']} (стр. {section['page_from']}–{section['page_to']})")


if __name__ == "__main__":
    main()
