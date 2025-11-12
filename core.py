# core.py
import os, json, zipfile, tempfile

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
    """Bouwt de juiste content.json structuur voor H5P MultiChoice."""
    norm_answers = []
    for a in answers:
        text = a.get("text", "").strip()
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
        "media": {"type": "image", "params": {"file": {"path": ""}}},
        "overallFeedback": [{
            "from": 0,
            "to": 100,
            "feedback": "Je behaalde @score van de @total punten."
        }]
    }
    return content


def replace_h5p_content_bytes(h5p_bytes: bytes, new_content: dict, ensure_pretty: bool = True) -> bytes:
    """Vervangt content/content.json in een H5P-bestand door de nieuwe JSON."""
    json_str = json.dumps(new_content, ensure_ascii=False, indent=(2 if ensure_pretty else None))
    with tempfile.TemporaryDirectory() as tmpdir:
        src_zip = os.path.join(tmpdir, "src.h5p")
        with open(src_zip, "wb") as f:
            f.write(h5p_bytes)

        extract_dir = os.path.join(tmpdir, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(src_zip, "r") as zin:
            zin.extractall(extract_dir)

        content_dir = os.path.join(extract_dir, "content")
        os.makedirs(content_dir, exist_ok=True)
        with open(os.path.join(content_dir, "content.json"), "w", encoding="utf-8") as f:
            f.write(json_str)

        out_zip_path = os.path.join(tmpdir, "updated.h5p")
        with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, extract_dir).replace("\\", "/")
                    zout.write(abs_path, rel_path)

        with open(out_zip_path, "rb") as f:
            return f.read()
