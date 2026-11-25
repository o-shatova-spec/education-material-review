import csv
import re
from io import BytesIO, StringIO
from urllib.parse import urlsplit

import pymupdf
import streamlit as st
from docx import Document

st.set_page_config(page_title='Експертиза навчальних посібників', page_icon='📚', layout='wide')

PRAVOPYS_URL = ('https://mova.gov.ua/storage/app/sites/19/2026/rishennja-komisiji/'
                '01-03/sdm-ukrayinskii-pravopis-vidannia.pdf')

# Рекомендації нижче — редакторські гіпотези, а не нормативні висновки.
RULES = [
    (r'\bприйма(?:ти|є|ють|в|ла|ли)\s+участь\b', 'Можливий русизм',
     'Розглянути «брати участь» у відповідній граматичній формі.'),
    (r'\bна\s+протязі\b', 'Контекстне слововживання',
     'Якщо йдеться про тривалість часу, використати «протягом».'),
    (r'\bу\s+відповідності\s+до\b', 'Калькована конструкція',
     'Рекомендовано «відповідно до».'),
    (r'\bпо\s+відношенню\s+до\b', 'Стилістика',
     'Розглянути «щодо», «стосовно» або «відносно» за змістом.'),
    (r'\bпо\s+причині\b', 'Калькована конструкція',
     'Розглянути «через», «з причини».'),
    (r'\bявля(?:є|ють)ться\b', 'Можливий русизм',
     'Перевірити можливість заміни на «є» або «становлять».'),
    (r'\bв\s+кінцевому\s+рахунку\b', 'Калькована конструкція',
     'Розглянути «зрештою», «у підсумку».'),
    (r'\bслідуюч(?:ий|а|е|і|ого|ому)\b', 'Контекстне слововживання',
     'Якщо йдеться про порядок, розглянути «наступний».'),
    (r'\bданий\s+(?:матеріал|розділ|посібник|параграф)\b', 'Стилістика',
     'Розглянути заміну «даний» на «цей», якщо немає спеціального значення.'),
    (r'\bне\s+дивлячись\s+на\b', 'Контекстне слововживання',
     'Якщо йдеться про допуст, розглянути «незважаючи на».'),
    (r'\bпривести\s+приклад\b', 'Стилістика',
     'У навчальному тексті рекомендовано «навести приклад».'),
    (r'\bзгідно\s+наказу\b', 'Граматичне керування',
     'Перевірити керування: «згідно з наказом».'),
    (r'\bвірна\s+відповідь\b', 'Контекстне слововживання',
     'У значенні правильної відповіді рекомендовано «правильна відповідь».'),
]

# Англіцизм != помилка. Прапорець лише для редакторської оцінки доречності.
ENGLISH_TERMS = {
    'фідбек': 'зворотний зв’язок',
    'дедлайн': 'кінцевий термін',
    'чекліст': 'контрольний список',
    'апдейт': 'оновлення',
    'воркшоп': 'практичний семінар / майстерня',
    'скіл': 'навичка',
    'кейс': 'приклад / ситуація / випадок (залежно від контексту)',
    'контент': 'зміст / матеріали (якщо доречно)',
}

# Домен є індикатором для перевірки, але не доказом походження автора.
RU_PLATFORM_HOSTS = {'vk.com', 'vk.ru', 'ok.ru', 'yandex.ru', 'mail.ru', 'rutube.ru'}
URL_RE = re.compile(r'(?i)\b(?:https?://|www\.)[^\s<>"«»]+')
WORD_RE = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)


def add_finding(findings, location, category, fragment, advice, evidence='Евристичне правило'):
    findings.append({
        'Місце': location,
        'Категорія': category,
        'Фрагмент': fragment[:350],
        'Рекомендація': advice,
        'Підстава / метод': evidence,
        'Статус': 'Потребує перевірки фахівцем',
    })


def extract_document(file):
    blocks = []
    links = []
    data = file.getvalue()

    if file.name.lower().endswith(".pdf"):
        with pymupdf.open(
            stream=data,
            filetype="pdf"
        ) as pdf:
            for page_no, page in enumerate(pdf, 1):
                text = page.get_text("text")
                if text.strip():
                    blocks.append(
                        (f"Сторінка PDF {page_no}", text)
                    )

                for link in page.get_links():
                    url = link.get("uri")
                    if url:
                        links.append(
                            (f"Сторінка PDF {page_no}", url)
                        )

    elif file.name.lower().endswith(".docx"):
        doc = Document(BytesIO(data))

        for index, paragraph in enumerate(doc.paragraphs, 1):
            if paragraph.text.strip():
                blocks.append(
                    (f"Абзац {index}", paragraph.text)
                )

        for t_no, table in enumerate(doc.tables, 1):
            for r_no, row in enumerate(table.rows, 1):
                for c_no, cell in enumerate(row.cells, 1):
                    if cell.text.strip():
                        location = (
                            f"Таблиця {t_no}, рядок {r_no}, "
                            f"комірка {c_no}"
                        )
                        blocks.append((location, cell.text))

        # Зовнішні гіперпосилання Word
        for rel in doc.part.rels.values():
            if rel.is_external and "hyperlink" in rel.reltype:
                links.append(
                    ("Гіперпосилання DOCX", str(rel.target_ref))
                )

    return blocks, links

