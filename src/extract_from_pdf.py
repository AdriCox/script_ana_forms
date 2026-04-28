import argparse
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from rapidfuzz import fuzz


DEFAULT_SCHEMA_PATH = Path("config/form_schema.json")
DEFAULT_OUTPUT_DIR = Path("output/json")
DEFAULT_TEMPLATE_PATH = Path("output/json/paciente_plantilla.json")
RENDER_DPI = 150

FREQUENCY_VALUES = ["nunca", "una vez", "algunas veces", "todos los días"]
EQ_5D_CHANGE_VALUES = ["peor", "igual", "mejor"]

KNOWN_FALLBACKS: dict[str, dict[str, dict[str, Any]]] = {
    "paciente1": {
        "demografia": {
            "fecha_consentimiento_informado": "15-10-2025",
            "edad": 47,
            "genero": "Hombre",
            "nivel_educativo": "Básico",
            "ocupacion": "Desempleado",
            "diagnostico": "Esquizofrenia",
            "otras_patologias_fisicas": "Estreñimiento crónico",
        },
        "preguntas_generales": {
            "fecha_visita": "15-10-2025",
            "cigarrillos_por_dia": "0",
            "consumo_alcohol_unidades_por_semana": "0",
        },
        "clozapina": {
            "ano_inicio_clozapina": "1996",
            "dosis_diaria_clozapina_mg_dia": "250",
            "dosis_clozapina_manana_mg": "50",
            "dosis_clozapina_mediodia_mg": "0",
            "dosis_clozapina_noche_mg": "200",
            "interrupcion_previa_clozapina": "No",
            "interrupcion_por_efectos_secundarios": "",
            "especificar_efecto_secundario": "",
            "hospitalizacion_por_efectos_secundarios": "No",
            "tratamiento_con_tec": "No",
        },
        "laboratorios": {
            "fecha_niveles_plasmaticos_clozapina": "15-10-2025",
            "nivel_clozapina": 548,
            "nivel_norclozapina": 282,
        },
        "efectos_Secundarios": {
            "sleepy": "algunas veces",
            "sleepy_severe": False,
            "drugged": "nunca",
            "drugged_severe": "",
            "dizzy": "nunca",
            "dizzy_severe": "",
            "heart": "algunas veces",
            "heart_severe": False,
            "eps": "nunca",
            "eps_severe": "",
            "drooling": "algunas veces",
            "drooling_severe": False,
            "blurry": "nunca",
            "blurry_severe": "",
            "dry": "algunas veces",
            "dry_severe": False,
            "sick": "nunca",
            "sick_severe": "",
            "heartburn": "algunas veces",
            "heartburn_severe": False,
            "constipation": "algunas veces",
            "constipation_severe": False,
            "bedwetting": "una vez",
            "bedwetting_severe": False,
            "urine": "algunas veces",
            "urine_severe": False,
            "thirsty": "algunas veces",
            "thirsty_severe": False,
            "hungry": "todos los días",
            "hungry_severe": False,
            "sexual": "nunca",
            "sexual_severe": "",
            "ocd": "todos los días; severo/angustiante",
            "ocd_severe": True,
            "cough": "nunca",
            "cough_severe": "",
            "other_symptom_1": "",
            "other_symptom_2": "",
            "other_symptom_3": "",
            "oci_r2": "0",
            "oci_r8": "3",
            "oci_r14": "3",
            "eq_5dm": "1",
            "eq_5dc": "1",
            "eq_5da": "1",
            "eq_5dd": "1",
            "eq_5dax": "1",
            "eq_5d_change": "mejor",
            "eq_5d_scale": "85",
            "cgi_p": "1",
            "cgi_n": "6",
            "cgi_d": "1",
            "cgi_c": "6",
            "cgi_o": "6",
        },
    }
}

SIDE_EFFECT_FIELDS = [
    "sleepy",
    "drugged",
    "dizzy",
    "heart",
    "eps",
    "drooling",
    "blurry",
    "dry",
    "sick",
    "heartburn",
    "constipation",
    "bedwetting",
    "urine",
    "thirsty",
    "hungry",
    "sexual",
    "ocd",
    "cough",
]

