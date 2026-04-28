import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_SCHEMA_PATH = Path("config/form_schema.json")
DEFAULT_SCREENSHOT_DIR = Path("output/screenshots")
DEFAULT_LOG_PATH = Path("output/ingestion_log.json")

PROD_SURVEY_URL = "https://redcap.camide.cam.ac.uk/surveys/?s=7FC37HE4WX3L4LLK"

GENDER_OPTIONS = {
    "mujer": 1,
    "female": 1,
    "hombre": 2,
    "male": 2,
    "otro": 3,
    "other": 3,
}

EDUCATION_LEVEL_OPTIONS = {
    "iletrado": 1,
    "illiterate": 1,
    "basico": 2,
    "básico": 2,
    "essential": 2,
    "medio": 3,
    "half": 3,
    "superior": 4,
}

OCCUPATION_OPTIONS = {
    "desempleado": 1,
    "unemployed": 1,
    "empleado a tiempo completo": 2,
    "full-time employee": 2,
    "empleado a tiempo parcial": 3,
    "part-time employee": 3,
    "voluntariado": 4,
    "volunteering": 4,
}

DIAGNOSIS_OPTIONS = {
    "esquizofrenia": 1,
    "schizophrenia": 1,
    "trastorno esquizofreniforme": 2,
    "schizophreniform disorder": 2,
    "trastorno esquizoafectivo": 3,
    "schizoaffective disorder": 3,
    "otros": 4,
    "others": 4,
}

HORIZONTAL_YES_NO_OPTIONS = {
    "si": 1,
    "sí": 1,
    "yes": 1,
    "no": 2,
}

ANTIPSYCHOTIC_2_OPTIONS = {
    "olanzapine": 1,
    "olanzapina": 1,
    "quetiapine": 2,
    "quetiapina": 2,
    "risperidone": 3,
    "risperidona": 3,
    "paliperidone": 4,
    "paliperidona": 4,
    "aripiprazole": 5,
    "aripiprazol": 5,
    "brexpiprazole": 6,
    "brexpiprazol": 6,
    "amisulpride": 7,
    "amisulprida": 7,
    "cariprazine": 8,
    "cariprazina": 8,
    "lurasidone": 9,
    "lurasidona": 9,
    "asenepine": 10,
    "asenapina": 10,
    "haloperidol": 11,
    "another second generation": 12,
    "otro de segunda generacion": 12,
    "otro de segunda generación": 12,
}

ANTIDEPRESSANT_OPTIONS = {
    "citalopram": 1,
    "citaloprama": 1,
    "sertralina": 2,
    "sertraline": 2,
    "fluoxetina": 3,
    "fluoxetine": 3,
    "escitalopram": 4,
    "escitaloprama": 4,
    "paroxetine": 5,
    "paroxetina": 5,
    "fluvoxamina": 6,
    "fluvoxamine": 6,
    "venlafaxina": 7,
    "venlafaxine": 7,
    "duloxetina": 8,
    "duloxetine": 8,
    "clomipramina": 9,
    "clomipramine": 9,
    "amitriptilina": 10,
    "amitriptyline": 10,
    "imipramina": 11,
    "imipramine": 11,
    "mirtazapina": 12,
    "mirtazapine": 12,
    "bupropion": 13,
    "trazodona": 14,
    "trazodone": 14,
    "reboxetina": 15,
    "reboxetine": 15,
    "others": 16,
    "otros": 16,
}

MOOD_STABILIZER_OPTIONS = {
    "lithium": 1,
    "litio": 1,
    "valproates": 2,
    "valproato": 2,
    "valproatos": 2,
    "lamotrigine": 3,
    "lamotrigina": 3,
    "topiramate": 4,
    "topiramato": 4,
    "others": 5,
    "otros": 5,
}

SIDE_EFFECT_FREQUENCY_OPTIONS = {
    "never": 1,
    "nunca": 1,
    "once": 2,
    "una vez": 2,
    "sometimes": 3,
    "algunas veces": 3,
    "every day": 4,
    "todos los dias": 4,
    "todos los días": 4,
    "todos los días; severo/angustiante": 4,
    "todos los dias; severo/angustiante": 4,
}

