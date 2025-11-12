import io, os, json, zipfile, tempfile
import streamlit as st
from openai import OpenAI
# ---------- Standaar h5p basis doc voor mc ----------

from pathlib import Path
TEMPLATE_PATH = Path("templates/basisMC.h5p")

def load_default_template_bytes() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()
# ----------

st.set_page_config(page_title="H5P generator (MC)", page_icon="🎯")

# ---------- H5P helpers (afgeleid van jouw notebook) ----------
def make_multichoice_content_fixed(
    question_text: str,
    answers: list,
    question_title: str,
    randomize: bool = True,
    single_choice: bool = True,
    show_solution_button: bool = True,
    show_check_button: bool = True,
    show_retry_button: bool = True,
):
    # Normaliseer antwoorditems ({text, correct, tip?})
    norm_answers = []
    for a in answers:
        text = a.get("text", "").strip()
        # H5P verwacht HTML-string; simpele plain text mag ook, maar we wrappen even in <p> voor zekerheid
        if not (text.startswith("<") and text.endswith(">")):
            text = f"<p>{text}</p>"
        norm_answers.append({
            "text": text,
            "correct": bool(a.get("correct", False)),
            "tipsAndFeedback": {
                "tip": (a.get("tip", "") or ""),
                "chosenFeedback": "",
                "notChosenFeedback": ""
            }
        })

    content = {
        # Top-level velden (zo verwacht MultiChoice ze)
        "questionTitle": question_title,
        "question": f"<p>{question_text}</p>",
        "answers": norm_answers,
        "behaviour": {
            "showSolutionsRequiresInput": False,
            "singleChoice": bool(single_choice),
            "randomAnswers": bool(randomize),
            "enableSolutionsButton": bool(show_solution_button),
            "enableRetry": bool(show_retry_button),
            "enableCheckButton": bool(show_check_button),
            "autoCheck": False
        },
        "media": { "type": "image", "params": { "file": { "path": "" } } },
        "overallFeedback": [{
            "from": 0,
            "to": 100,
            "feedback": "Je behaalde @score van de @total punten."
        }]
    }
    return content


 # zoals jouw notebook doet. :contentReference[oaicite:8]{index=8}

def replace_h5p_content_bytes(h5p_bytes: bytes, new_content: dict, ensure_pretty: bool = True) -> bytes:
    """
    Neemt een basis .h5p (bytes), vervangt content/content.json door new_content (dict),
    en geeft de bijgewerkte .h5p als bytes terug. Gebaseerd op jouw replace_h5p_content. :contentReference[oaicite:9]{index=9}
    """
    # JSON serialiseren
    json_str = json.dumps(new_content, ensure_ascii=False, indent=(2 if ensure_pretty else None))

    # Uitpakken naar tmp, vervangen, inpakken
    with tempfile.TemporaryDirectory() as tmpdir:
        src_zip = os.path.join(tmpdir, "src.h5p")
        with open(src_zip, "wb") as f:
            f.write(h5p_bytes)

        extract_dir = os.path.join(tmpdir, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(src_zip, "r") as zin:
            zin.extractall(extract_dir)

        # content/content.json vervangen
        content_dir = os.path.join(extract_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        content_path = os.path.join(content_dir, "content.json")
        with open(content_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # Terug zippen
        out_zip_path = os.path.join(tmpdir, "updated.h5p")
        with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, extract_dir).replace("\\", "/")
                    zout.write(abs_path, rel_path)

        return open(out_zip_path, "rb").read()

# ---------- Model-aanroep zoals prompt_to_multichoice ----------

def generate_mc_json_from_prompt(client: OpenAI, prompt_text: str, title: str = "AI gegenereerde oefening") -> dict:
    """
    Vraagt JSON terug met velden: question_text, answers[], question_title.
    Daarna wordt dit omgezet naar H5P.MultiChoice content.json via make_multichoice_content_fixed.
    Compatibel met openai 2.7.1 (chat.completions.create)
    """
    system_prompt = (
        "Je bent een hulpagent die meerkeuzevragen maakt voor H5P. "
        "Antwoord ALLEEN als één JSON-object met exact deze velden:\n"
        '{ "question_text": "…", "answers":[{"text":"…","correct":true|false}], "question_title":"…"}\n'
        "Regels:\n"
        "- Exact één juist antwoord (één item met correct=true).\n"
        "- Geen uitleg, geen codeblokken, alleen JSON."
    )

    # Gebruik chat.completions (juiste call voor v2.7.1)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text},
        ]
    )

    # Antwoord uitlezen en JSON laden
    raw = resp.choices[0].message.content.strip()
    data = json.loads(raw)

    # Validatie: exact 1 correct antwoord
    correct_count = sum(1 for a in data.get("answers", []) if a.get("correct"))
    if correct_count != 1:
        raise ValueError(f"Er moet exact 1 juist antwoord zijn, maar ik tel {correct_count}.")

    # Naar H5P content.json
    content = make_multichoice_content_fixed(
        question_text=data["question_text"],
        answers=data["answers"],
        question_title=(data.get("question_title") or title)
    )
    return content