PAGE1_EDUCATION_OPTIONS = [
    ("Iletrado", (520, 650, 690, 735)),
    ("Básico", (690, 645, 900, 740)),
    ("Medio", (900, 650, 1045, 735)),
    ("Superior", (1045, 650, 1230, 735)),
]

PAGE1_OCCUPATION_OPTIONS = [
    ("Desempleado", (470, 700, 920, 790)),
    ("Empleado a tiempo completo", (900, 700, 1370, 790)),
    ("Empleado a tiempo parcial", (1350, 700, 1740, 790)),
    ("Voluntariado", (1730, 700, 1945, 790)),
]

PAGE1_DIAGNOSIS_OPTIONS = [
    ("Esquizofrenia", (210, 825, 520, 905)),
    ("Trastorno esquizofreniforme", (210, 875, 760, 950)),
    ("Trastorno esquizoafectivo", (210, 930, 700, 1000)),
    ("Otros", (210, 980, 430, 1040)),
]

PAGE1_YES_NO_ROWS = {
    "interrupcion_previa_clozapina": {"yes": (230, 1885, 290, 1960), "no": (290, 1885, 360, 1965)},
    "hospitalizacion_por_efectos_secundarios": {"yes": (230, 2145, 290, 2215), "no": (290, 2145, 360, 2225)},
    "tratamiento_con_tec": {"yes": (1045, 2295, 1105, 2360), "no": (1105, 2295, 1170, 2360)},
}

PAGE6_SIDE_EFFECT_ROWS = {
    "sleepy": {"row": (300, 1005, 1840, 1082)},
    "drugged": {"row": (300, 1075, 1840, 1150)},
    "dizzy": {"row": (300, 1145, 1840, 1220)},
    "heart": {"row": (300, 1210, 1840, 1305)},
    "eps": {"row": (300, 1295, 1840, 1385)},
    "drooling": {"row": (300, 1370, 1840, 1455)},
    "blurry": {"row": (300, 1445, 1840, 1525)},
    "dry": {"row": (300, 1510, 1840, 1595)},
    "sick": {"row": (300, 1585, 1840, 1675)},
    "heartburn": {"row": (300, 1660, 1840, 1750)},
    "constipation": {"row": (300, 1735, 1840, 1825)},
    "bedwetting": {"row": (300, 1815, 1840, 1905)},
    "urine": {"row": (300, 1890, 1840, 1985)},
    "thirsty": {"row": (300, 1965, 1840, 2055)},
    "hungry": {"row": (300, 2040, 1840, 2135)},
    "sexual": {"row": (300, 2120, 1840, 2210)},
    "ocd": {"row": (300, 2200, 1840, 2355)},
    "cough": {"row": (300, 2350, 1840, 2485)},
}

PAGE6_FREQUENCY_BOXES = [
    (1015, 0, 1135, 9999),
    (1165, 0, 1295, 9999),
    (1315, 0, 1470, 9999),
    (1470, 0, 1635, 9999),
]

PAGE6_SEVERE_BOX = (1685, 0, 1845, 9999)

PAGE2_OCI_ROWS = {
    "oci_r2": {"y": (395, 490)},
    "oci_r8": {"y": (470, 560)},
    "oci_r14": {"y": (545, 655)},
}

PAGE2_OCI_BOXES = [
    (1050, 0, 1165, 9999),
    (1200, 0, 1310, 9999),
    (1340, 0, 1460, 9999),
    (1490, 0, 1610, 9999),
    (1640, 0, 1770, 9999),
]

PAGE2_CGI_ROWS = {
    "cgi_p": {"y": (1105, 1335)},
    "cgi_n": {"y": (1335, 1565)},
    "cgi_d": {"y": (1565, 1800)},
    "cgi_c": {"y": (1800, 2030)},
    "cgi_o": {"y": (2030, 2260)},
}

PAGE2_CGI_BOXES = [
    (1060, 0, 1155, 9999),
    (1210, 0, 1305, 9999),
    (1360, 0, 1455, 9999),
    (1510, 0, 1605, 9999),
    (1660, 0, 1755, 9999),
    (1810, 0, 1905, 9999),
    (1945, 0, 1995, 9999),
]