EQ_5D_CHANGE_OPTIONS = {
    "peor": 1,
    "worse": 1,
    "igual": 2,
    "same": 2,
    "mejor": 3,
    "better": 3,
}

def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def patient_id_from_json_path(patient_json_path: Path) -> int | str:
    stem = patient_json_path.stem
    match = re.search(r"\d+", stem)
    if match:
        return int(match.group(0))
    return stem


def update_ingestion_log(log_path: Path, patient: int | str, record_id: int, link: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
                if isinstance(loaded, list):
                    entries = loaded
        except json.JSONDecodeError:
            entries = []

    submitted_at = _utc_now_iso()
    new_entry = {"patient": patient, "record_id": record_id, "link": link, "submitted_at": submitted_at}

    replaced = False
    for index, entry in enumerate(entries):
        if entry.get("patient") == patient:
            entries[index] = new_entry
            replaced = True
            break
    if not replaced:
        entries.append(new_entry)

    with log_path.open("w", encoding="utf-8") as file:
        json.dump(entries, file, ensure_ascii=False, indent=2)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wait_for_user_to_start_flow() -> None:
    input("Resuelve el CAPTCHA y pulsa Enter en esta terminal para empezar el flujo...")


def wait_for_user_after_begin() -> None:
    input("Cuando el formulario esté cargado (CAPTCHA resuelto si reaparece), pulsa Enter para continuar...")


def press_tab(page, times: int) -> None:
    for _ in range(times):
        page.keyboard.press("Tab")
        page.wait_for_timeout(40)


def press_key(page, key: str) -> None:
    page.keyboard.press(key)


def type_text(page, value: Any) -> None:
    page.keyboard.type(str(value), delay=18)


def sleep_ms(page, ms: int) -> None:
    page.wait_for_timeout(ms)


def press_enter(page) -> None:
    page.keyboard.press("Enter")


def _normalize_option_label(value: Any) -> str:
    return str(value).strip().lower()


def mapped_point_option(field_name: str, value: Any, options: dict[str, int]) -> int:
    normalized_value = _normalize_option_label(value)
    if normalized_value not in options:
        raise ValueError(f"Unsupported value for {field_name}: {value}")
    return options[normalized_value]


def mapped_optional_point_option(field_name: str, value: Any, options: dict[str, int]) -> int | None:
    normalized_value = _normalize_option_label(value)
    if not normalized_value:
        return None
    if normalized_value not in options:
        raise ValueError(f"Unsupported value for {field_name}: {value}")
    return options[normalized_value]


def mapped_optional_dropdown_steps(field_name: str, value: Any, options: dict[str, int]) -> int:
    normalized_value = _normalize_option_label(value)
    if not normalized_value:
        return 0
    if normalized_value not in options:
        raise ValueError(f"Unsupported value for {field_name}: {value}")
    return options[normalized_value]


def mapped_optional_int_option(field_name: str, value: Any, minimum: int, maximum: int, offset: int = 0) -> int | None:
    normalized_value = _normalize_option_label(value)
    if not normalized_value:
        return None
    try:
        numeric_value = int(normalized_value)
    except ValueError as error:
        raise ValueError(f"Unsupported numeric value for {field_name}: {value}") from error
    if not minimum <= numeric_value <= maximum:
        raise ValueError(f"Unsupported numeric value for {field_name}: {value}")
    return numeric_value + offset


def format_lab_level_divided(raw_value: Any) -> str:
    if raw_value in ("", None):
        return ""
    try:
        numeric = float(raw_value)
    except (TypeError, ValueError):
        return ""
    divided = numeric / 10000.0
    truncated = int(divided * 100) / 100.0
    clamped = max(0.01, min(1.50, truncated))
    return f"{clamped:.2f}".replace(".", ",")


def mapped_optional_bool_value(field_name: str, value: Any) -> bool | None:
    if value in ("", None):
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"Unsupported boolean value for {field_name}: {value}")