# ---------- UI ----------

from pathlib import Path
import streamlit as st

LOGO_PATH = Path("logo.png")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=400)  # pas breedte aan naar wens


st.title("🎯 H5P-generator (MultiChoice) – prompt → H5P")
st.write("Geef een **prompt** op, upload een **basis .h5p**, en download je **nieuwe .h5p**.")

with st.sidebar:
    st.header("🔑 API-sleutel")
    api_key = st.text_input("OpenAI API key (anders wordt secrets gebruikt)", type="password")
    if not api_key:
        api_key = st.secrets.get("OPENAI_API_KEY", "")

    model_ok = bool(api_key)
    if not model_ok:
        st.info("Zet een key in secrets of vul ze hierboven in.")

prompt_text = st.text_area("Je prompt", "Maak een meerkeuzevraag: hoe bak ik frietjes?")
uploaded_h5p = st.file_uploader("Upload basis .h5p (MultiChoice)", type=["h5p"], accept_multiple_files=False)

col1, col2 = st.columns(2)
with col1:
    run = st.button("🧠 Genereer H5P-JSON")
with col2:
    build = st.button("📦 Bouw & download H5P")

# Session state voor JSON payload
if "h5p_content_json" not in st.session_state:
    st.session_state["h5p_content_json"] = None

if run:
    if not model_ok:
        st.error("Geen API-sleutel gevonden.")
    else:
        try:
            client = OpenAI(api_key=api_key)
            content = generate_mc_json_from_prompt(client, prompt_text)
            st.session_state["h5p_content_json"] = content
            st.success("JSON gegenereerd!")
            st.code(json.dumps(content, ensure_ascii=False, indent=2), language="json")
        except Exception as e:
            st.error(f"Fout bij genereren: {e}")

# ----------
use_builtin = st.checkbox("Gebruik ingebouwde basis .h5p", value=True)
uploaded_h5p = None
if not use_builtin:
    uploaded_h5p = st.file_uploader("Upload basis .h5p (MultiChoice)", type=["h5p"], accept_multiple_files=False)

# Bewaar template-bytes in session_state zodat je niet bij elke rerun opnieuw hoeft
if "template_bytes" not in st.session_state:
    st.session_state["template_bytes"] = None

if use_builtin:
    try:
        st.session_state["template_bytes"] = load_default_template_bytes()
        st.caption("Ingebouwde template wordt gebruikt.")
    except Exception as e:
        st.error(f"Ingebouwde template niet gevonden: {e}")
else:
    if uploaded_h5p:
        st.session_state["template_bytes"] = uploaded_h5p.getvalue()
        st.caption(f"Geüploade template: {uploaded_h5p.name}")

# Bij 'Bouw & download' gebruik je voortaan st.session_state["template_bytes"]
if build:
    if not st.session_state["template_bytes"]:
        st.error("Er is geen template beschikbaar. Gebruik de ingebouwde of upload er één.")
    elif not st.session_state["h5p_content_json"]:
        st.error("Genereer eerst de H5P-JSON.")
    else:
        try:
            new_bytes = replace_h5p_content_bytes(
                st.session_state["template_bytes"],
                st.session_state["h5p_content_json"],
                ensure_pretty=True
            )
            st.success("Nieuwe H5P klaar om te downloaden.")
            st.download_button(
                "⬇️ Download bijgewerkte H5P",
                data=new_bytes,
                file_name="updated.h5p",
                mime="application/zip"
            )
        except Exception as e:
            st.error(f"Fout bij bouwen: {e}")
