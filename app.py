
import streamlit as st
from io import BytesIO
from docx import Document
import pymupdf

st.set_page_config(
    page_title="Експертиза освітніх матеріалів",
    page_icon="📚",
    layout="wide"
)

st.title("Інтелектуальна система експертизи освітніх матеріалів")

st.write(
    "Автоматизований аналіз освітніх матеріалів "
    "відповідно до встановлених критеріїв якості."
)

st.warning(
    "Тестова версія. Завантажуйте лише відкриті "
    "або спеціально підготовлені матеріали."
)

st.header("1. Відомості про матеріал")

subject = st.text_input(
    "Навчальний предмет",
    placeholder="Наприклад: Технології"
)

grade = st.selectbox(
    "Клас",
    list(range(5, 13))
)

material_type = st.selectbox(
    "Тип матеріалу",
    ["Урок", "Навчальний посібник", "Комплект уроків"]
)

st.header("2. Завантаження документа")

uploaded_file = st.file_uploader(
    "Оберіть файл PDF або Word",
    type=["pdf", "docx"]
)

if uploaded_file is not None:
    st.info(f"Завантажено: {uploaded_file.name}")

    if st.button("Перевірити матеріал"):
        try:
            file_bytes = uploaded_file.getvalue()

            if uploaded_file.name.lower().endswith(".pdf"):
                with pymupdf.open(
                    stream=file_bytes,
                    filetype="pdf"
                ) as pdf:
                    text = "\n".join(
                        page.get_text()
                        for page in pdf
                    )
            else:
                doc = Document(BytesIO(file_bytes))
                text = "\n".join(
                    paragraph.text
                    for paragraph in doc.paragraphs
                )

            st.header("3. Результати аналізу")

            st.write("Предмет:", subject)
            st.write("Клас:", grade)
            st.write("Тип матеріалу:", material_type)
            st.write("Кількість символів:", len(text))

            if text.strip():
                st.success("Текст документа успішно опрацьовано.")
                st.info(
                    "Наступний етап — підключення "
                    "модуля перевірки за 11 критеріями."
                )
            else:
                st.warning(
                    "Текст не виявлено. "
                    "Можливо, документ містить скановані сторінки."
                )

        except Exception:
            st.error(
                "Помилка читання документа. "
                "Перевірте формат файлу."
            )