def point_section(
    page,
    option: int,
    tabs: int = 2,
    orientation: str = "vertical",
) -> None:
    if option < 1:
        raise ValueError("option must be >= 1")
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("orientation must be 'vertical' or 'horizontal'")

    press_tab(page, tabs)

    forward_key = "ArrowDown" if orientation == "vertical" else "ArrowRight"
    backward_key = "ArrowUp" if orientation == "vertical" else "ArrowLeft"

    if option == 1:
        press_key(page, forward_key)
        press_key(page, backward_key)
        return

    for _ in range(option - 1):
        press_key(page, forward_key)


def optional_point_section(
    page,
    option: int | None,
    tabs: int = 2,
    orientation: str = "vertical",
) -> None:
    if option is None:
        press_tab(page, tabs)
        return
    point_section(page, option=option, tabs=tabs, orientation=orientation)


def dropdown_section(page, down_steps: int, tabs: int = 2) -> None:
    if down_steps < 0:
        raise ValueError("down_steps must be >= 0")
    press_tab(page, tabs)
    for _ in range(down_steps):
        press_key(page, "ArrowDown")


def severity_filler(page, severe: bool | None) -> None:
    if severe is None:
        return
    press_tab(page, 2)
    if severe:
        press_key(page, "ArrowRight")
        press_key(page, "ArrowLeft")
        return
    press_key(page, "ArrowRight")


def extract_patient_study_id(page) -> int:
    note_selectors = [
        "#patient_id_note_1-tr",
        'tr[id*="patient_id_note"]',
        "text=/This patient'?s study ID is:/i",
    ]
    note_text = ""

    for selector in note_selectors:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        note_text = locator.first.inner_text().strip()
        if note_text:
            break

    if not note_text:
        note_text = page.locator("body").inner_text()

    match = re.search(r"This patient'?s study ID is:\s*(\d+)", note_text, re.IGNORECASE)
    if not match:
        raise ValueError("Could not extract patient study ID from confirmation page")

    return int(match.group(1))

def enter_survey_if_needed(page) -> bool:
    begin_candidates = [
        'button:has-text("Begin survey")',
        'button:has-text("Comenzar")',
        'input[type="submit"][value*="Begin survey" i]',
        'input[type="submit"][value*="Begin Survey" i]',
        'input[type="submit"][value*="Comenzar" i]',
        'a:has-text("Begin survey")',
    ]
    for selector in begin_candidates:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        try:
            locator.first.focus()
            press_enter(page)
        except Exception:
            locator.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(700)
        return True
    return False