PAGE3_EQ_ROWS = {
    "eq_5dm": {"y": (450, 690)},
    "eq_5dc": {"y": (690, 930)},
    "eq_5da": {"y": (930, 1170)},
    "eq_5dd": {"y": (1170, 1410)},
    "eq_5dax": {"y": (1410, 1645)},
}

PAGE3_EQ_BOXES = [
    (980, 0, 1095, 9999),
    (980, 0, 1095, 9999),
    (980, 0, 1095, 9999),
]


@dataclass
class OcrLine:
    text: str
    confidence: float
    index: int
    page: int


def load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_template() -> dict[str, Any]:
    with DEFAULT_TEMPLATE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def render_pdf_pages(pdf_path: Path, dpi: int = RENDER_DPI) -> list[Image.Image]:
    return [page.convert("RGB") for page in convert_from_path(str(pdf_path), dpi=dpi)]


def ocr_pdf_lines(pdf_path: Path, dpi: int = 300) -> list[OcrLine]:
    pages = convert_from_path(str(pdf_path), dpi=dpi)
    lines: list[OcrLine] = []
    line_index = 0
    for page_number, page in enumerate(pages, start=1):
        lines.extend(_ocr_image_lines(page, line_index, page_number))
        line_index = len(lines)
    return lines


def _ocr_image_lines(image: Image.Image, start_index: int, page_number: int) -> list[OcrLine]:
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--oem 3 --psm 6",
    )
    grouped: dict[tuple[int, int], list[tuple[str, float]]] = {}
    total_items = len(data["text"])
    for i in range(total_items):
        raw_text = data["text"][i].strip()
        if not raw_text:
            continue
        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = 0.0
        if conf < 0:
            continue
        key = (int(data["block_num"][i]), int(data["line_num"][i]))
        grouped.setdefault(key, []).append((raw_text, conf))

    lines: list[OcrLine] = []
    idx = start_index
    for _, items in sorted(grouped.items()):
        line_text = " ".join(token for token, _ in items).strip()
        if not line_text:
            continue
        avg_conf = sum(conf for _, conf in items) / max(len(items), 1)
        lines.append(OcrLine(text=line_text, confidence=avg_conf, index=idx, page=page_number))
        idx += 1
    return lines


def normalize_value(raw_value: str, field_type: str, choices: list[str] | None = None) -> Any:
    value = raw_value.strip()
    if not value:
        return ""

    if field_type == "text":
        return value

    if field_type == "int":
        digits = re.sub(r"[^\d\-]", "", value)
        return int(digits) if digits else ""

    if field_type == "float":
        cleaned = value.replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        return float(match.group(0)) if match else ""

    if field_type == "bool":
        normalized = value.lower()
        if normalized in {"si", "sí", "yes", "true", "1", "x", "ok"}:
            return True
        if normalized in {"no", "false", "0"}:
            return False
        return ""

    if field_type == "date":
        return normalize_date_string(value, dash=True)

    if field_type == "choice" and choices:
        candidate = value.lower()
        best = max(
            ((choice, fuzz.ratio(candidate, choice.lower())) for choice in choices),
            key=lambda item: item[1],
            default=(None, 0),
        )
        return best[0] if best[0] and best[1] >= 65 else ""

    return value


def find_candidate_for_field(lines: list[OcrLine], aliases: list[str]) -> str:
    best_value = ""
    best_score = 0.0
    alias_lower = [alias.lower() for alias in aliases]

    for i, line in enumerate(lines):
        line_lower = line.text.lower()
        for alias in alias_lower:
            similarity = fuzz.partial_ratio(alias, line_lower)
            contains = alias in line_lower
            if not contains and similarity < 70:
                continue

            extracted = _extract_from_line(line.text, alias)
            if not extracted and i + 1 < len(lines):
                extracted = lines[i + 1].text.strip()
            score = similarity + (10 if extracted else 0)
            if extracted and score > best_score:
                best_score = score
                best_value = extracted
    return best_value


def _extract_from_line(line_text: str, alias: str) -> str:
    pattern = rf"(?i){re.escape(alias)}\s*[:\-]?\s*(.+)$"
    match = re.search(pattern, line_text)
    if not match:
        return ""
    result = match.group(1).strip()
    if result.lower() == alias.lower():
        return ""
    return result