def analyze_source(url, location, findings, seen):
    url = url.strip().rstrip('.,;:!?)]}»')
    if not url or url in seen:
        return
    seen.add(url)
    normalized = url if url.startswith(('http://', 'https://')) else 'https://' + url
    try:
        host = (urlsplit(normalized).hostname or '').lower().rstrip('.')
    except ValueError:
        return
    if not host:
        return
    if host.endswith('.ru') or host.endswith('.рф') or host in RU_PLATFORM_HOSTS:
        add_finding(
            findings, location, 'Джерело: потребує перевірки', url,
            'Перевірити власника, автора, бібліографічні дані, актуальність та допустимість використання джерела. Домен сам собою не доводить походження автора.',
            'Домен / відома вебплатформа; НЕ висновок про походження',
        )


def analyze(blocks, links):
    findings = []
    seen_urls = set()
    total_chars = 0
    for location, text in blocks:
        total_chars += len(text)
        for pattern, category, advice in RULES:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                a, b = max(0, match.start()-55), min(len(text), match.end()+55)
                add_finding(findings, location, category, text[a:b].replace('\n', ' '), advice)

        for term, alternative in ENGLISH_TERMS.items():
            pattern = rf'(?<!\w){re.escape(term)}(?!\w)'
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                a, b = max(0, match.start()-40), min(len(text), match.end()+40)
                add_finding(findings, location, 'Англіцизм: оцінити доречність',
                            text[a:b].replace('\n', ' '),
                            f'Перевірити, чи точніше за контекстом: «{alternative}». Не замінювати усталені наукові терміни автоматично.')

        for m in re.finditer(r'[ \t]{2,}', text):
            add_finding(findings, location, 'Оформлення',
                        text[max(0, m.start()-25):m.end()+25].replace('\n', ' '),
                        'Перевірити надлишкові пробіли.')
        for m in URL_RE.finditer(text):
            analyze_source(m.group(), location, findings, seen_urls)

        # Лише індикатор складності; не офіційна вікова норма.
        for sentence in re.split(r'(?<=[.!?])\s+', text.replace('\n', ' ')):
            if len(WORD_RE.findall(sentence)) > 35:
                add_finding(findings, location, 'Вікова доступність: довге речення',
                            sentence[:280], 'Перевірити зрозумілість для обраного класу; за потреби спростити.',
                            'Евристика: понад 35 слів; не нормативний поріг')

    for location, url in links:
        analyze_source(url, location, findings, seen_urls)
    return findings, total_chars


def csv_bytes(findings):
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(findings[0]), delimiter=';')
    writer.writeheader()
    writer.writerows(findings)
    return out.getvalue().encode('utf-8-sig')


st.title('Експертиза навчальних посібників')
st.caption('Прототип: мовні конструкції, англіцизми, джерела та попередня вікова доступність')
st.warning('Використовуйте лише відкриті або спеціально підготовлені матеріали. Не завантажуйте конфіденційні документи УІРО.')
st.markdown(f'Нормативне джерело: [Український правопис (2026)]({PRAVOPYS_URL}). PDF є джерелом норм, але не автоматичним коректором.')

st.header('1. Відомості про посібник')
name = st.text_input('Назва посібника')
subject = st.text_input('Навчальний предмет')
grade = st.selectbox('Клас', list(range(5, 13)))
kind = st.selectbox('Тип', ['Навчальний посібник', 'Навчально-методичний посібник', 'Комплект матеріалів', 'Окремий урок'])

st.header('2. Документ')
file = st.file_uploader('PDF або DOCX', type=['pdf', 'docx'])
if file and st.button('Перевірити матеріал', type='primary'):
    try:
        blocks, hyperlinks = extract_document(file)
        findings, chars = analyze(blocks, hyperlinks)
        st.header('3. Результати')
        st.write(f'**{name or file.name}** · {subject or "Предмет не зазначено"} · {grade} клас · {kind}')
        a, b, c = st.columns(3)
        a.metric('Символів', chars)
        b.metric('Текстових блоків', len(blocks))
        c.metric('Зауважень для перевірки', len(findings))
        if not blocks:
            st.warning('Текст не витягнуто. Можливо, PDF містить скановані сторінки.')
        if findings:
            categories = sorted({item['Категорія'] for item in findings})
            selected = st.multiselect('Категорії', categories, default=categories)
            st.dataframe([f for f in findings if f['Категорія'] in selected],
                         use_container_width=True, hide_index=True)
            st.download_button('Завантажити повний реєстр (CSV)', csv_bytes(findings),
                               file_name='review_findings.csv', mime='text/csv')
        elif blocks:
            st.info('За наявними евристичними правилами сигналів не знайдено. Це не означає, що помилок немає.')
        st.caption('Домен .ru / .рф позначається для ручної перевірки, а не автоматично визнається забороненим. DOI та назви видавців потребують окремого бібліографічного аналізу. Наукова достовірність цим прототипом не встановлюється.')
    except Exception as exc:
        st.error(f"Помилка оброблення документа: {type(exc).__name__}: {exc}")
        st.exception(exc)