def execute_partial_flow(page, patient_data: dict[str, Any]) -> tuple[list[str], int]:
    fixed_form = patient_data.get("fixed_form", {})
    demografia = patient_data.get("demografia", {})
    preguntas_generales = patient_data.get("preguntas_generales", {})
    clozapina = patient_data.get("clozapina", {})
    efectos_secundarios = patient_data.get("efectos_Secundarios", {})
    executed_steps: list[str] = []
    genero_option = mapped_point_option("demografia.genero", demografia.get("genero", ""), GENDER_OPTIONS)
    nivel_educativo_option = mapped_point_option(
        "demografia.nivel_educativo",
        demografia.get("nivel_educativo", ""),
        EDUCATION_LEVEL_OPTIONS,
    )
    ocupacion_option = mapped_point_option("demografia.ocupacion", demografia.get("ocupacion", ""), OCCUPATION_OPTIONS)
    diagnostico_option = mapped_point_option(
        "demografia.diagnostico",
        demografia.get("diagnostico", ""),
        DIAGNOSIS_OPTIONS,
    )
    interrupcion_previa_option = mapped_optional_point_option(
        "clozapina.interrupcion_previa_clozapina",
        clozapina.get("interrupcion_previa_clozapina", ""),
        HORIZONTAL_YES_NO_OPTIONS,
    )
    interrupcion_efectos_option = mapped_optional_point_option(
        "clozapina.interrupcion_por_efectos_secundarios",
        clozapina.get("interrupcion_por_efectos_secundarios", ""),
        HORIZONTAL_YES_NO_OPTIONS,
    )
    hospitalizacion_efectos_option = mapped_optional_point_option(
        "clozapina.hospitalizacion_por_efectos_secundarios",
        clozapina.get("hospitalizacion_por_efectos_secundarios", ""),
        HORIZONTAL_YES_NO_OPTIONS,
    )
    tratamiento_tec_option = mapped_optional_point_option(
        "clozapina.tratamiento_con_tec",
        clozapina.get("tratamiento_con_tec", ""),
        HORIZONTAL_YES_NO_OPTIONS,
    )
    antipsicotico_2_steps = mapped_optional_dropdown_steps(
        "clozapina.antipsicotico_2",
        clozapina.get("antipsicotico_2", ""),
        ANTIPSYCHOTIC_2_OPTIONS,
    )
    antidepresivo_1_steps = mapped_optional_dropdown_steps(
        "clozapina.antidepresivo_1",
        clozapina.get("antidepresivo_1", ""),
        ANTIDEPRESSANT_OPTIONS,
    )
    antidepresivo_2_steps = mapped_optional_dropdown_steps(
        "clozapina.antidepresivo_2",
        clozapina.get("antidepresivo_2", ""),
        ANTIDEPRESSANT_OPTIONS,
    )
    estabilizador_animo_1_option = mapped_optional_point_option(
        "clozapina.estabilizador_animo_1",
        clozapina.get("estabilizador_animo_1", ""),
        MOOD_STABILIZER_OPTIONS,
    )
    estabilizador_animo_2_option = mapped_optional_point_option(
        "clozapina.estabilizador_animo_2",
        clozapina.get("estabilizador_animo_2", ""),
        MOOD_STABILIZER_OPTIONS,
    )
    side_effect_fields = [
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
    side_effect_options = {
        field_name: mapped_optional_point_option(
            f"efectos_Secundarios.{field_name}",
            efectos_secundarios.get(field_name, ""),
            SIDE_EFFECT_FREQUENCY_OPTIONS,
        )
        for field_name in side_effect_fields
    }
    side_effect_severities = {
        field_name: mapped_optional_bool_value(
            f"efectos_Secundarios.{field_name}_severe",
            efectos_secundarios.get(f"{field_name}_severe"),
        )
        for field_name in side_effect_fields
    }
    oci_eq_fields = ["oci_r2", "oci_r8", "oci_r14", "eq_5dm", "eq_5dc", "eq_5da", "eq_5dd", "eq_5dax", "eq_5d_change"]
    oci_eq_options = {
        "oci_r2": mapped_optional_int_option("efectos_Secundarios.oci_r2", efectos_secundarios.get("oci_r2", ""), 0, 4, offset=1),
        "oci_r8": mapped_optional_int_option("efectos_Secundarios.oci_r8", efectos_secundarios.get("oci_r8", ""), 0, 4, offset=1),
        "oci_r14": mapped_optional_int_option("efectos_Secundarios.oci_r14", efectos_secundarios.get("oci_r14", ""), 0, 4, offset=1),
        "eq_5dm": mapped_optional_int_option("efectos_Secundarios.eq_5dm", efectos_secundarios.get("eq_5dm", ""), 1, 3),
        "eq_5dc": mapped_optional_int_option("efectos_Secundarios.eq_5dc", efectos_secundarios.get("eq_5dc", ""), 1, 3),
        "eq_5da": mapped_optional_int_option("efectos_Secundarios.eq_5da", efectos_secundarios.get("eq_5da", ""), 1, 3),
        "eq_5dd": mapped_optional_int_option("efectos_Secundarios.eq_5dd", efectos_secundarios.get("eq_5dd", ""), 1, 3),
        "eq_5dax": mapped_optional_int_option("efectos_Secundarios.eq_5dax", efectos_secundarios.get("eq_5dax", ""), 1, 3),
        "eq_5d_change": mapped_optional_point_option(
            "efectos_Secundarios.eq_5d_change",
            efectos_secundarios.get("eq_5d_change", ""),
            EQ_5D_CHANGE_OPTIONS,
        ),
    }
    cgi_fields = ["cgi_p", "cgi_n", "cgi_d", "cgi_c", "cgi_o"]
    cgi_options = {
        field_name: mapped_optional_int_option(
            f"efectos_Secundarios.{field_name}",
            efectos_secundarios.get(field_name, ""),
            1,
            7,
        )
        for field_name in cgi_fields
    }

    press_tab(page, 4)
    executed_steps.append("tab_x4")
    type_text(page, fixed_form.get("email", ""))
    executed_steps.append("type_email")
    sleep_ms(page, 500)

    press_tab(page, 1)
    press_key(page, "ArrowDown")
    executed_steps.append("hospital_arrow_down")

    press_tab(page, 2)
    sleep_ms(page, 200)
    press_key(page, "ArrowDown")
    press_enter(page)
    executed_steps.append("hospital_espanol_arrow_down_enter")
    sleep_ms(page, 500)

    point_section(page, option=1, tabs=1)
    executed_steps.append("criterio_1_down_up")
    sleep_ms(page, 300)

    point_section(page, option=1)
    executed_steps.append("criterio_2_down_up")
    sleep_ms(page, 300)

    point_section(page, option=2)
    executed_steps.append("criterio_3_down")
    sleep_ms(page, 300)

    point_section(page, option=2)
    executed_steps.append("criterio_4_down")
    sleep_ms(page, 300)

    point_section(page, option=2)
    executed_steps.append("criterio_5_down")
    sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, demografia.get("fecha_consentimiento_informado", ""))
    executed_steps.append("type_fecha_consentimiento")

    press_tab(page, 3)
    type_text(page, demografia.get("edad", ""))
    executed_steps.append("type_edad")

    point_section(page, option=genero_option, tabs=1)
    executed_steps.append(f"select_genero_{genero_option}")
    sleep_ms(page, 300)

    point_section(page, option=nivel_educativo_option)
    executed_steps.append(f"select_nivel_educativo_{nivel_educativo_option}")
    sleep_ms(page, 300)

    point_section(page, option=ocupacion_option)
    executed_steps.append(f"select_ocupacion_{ocupacion_option}")
    sleep_ms(page, 300)

    point_section(page, option=diagnostico_option)
    executed_steps.append(f"select_diagnostico_{diagnostico_option}")
    sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, demografia.get("otras_patologias_fisicas", ""))
    executed_steps.append("type_otras_patologias_fisicas")
    sleep_ms(page, 300)

    press_tab(page, 1)
    press_enter(page)
    executed_steps.append("submit_demografia_page")

    page.wait_for_load_state("domcontentloaded")
    sleep_ms(page, 1000)
    record_id = extract_patient_study_id(page)
    executed_steps.append(f"capture_record_id_{record_id}")

    press_tab(page, 4)
    type_text(page, preguntas_generales.get("fecha_visita", ""))
    executed_steps.append("type_fecha_visita")
    sleep_ms(page, 300)

    press_tab(page, 3)
    type_text(page, preguntas_generales.get("cigarrillos_por_dia", ""))
    executed_steps.append("type_cigarrillos_por_dia")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, preguntas_generales.get("consumo_alcohol_unidades_por_semana", ""))
    executed_steps.append("type_consumo_alcohol_unidades_por_semana")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("ano_inicio_clozapina", ""))
    executed_steps.append("type_ano_inicio_clozapina")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_diaria_clozapina_mg_dia", ""))
    executed_steps.append("type_dosis_diaria_clozapina_mg_dia")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_clozapina_manana_mg", ""))
    executed_steps.append("type_dosis_clozapina_manana_mg")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_clozapina_mediodia_mg", ""))
    executed_steps.append("type_dosis_clozapina_mediodia_mg")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_clozapina_noche_mg", ""))
    executed_steps.append("type_dosis_clozapina_noche_mg")
    sleep_ms(page, 300)

    laboratorios = patient_data.get("laboratorios", {})

    press_tab(page, 1)
    type_text(page, laboratorios.get("fecha_niveles_plasmaticos_clozapina", ""))
    executed_steps.append("type_fecha_niveles_plasmaticos_clozapina")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_diaria_clozapina_mg_dia", ""))
    executed_steps.append("type_dosis_diaria_clozapina_mg_dia_duplicada")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, format_lab_level_divided(laboratorios.get("nivel_clozapina", "")))
    executed_steps.append("type_nivel_clozapina_dividido")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, format_lab_level_divided(laboratorios.get("nivel_norclozapina", "")))
    executed_steps.append("type_nivel_norclozapina_dividido")
    sleep_ms(page, 300)

    optional_point_section(page, option=interrupcion_previa_option, tabs=1, orientation="horizontal")
    executed_steps.append("select_interrupcion_previa_clozapina")
    sleep_ms(page, 300)

    optional_point_section(page, option=interrupcion_efectos_option, tabs=2, orientation="horizontal")
    executed_steps.append("select_interrupcion_por_efectos_secundarios")
    sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, clozapina.get("especificar_efecto_secundario", ""))
    executed_steps.append("type_especificar_efecto_secundario")
    sleep_ms(page, 300)

    optional_point_section(page, option=hospitalizacion_efectos_option, tabs=1, orientation="horizontal")
    executed_steps.append("select_hospitalizacion_por_efectos_secundarios")
    sleep_ms(page, 300)

    optional_point_section(page, option=tratamiento_tec_option, tabs=2, orientation="horizontal")
    executed_steps.append("select_tratamiento_con_tec")
    sleep_ms(page, 300)

    dropdown_section(page, down_steps=antipsicotico_2_steps, tabs=2)
    executed_steps.append(f"select_antipsicotico_2_{antipsicotico_2_steps}")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_antipsicotico_2", ""))
    executed_steps.append("type_dosis_antipsicotico_2")
    sleep_ms(page, 300)

    dropdown_section(page, down_steps=antidepresivo_1_steps, tabs=1)
    executed_steps.append(f"select_antidepresivo_1_{antidepresivo_1_steps}")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_antidepresivo_1", ""))
    executed_steps.append("type_dosis_antidepresivo_1")
    sleep_ms(page, 300)

    dropdown_section(page, down_steps=antidepresivo_2_steps, tabs=1)
    executed_steps.append(f"select_antidepresivo_2_{antidepresivo_2_steps}")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("dosis_antidepresivo_2", ""))
    executed_steps.append("type_dosis_antidepresivo_2")
    sleep_ms(page, 300)

    optional_point_section(page, option=estabilizador_animo_1_option, tabs=1, orientation="horizontal")
    executed_steps.append("select_estabilizador_animo_1")
    sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, clozapina.get("dosis_estabilizador_animo_1", ""))
    executed_steps.append("type_dosis_estabilizador_animo_1")
    sleep_ms(page, 300)

    optional_point_section(page, option=estabilizador_animo_2_option, tabs=1, orientation="horizontal")
    executed_steps.append("select_estabilizador_animo_2")
    sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, clozapina.get("dosis_estabilizador_animo_2", ""))
    executed_steps.append("type_dosis_estabilizador_animo_2")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_1", ""))
    executed_steps.append("type_otra_medicacion_1")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_2", ""))
    executed_steps.append("type_otra_medicacion_2")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_3", ""))
    executed_steps.append("type_otra_medicacion_3")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_4", ""))
    executed_steps.append("type_otra_medicacion_4")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_5", ""))
    executed_steps.append("type_otra_medicacion_5")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, clozapina.get("otra_medicacion_6", ""))
    executed_steps.append("type_otra_medicacion_6")
    sleep_ms(page, 300)

    for index, field_name in enumerate(side_effect_fields):
        optional_point_section(
            page,
            option=side_effect_options[field_name],
            tabs=1 if index == 0 else 2,
            orientation="horizontal",
        )
        executed_steps.append(f"select_{field_name}")
        sleep_ms(page, 300)
        severity_filler(page, side_effect_severities[field_name])
        executed_steps.append(f"select_{field_name}_severe")
        sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, efectos_secundarios.get("other_symptom_1", ""))
    executed_steps.append("type_other_symptom_1")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, efectos_secundarios.get("other_symptom_2", ""))
    executed_steps.append("type_other_symptom_2")
    sleep_ms(page, 300)

    press_tab(page, 1)
    type_text(page, efectos_secundarios.get("other_symptom_3", ""))
    executed_steps.append("type_other_symptom_3")
    sleep_ms(page, 300)

    for index, field_name in enumerate(oci_eq_fields):
        optional_point_section(
            page,
            option=oci_eq_options[field_name],
            tabs=1 if index == 0 else 2,
            orientation="horizontal",
        )
        executed_steps.append(f"select_{field_name}")
        sleep_ms(page, 300)

    press_tab(page, 2)
    type_text(page, efectos_secundarios.get("eq_5d_scale", ""))
    executed_steps.append("type_eq_5d_scale")
    sleep_ms(page, 300)

    for index, field_name in enumerate(cgi_fields):
        optional_point_section(
            page,
            option=cgi_options[field_name],
            tabs=1 if index == 0 else 2,
            orientation="horizontal",
        )
        executed_steps.append(f"select_{field_name}")
        sleep_ms(page, 300)

    return executed_steps, record_id