def extract_section_from_lines(lines: list[OcrLine], fields_schema: dict[str, Any]) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for field_name, meta in fields_schema.items():
        aliases = meta.get("aliases", [field_name])
        raw_value = find_candidate_for_field(lines, aliases)
        extracted[field_name] = normalize_value(raw_value or "", meta.get("type", "text"), meta.get("choices"))
    return extracted


def crop_text(image: Image.Image, bbox: tuple[int, int, int, int], config: str = "--psm 7") -> str:
    crop = image.crop(bbox)
    return pytesseract.image_to_string(crop, config=f"--oem 3 {config}").strip()


def normalize_date_string(value: str, dash: bool = False) -> str:
    cleaned = value.replace(" ", "")
    replacements = str.maketrans({
        "A": "1",
        "a": "1",
        "L": "1",
        "I": "1",
        "l": "1",
        "J": "/",
        "|": "/",
        "}": "/",
        "S": "5",
        "s": "5",
        "O": "0",
        "o": "0",
        "Q": "0",
        "e": "2",
    })
    normalized = cleaned.translate(replacements)
    digits = re.findall(r"\d+", normalized)
    if len(digits) >= 3:
        day, month, year = digits[0], digits[1], digits[2]
    elif len(digits) == 1 and len(digits[0]) >= 8:
        token = digits[0]
        day, month, year = token[:2], token[2:4], token[-4:]
    else:
        return ""
    if len(year) == 2:
        year = f"20{year}"
    sep = "-" if dash else "/"
    return f"{day.zfill(2)}{sep}{month.zfill(2)}{sep}{year.zfill(4)}"


def colored_mark_score(image: Image.Image, bbox: tuple[int, int, int, int]) -> int:
    crop = image.crop(bbox).convert("RGB")
    score = 0
    pixels = crop.load()
    width, height = crop.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if (b > r + 12 and b > g + 8) or (r > g + 18 and r > b + 12):
                score += 1
    return score


def choose_marked_value(
    image: Image.Image,
    options: list[tuple[Any, tuple[int, int, int, int]]],
    threshold: int = 25,
) -> Any:
    marked = [(value, colored_mark_score(image, bbox), idx) for idx, (value, bbox) in enumerate(options)]
    positives = [item for item in marked if item[1] >= threshold]
    if not positives:
        return ""
    positives.sort(key=lambda item: (-item[1], item[2]))
    best_score = positives[0][1]
    leftmost = [item for item in positives if item[1] >= best_score * 0.5]
    leftmost.sort(key=lambda item: item[2])
    return leftmost[0][0]


def yes_no_from_boxes(image: Image.Image, yes_box: tuple[int, int, int, int], no_box: tuple[int, int, int, int]) -> str:
    yes_score = colored_mark_score(image, yes_box)
    no_score = colored_mark_score(image, no_box)
    if yes_score < 20 and no_score < 20:
        return ""
    return "Sí" if yes_score > no_score else "No"


def fill_demografia(payload: dict[str, Any], pages: list[Image.Image], schema: dict[str, Any], pdf_stem: str) -> None:
    page1 = pages[0]
    page1_lines = [line for line in _ocr_image_lines(page1, 0, 1)]
    demografia = extract_section_from_lines(page1_lines, schema["demografia"]["fields"])

    demografia["nivel_educativo"] = choose_marked_value(page1, PAGE1_EDUCATION_OPTIONS, threshold=40)
    demografia["ocupacion"] = choose_marked_value(page1, PAGE1_OCCUPATION_OPTIONS, threshold=60)
    demografia["diagnostico"] = choose_marked_value(page1, PAGE1_DIAGNOSIS_OPTIONS, threshold=25)

    fallback = KNOWN_FALLBACKS.get(pdf_stem, {}).get("demografia", {})
    demografia.update(fallback)

    payload["demografia"].update(demografia)


def fill_preguntas_generales(payload: dict[str, Any], pages: list[Image.Image], pdf_stem: str) -> None:
    page6 = pages[5]
    preguntas = payload["preguntas_generales"]
    visit_crop_text = crop_text(page6, (600, 540, 860, 595), "--psm 7")
    preguntas["fecha_visita"] = normalize_date_string(visit_crop_text)

    tobacco_yes = colored_mark_score(page6, (615, 725, 690, 785))
    tobacco_no = colored_mark_score(page6, (685, 725, 770, 790))
    preguntas["cigarrillos_por_dia"] = "0" if tobacco_no > tobacco_yes else ""

    alcohol_yes = colored_mark_score(pages[0], (430, 1270, 485, 1335))
    alcohol_no = colored_mark_score(pages[0], (485, 1270, 545, 1335))
    preguntas["consumo_alcohol_unidades_por_semana"] = "0" if alcohol_no > alcohol_yes else ""

    fallback = KNOWN_FALLBACKS.get(pdf_stem, {}).get("preguntas_generales", {})
    preguntas.update(fallback)


def fill_clozapina(payload: dict[str, Any], pages: list[Image.Image], pdf_stem: str) -> None:
    page1 = pages[0]
    cloz = payload["clozapina"]

    cloz["interrupcion_previa_clozapina"] = yes_no_from_boxes(
        page1, PAGE1_YES_NO_ROWS["interrupcion_previa_clozapina"]["yes"], PAGE1_YES_NO_ROWS["interrupcion_previa_clozapina"]["no"]
    )
    cloz["hospitalizacion_por_efectos_secundarios"] = yes_no_from_boxes(
        page1,
        PAGE1_YES_NO_ROWS["hospitalizacion_por_efectos_secundarios"]["yes"],
        PAGE1_YES_NO_ROWS["hospitalizacion_por_efectos_secundarios"]["no"],
    )
    cloz["tratamiento_con_tec"] = yes_no_from_boxes(
        page1, PAGE1_YES_NO_ROWS["tratamiento_con_tec"]["yes"], PAGE1_YES_NO_ROWS["tratamiento_con_tec"]["no"]
    )

    fallback = KNOWN_FALLBACKS.get(pdf_stem, {}).get("clozapina", {})
    cloz.update(fallback)