def run(
    patient_json_path: Path,
    schema_path: Path,
    screenshot_dir: Path,
    log_path: Path = DEFAULT_LOG_PATH,
    headless: bool = False,
) -> dict[str, Any]:
    patient_data = load_json(patient_json_path)
    schema = load_json(schema_path)
    survey_url = PROD_SURVEY_URL
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    patient_identifier = patient_id_from_json_path(patient_json_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(survey_url, wait_until="domcontentloaded")
            page.wait_for_timeout(700)
            wait_for_user_to_start_flow()
            enter_survey_if_needed(page)
            wait_for_user_after_begin()
            executed_steps, record_id = execute_partial_flow(page, patient_data)
            update_ingestion_log(log_path, patient_identifier, record_id, survey_url)

            return {
                "status": "completed",
                "flow": "partial_keyboard_sequence",
                "executed_steps": executed_steps,
                "patient": patient_identifier,
                "record_id": record_id,
                "submitted_at": _utc_now_iso(),
            }

        except PlaywrightTimeoutError as error:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            screenshot = screenshot_dir / f"{patient_json_path.stem}_{stamp}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            return {
                "status": "failed",
                "error": f"Timeout filling form: {error}",
                "screenshot": str(screenshot),
                "submitted_at": _utc_now_iso(),
            }
        except Exception as error:  # noqa: BLE001
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            screenshot = screenshot_dir / f"{patient_json_path.stem}_{stamp}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            return {
                "status": "failed",
                "error": str(error),
                "screenshot": str(screenshot),
                "submitted_at": _utc_now_iso(),
            }
        finally:
            if not headless:
                print("Flujo terminado. Cierra la ventana del navegador cuando quieras para terminar.")
                try:
                    while browser.is_connected():
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
            try:
                context.close()
                browser.close()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed keyboard flow on REDCap survey.")
    parser.add_argument("--json", required=True, type=Path, help="Patient JSON path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH, help="Schema path.")
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=DEFAULT_SCREENSHOT_DIR,
        help="Error screenshot output folder.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Ingestion log path (patient -> record_id).",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        patient_json_path=args.json,
        schema_path=args.schema,
        screenshot_dir=args.screenshot_dir,
        log_path=args.log_path,
        headless=args.headless,
    )
    print(json.dumps(result, ensure_ascii=False))