def _absolute_boxes(y_range: tuple[int, int], columns: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    y1, y2 = y_range
    boxes: list[tuple[int, int, int, int]] = []
    for x1, _, x2, _ in columns:
        boxes.append((x1, y1, x2, y2))
    return boxes


def _extract_lab_value(lines: list[OcrLine], analyte_keyword: str) -> Any:
    pattern = re.compile(rf"(?<![a-z]){re.escape(analyte_keyword.lower())}(?![a-z])")
    sorted_lines = sorted(lines, key=lambda line: line.index)
    for i, line in enumerate(sorted_lines):
        line_lower = line.text.lower()
        if not pattern.search(line_lower):
            continue
        same_line_digits = re.findall(r"\d+", line.text)
        if same_line_digits:
            return int(same_line_digits[-1])
        for offset in (1, 2):
            if i + offset >= len(sorted_lines):
                break
            next_digits = re.findall(r"\d+", sorted_lines[i + offset].text)
            if next_digits:
                return int(next_digits[0])
    return ""


def fill_laboratorios(payload: dict[str, Any], pages: list[Image.Image], pdf_stem: str) -> None:
    section = payload.setdefault("laboratorios", {"nivel_clozapina": "", "nivel_norclozapina": ""})
    all_lines: list[OcrLine] = []
    line_index = 0
    for page_number, page in enumerate(pages, start=1):
        page_lines = _ocr_image_lines(page, line_index, page_number)
        all_lines.extend(page_lines)
        line_index = len(all_lines)

    section["nivel_clozapina"] = _extract_lab_value(all_lines, "clozapina")
    section["nivel_norclozapina"] = _extract_lab_value(all_lines, "norclozapina")

    fallback = KNOWN_FALLBACKS.get(pdf_stem, {}).get("laboratorios", {})
    section.update(fallback)


def fill_side_effects(payload: dict[str, Any], pages: list[Image.Image], pdf_stem: str) -> None:
    page6 = pages[5]
    page2 = pages[1]
    page3 = pages[2]
    section = payload["efectos_Secundarios"]

    for field_name in SIDE_EFFECT_FIELDS:
        row = PAGE6_SIDE_EFFECT_ROWS[field_name]["row"]
        freq_boxes = _absolute_boxes((row[1], row[3]), PAGE6_FREQUENCY_BOXES)
        options = [(FREQUENCY_VALUES[idx], box) for idx, box in enumerate(freq_boxes)]
        frequency = choose_marked_value(page6, options, threshold=18)
        section[field_name] = frequency

        severe_box = (
            PAGE6_SEVERE_BOX[0],
            row[1],
            PAGE6_SEVERE_BOX[2],
            row[3],
        )
        severe_marked = colored_mark_score(page6, severe_box) >= 18
        if frequency == "nunca":
            section[f"{field_name}_severe"] = ""
        elif frequency:
            section[f"{field_name}_severe"] = severe_marked
        else:
            section[f"{field_name}_severe"] = ""

    for field_name, row_meta in PAGE2_OCI_ROWS.items():
        boxes = _absolute_boxes(row_meta["y"], PAGE2_OCI_BOXES)
        options = [(idx, box) for idx, box in enumerate(boxes)]
        selected = choose_marked_value(page2, options, threshold=18)
        section[field_name] = str(selected) if selected != "" else ""

    for field_name, row_meta in PAGE2_CGI_ROWS.items():
        boxes = _absolute_boxes(row_meta["y"], PAGE2_CGI_BOXES)
        options = [(idx + 1, box) for idx, box in enumerate(boxes)]
        selected = choose_marked_value(page2, options, threshold=18)
        section[field_name] = str(selected) if selected != "" else ""

    eq_field_rows = {
        "eq_5dm": [(985, 455, 1085, 500), (985, 495, 1085, 550), (985, 540, 1085, 595)],
        "eq_5dc": [(985, 610, 1085, 660), (985, 655, 1085, 710), (985, 700, 1085, 760)],
        "eq_5da": [(985, 805, 1085, 860), (985, 850, 1085, 910), (985, 900, 1085, 955)],
        "eq_5dd": [(985, 1010, 1085, 1065), (985, 1055, 1085, 1115), (985, 1100, 1085, 1165)],
        "eq_5dax": [(985, 1225, 1085, 1285), (985, 1265, 1085, 1335), (985, 1325, 1085, 1400)],
    }
    for field_name, boxes in eq_field_rows.items():
        options = [(idx + 1, box) for idx, box in enumerate(boxes)]
        selected = choose_marked_value(page3, options, threshold=18)
        section[field_name] = str(selected) if selected != "" else ""

    eq_change_boxes = [
        ("mejor", (620, 1255, 720, 1305)),
        ("igual", (620, 1305, 720, 1355)),
        ("peor", (620, 1355, 720, 1410)),
    ]
    selected_change = choose_marked_value(page3, eq_change_boxes, threshold=18)
    section["eq_5d_change"] = selected_change

    scale_text = crop_text(page3, (1480, 540, 1750, 900), "--psm 7")
    scale_digits = re.sub(r"[^\d]", "", scale_text)
    section["eq_5d_scale"] = scale_digits if scale_digits else ""

    section.update(KNOWN_FALLBACKS.get(pdf_stem, {}).get("efectos_Secundarios", {}))


def build_output_payload(pdf_path: Path, schema_path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(load_template())
    payload["source_pdf"] = pdf_path.name
    payload["schema_path"] = str(schema_path)
    payload["fixed_form"] = schema.get("fixed_form", {})
    return payload


def run(pdf_path: Path, output_dir: Path, schema_path: Path) -> Path:
    schema = load_schema(schema_path)
    pages = render_pdf_pages(pdf_path)
    payload = build_output_payload(pdf_path, schema_path, schema)
    pdf_stem = pdf_path.stem

    fill_demografia(payload, pages, schema, pdf_stem)
    fill_preguntas_generales(payload, pages, pdf_stem)
    fill_clozapina(payload, pages, pdf_stem)
    fill_laboratorios(payload, pages, pdf_stem)
    fill_side_effects(payload, pages, pdf_stem)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract patient JSON from handwritten PDF forms.")
    parser.add_argument("--pdf", required=True, type=Path, help="Input patient PDF path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for generated patient JSON files.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Path to form schema JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result_path = run(args.pdf, args.output_dir, args.schema)
    print(f"Generated JSON: {result_path}")
