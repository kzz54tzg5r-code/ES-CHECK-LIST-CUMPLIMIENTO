# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from zipfile import ZipFile
from io import BytesIO
import uuid
import html
from PIL import Image, ImageDraw, ImageFont

# =============================
# ORION - CHECKLIST EVIDENCIAS
# =============================

st.set_page_config(
    page_title="ORION | Checklist de Evidencias",
    page_icon="✅",
    layout="wide"
)

ADMIN_PASSWORD = "admin123"
DATA_DIR = Path("data_orion")
EVIDENCE_DIR = DATA_DIR / "evidencias"
CONFIG_FILE = DATA_DIR / "checklist_config.csv"
EVIDENCE_FILE = DATA_DIR / "evidencias_registro.csv"
MANUAL_FILE = DATA_DIR / "checklist_manual.csv"

TIENDAS_DEFAULT = [
    "IZT", "VALL", "ECA", "PUE", "ARCO", "GDL", "TOL", "IXT", "MIR",
    "PUE SUR", "QRO", "LEÓN", "NAU", "OLIVAR", "CENTRO", "VER", "AGS"
]

CHECKLIST_DEFAULT = [
    {"Concepto": "GANCHOS 30%", "Peso": 1, "Activo": True},
    {"Concepto": "GANCHOS 40%", "Peso": 1, "Activo": True},
    {"Concepto": "GANCHOS 50%", "Peso": 1, "Activo": True},
]

DATA_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)


def save_df(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_config() -> pd.DataFrame:
    if CONFIG_FILE.exists():
        df = pd.read_csv(CONFIG_FILE)
    else:
        df = pd.DataFrame(CHECKLIST_DEFAULT)
        save_df(df, CONFIG_FILE)
    if "Activo" in df.columns:
        df["Activo"] = df["Activo"].astype(str).str.lower().isin(["true", "1", "sí", "si"])
    return df


def load_evidences() -> pd.DataFrame:
    cols = [
        "ID", "Semana", "Tienda", "Concepto", "Archivo", "Comentario_Tienda",
        "Responsable", "Fecha_Carga", "Estatus", "Comentario_Admin", "Fecha_Revision"
    ]
    if EVIDENCE_FILE.exists():
        df = pd.read_csv(EVIDENCE_FILE, dtype=str, encoding="utf-8-sig").fillna("")
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        df["Estatus"] = df["Estatus"].replace({"nan": "", "None": ""}).fillna("").astype(str)
        df["Comentario_Admin"] = df["Comentario_Admin"].replace({"nan": "", "None": ""}).fillna("").astype(str)
        df["Fecha_Revision"] = df["Fecha_Revision"].replace({"nan": "", "None": ""}).fillna("").astype(str)
        return df[cols]
    df = pd.DataFrame(columns=cols)
    save_df(df, EVIDENCE_FILE)
    return df


def load_manual() -> pd.DataFrame:
    cols = ["Semana", "Tienda", "Concepto", "Estatus_Manual", "Comentario_Admin", "Fecha_Actualizacion"]
    if MANUAL_FILE.exists():
        df = pd.read_csv(MANUAL_FILE, dtype=str, encoding="utf-8-sig").fillna("")
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        df["Estatus_Manual"] = df["Estatus_Manual"].replace({"nan": "", "None": ""}).fillna("").astype(str)
        return df[cols]
    df = pd.DataFrame(columns=cols)
    save_df(df, MANUAL_FILE)
    return df


def upsert_manual(base: pd.DataFrame, semana: str, tienda: str, concepto: str, estatus: str, comentario: str = "") -> pd.DataFrame:
    mask = (base["Semana"].astype(str) == str(semana)) & (base["Tienda"] == tienda) & (base["Concepto"] == concepto)
    row = {
        "Semana": semana,
        "Tienda": tienda,
        "Concepto": concepto,
        "Estatus_Manual": estatus,
        "Comentario_Admin": comentario,
        "Fecha_Actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if mask.any():
        for k, v in row.items():
            base.loc[mask, k] = v
    else:
        base = pd.concat([base, pd.DataFrame([row])], ignore_index=True)
    return base

def fmt_pct(x):
    try:
        return f"{float(x):.0f}%"
    except Exception:
        return "0%"


def status_icon(status):
    if status == "Aceptada":
        return "✅"
    if status == "Rechazada":
        return "❌"
    if status == "Pendiente":
        return "🟡"
    return "⬜"


def calculate_matrix(evidencias: pd.DataFrame, config: pd.DataFrame, semana: str, manual: pd.DataFrame | None = None) -> pd.DataFrame:
    conceptos = config[config["Activo"] == True]["Concepto"].tolist()
    rows = []
    ev_sem = evidencias[evidencias["Semana"].astype(str) == str(semana)] if semana != "Todas" else evidencias.copy()
    manual = manual if manual is not None else pd.DataFrame(columns=["Semana", "Tienda", "Concepto", "Estatus_Manual"])
    man_sem = manual[manual["Semana"].astype(str) == str(semana)] if semana != "Todas" else manual.copy()

    for tienda in TIENDAS_DEFAULT:
        row = {"Tienda": tienda}
        accepted = 0
        required = 0
        for concepto in conceptos:
            subset = ev_sem[(ev_sem["Tienda"] == tienda) & (ev_sem["Concepto"] == concepto)]
            man = man_sem[(man_sem["Tienda"] == tienda) & (man_sem["Concepto"] == concepto)]
            manual_status = man["Estatus_Manual"].iloc[-1] if not man.empty else ""

            if manual_status == "N/A":
                row[concepto] = "N/A"
                continue

            required += 1
            if manual_status == "Aceptada" or (not subset.empty and (subset["Estatus"] == "Aceptada").any()):
                row[concepto] = "OK"
                accepted += 1
            elif manual_status == "Rechazada" or (not subset.empty and (subset["Estatus"] == "Rechazada").any()):
                row[concepto] = "NO"
            elif manual_status == "Pendiente" or not subset.empty:
                row[concepto] = "PEND"
            else:
                row[concepto] = ""
        row["% Cumplimiento"] = fmt_pct((accepted / required * 100) if required else 0)
        rows.append(row)
    return pd.DataFrame(rows)


def render_portal_table(df: pd.DataFrame) -> str:
    # Tabla visual con colores tipo Portal Web: encabezados azul/gris y filas alternadas azul claro.
    html_parts = ["<style>",
            ".portal-table{border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:15px;}",
            ".portal-table th{background:#2f67a8;color:white;padding:8px;border:1px solid #1b1b1b;text-align:center;font-weight:800;}",
            ".portal-table th:first-child,.portal-table th:last-child{background:#a6a6a6;color:white;}",
            ".portal-table td{border:1px solid #1b1b1b;padding:7px;text-align:center;font-weight:700;}",
            ".portal-table tr:nth-child(even) td{background:#d9e8f6;}",
            ".portal-table tr:nth-child(odd) td{background:#ffffff;}",
            ".portal-table td:first-child{font-weight:900;}",
            ".dot{height:18px;width:18px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:middle;border:1px solid rgba(0,0,0,.25);}",
            ".green{background:#69ad93}.red{background:#e85b35}.amber{background:#c58b4a}.gray{background:#9a9a9a}.blank{background:#ffffff}",
            "</style>"]
    html_parts.append('<table class="portal-table"><thead><tr>')
    for col in df.columns:
        html_parts.append(f"<th>{html.escape(str(col))}</th>")
    html_parts.append("</tr></thead><tbody>")
    for _, row in df.iterrows():
        html_parts.append("<tr>")
        for col in df.columns:
            val = str(row[col])
            if col == "% Cumplimiento":
                try:
                    num = float(val.replace("%", ""))
                except Exception:
                    num = 0
                klass = "green" if num >= 80 else "amber" if num >= 50 else "red"
                html_parts.append(f'<td><span class="dot {klass}"></span>{html.escape(val)}</td>')
            else:
                if val == "OK":
                    cell = '<span class="dot green"></span>OK'
                elif val == "NO":
                    cell = '<span class="dot red"></span>NO'
                elif val == "PEND":
                    cell = '<span class="dot amber"></span>PEND'
                elif val == "N/A":
                    cell = '<span class="dot gray"></span>N/A'
                elif val == "":
                    cell = '<span class="dot blank"></span>'
                else:
                    cell = html.escape(val)
                html_parts.append(f"<td>{cell}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table>")
    return "".join(html_parts)


def make_matrix_image(df: pd.DataFrame, title: str) -> BytesIO:
    """Genera una imagen PNG del checklist general con estilo tipo portal web."""
    font = ImageFont.load_default()
    header_bg = (47, 103, 168)
    gray_bg = (166, 166, 166)
    even_bg = (217, 232, 246)
    odd_bg = (255, 255, 255)
    border = (27, 27, 27)
    white = (255, 255, 255)
    green = (105, 173, 147)
    red = (232, 91, 53)
    amber = (197, 139, 74)
    gray = (154, 154, 154)
    blue_text = (35, 85, 140)

    cols = list(df.columns)
    col_widths = []
    for col in cols:
        max_len = max([len(str(col))] + [len(str(v)) for v in df[col].tolist()])
        col_widths.append(max(90, min(190, max_len * 8 + 28)))
    row_h = 34
    title_h = 54
    width = sum(col_widths) + 2
    height = title_h + row_h * (len(df) + 1) + 2
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, title_h], fill=(247, 249, 255))
    draw.text((12, 18), title, fill=blue_text, font=font)

    y = title_h
    x = 0
    for i, col in enumerate(cols):
        bg = gray_bg if i == 0 or col == "% Cumplimiento" else header_bg
        draw.rectangle([x, y, x + col_widths[i], y + row_h], fill=bg, outline=border)
        draw.text((x + 6, y + 10), str(col)[:24], fill=white, font=font)
        x += col_widths[i]

    for r, (_, row) in enumerate(df.iterrows()):
        y = title_h + row_h * (r + 1)
        bg = even_bg if r % 2 else odd_bg
        x = 0
        for i, col in enumerate(cols):
            val = str(row[col])
            draw.rectangle([x, y, x + col_widths[i], y + row_h], fill=bg, outline=border)
            tx = x + 8
            if val in ["OK", "NO", "PEND", "N/A"] or col == "% Cumplimiento":
                if val == "OK":
                    dot_color, text_val = green, "OK"
                elif val == "NO":
                    dot_color, text_val = red, "NO"
                elif val == "PEND":
                    dot_color, text_val = amber, "PEND"
                elif val == "N/A":
                    dot_color, text_val = gray, "N/A"
                else:
                    try:
                        num = float(val.replace("%", ""))
                    except Exception:
                        num = 0
                    dot_color = green if num >= 80 else amber if num >= 50 else red
                    text_val = val
                draw.ellipse([tx, y + 9, tx + 15, y + 24], fill=dot_color, outline=border)
                draw.text((tx + 22, y + 11), text_val, fill=(0, 0, 0), font=font)
            else:
                draw.text((tx, y + 11), val[:24], fill=(0, 0, 0), font=font)
            x += col_widths[i]

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def make_zip_by_store(evidencias: pd.DataFrame) -> BytesIO:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            evidencias.to_excel(writer, sheet_name="Concentrado", index=False)
            for tienda in sorted(evidencias["Tienda"].dropna().unique()):
                evidencias[evidencias["Tienda"] == tienda].to_excel(
                    writer, sheet_name=str(tienda)[:31], index=False
                )
        zip_file.writestr("Concentrado_Evidencias.xlsx", excel_buffer.getvalue())

        for _, row in evidencias.iterrows():
            archivo = str(row.get("Archivo", ""))
            tienda = str(row.get("Tienda", "SIN_TIENDA"))
            concepto = str(row.get("Concepto", "SIN_CONCEPTO")).replace("/", "-")
            if archivo and Path(archivo).exists():
                ext = Path(archivo).suffix
                zip_name = f"{tienda}/{concepto}/{Path(archivo).stem}{ext}"
                zip_file.write(archivo, zip_name)
    buffer.seek(0)
    return buffer


def delete_evidence_record(evidencias_df: pd.DataFrame, evidence_id: str) -> pd.DataFrame:
    """Elimina una evidencia del registro y borra el archivo físico si existe."""
    target = evidencias_df[evidencias_df["ID"].astype(str) == str(evidence_id)]
    if not target.empty:
        archivo = str(target.iloc[0].get("Archivo", ""))
        try:
            if archivo and Path(archivo).exists():
                Path(archivo).unlink()
        except Exception:
            pass
    return evidencias_df[evidencias_df["ID"].astype(str) != str(evidence_id)].reset_index(drop=True)

st.markdown("""
<style>
.main-title {font-size: 34px; font-weight: 800; color: #3366CC; margin-bottom: 0px;}
.subtitle {font-size: 15px; color: #555; margin-top: 0px;}
.kpi-card {background: #f7f9ff; padding: 18px; border-radius: 14px; border-left: 7px solid #3366CC; box-shadow: 0 2px 8px rgba(0,0,0,.06);}
.kpi-number {font-size: 28px; font-weight: 800; color: #3366CC;}
.kpi-label {font-size: 13px; color: #666;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">ORION | Checklist de Evidencias</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Operaciones Ropa · Control de evidencias por tienda</div>', unsafe_allow_html=True)

config = load_config()
evidencias = load_evidences()
manual = load_manual()

with st.sidebar:
    st.header("Acceso")
    rol = st.selectbox("Tipo de usuario", ["Tienda", "Administrador"])
    is_admin = False
    if rol == "Administrador":
        pwd = st.text_input("Contraseña administrador", type="password")
        is_admin = pwd == ADMIN_PASSWORD
        if pwd and not is_admin:
            st.error("Contraseña incorrecta")
    semana = st.text_input("Semana", value=f"SEM {datetime.now().isocalendar().week}")

active_concepts = config[config["Activo"] == True]["Concepto"].tolist()

# KPIs
matrix = calculate_matrix(evidencias, config, semana, manual)
try:
    cumplimiento_prom = matrix["% Cumplimiento"].str.replace("%", "", regex=False).astype(float).mean()
except Exception:
    cumplimiento_prom = 0
pendientes = int((evidencias["Estatus"] == "Pendiente").sum())
aceptadas = int((evidencias["Estatus"] == "Aceptada").sum())
rechazadas = int((evidencias["Estatus"] == "Rechazada").sum())

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-number">{fmt_pct(cumplimiento_prom)}</div><div class="kpi-label">Cumplimiento promedio</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-number">{aceptadas}</div><div class="kpi-label">Aceptadas</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-number">{pendientes}</div><div class="kpi-label">Pendientes</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-number">{rechazadas}</div><div class="kpi-label">Rechazadas</div></div>', unsafe_allow_html=True)

st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Checklist General",
    "📤 Cargar Evidencias",
    "🛡️ Validación Admin",
    "⚙️ Configuración"
])

with tab1:
    st.subheader("Checklist de cumplimiento")
    st.caption("El cumplimiento considera evidencias aceptadas. En administración, cada punto puede modificarse desde su propio menú y también puede marcarse como N/A.")
    st.markdown(render_portal_table(matrix), unsafe_allow_html=True)

    img_buffer = make_matrix_image(matrix, f"ORION | Checklist General | {semana}")
    st.download_button(
        "Descargar checklist como imagen PNG",
        data=img_buffer.getvalue(),
        file_name=f"Checklist_General_{semana}.png".replace(" ", "_"),
        mime="image/png"
    )

    if is_admin:
        st.divider()
        st.markdown("**Modificar checklist general por punto — solo administrador**")
        st.caption("Abre cada tienda y cada punto del checklist para seleccionar qué hacer: Sin marcar, Pendiente, Aceptada, Rechazada o N/A.")

        tienda_filtro_punto = st.selectbox("Tienda para modificar", TIENDAS_DEFAULT, key="tienda_filtro_punto")
        st.markdown(f"### {tienda_filtro_punto}")

        if not active_concepts:
            st.info("No hay encabezados activos en el checklist.")
        else:
            for concepto_item in active_concepts:
                man_row = manual[
                    (manual["Semana"].astype(str) == str(semana))
                    & (manual["Tienda"] == tienda_filtro_punto)
                    & (manual["Concepto"] == concepto_item)
                ]
                current_status = man_row["Estatus_Manual"].iloc[-1] if not man_row.empty else ""
                current_comment = man_row["Comentario_Admin"].iloc[-1] if not man_row.empty else ""

                ev_subset = evidencias[
                    (evidencias["Semana"].astype(str) == str(semana))
                    & (evidencias["Tienda"] == tienda_filtro_punto)
                    & (evidencias["Concepto"] == concepto_item)
                ]

                visible_status = current_status if current_status else "Sin marcar"
                with st.expander(f"{concepto_item} | Estatus actual: {visible_status}"):
                    st.write("**Menú del punto de checklist**")
                    if not ev_subset.empty:
                        st.caption(f"Evidencias cargadas para este punto: {len(ev_subset)}")
                        st.dataframe(
                            ev_subset[["ID", "Estatus", "Responsable", "Fecha_Carga", "Comentario_Tienda"]],
                            width="stretch",
                            hide_index=True
                        )
                    else:
                        st.caption("Sin evidencias cargadas para este punto.")

                    opciones = ["Sin marcar", "Pendiente", "Aceptada", "Rechazada", "N/A"]
                    idx_default = opciones.index(visible_status) if visible_status in opciones else 0
                    accion = st.selectbox(
                        "Qué quieres hacer con este punto",
                        opciones,
                        index=idx_default,
                        key=f"accion_{tienda_filtro_punto}_{concepto_item}"
                    )
                    comentario_punto = st.text_input(
                        "Comentario del administrador",
                        value=str(current_comment) if str(current_comment) != "nan" else "",
                        key=f"comentario_punto_{tienda_filtro_punto}_{concepto_item}"
                    )
                    if st.button("Guardar este punto", key=f"guardar_punto_{tienda_filtro_punto}_{concepto_item}"):
                        manual_status = "" if accion == "Sin marcar" else accion
                        manual_new = upsert_manual(manual, semana, tienda_filtro_punto, concepto_item, manual_status, comentario_punto)
                        save_df(manual_new, MANUAL_FILE)
                        st.success("Punto actualizado.")
                        st.rerun()

    excel_matrix = BytesIO()
    matrix.to_excel(excel_matrix, index=False, engine="openpyxl")
    st.download_button(
        "Descargar checklist en Excel",
        data=excel_matrix.getvalue(),
        file_name=f"Checklist_Evidencias_{semana}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


with tab2:
    st.subheader("Carga de evidencias por tienda")
    st.caption("Selecciona la tienda. Las actividades se muestran automáticamente de acuerdo con los encabezados activos del checklist.")

    tienda = st.selectbox("Filtro por tienda", TIENDAS_DEFAULT, key="tienda_carga_evidencia")
    responsable = st.text_input("Responsable", key="responsable_general")

    if not active_concepts:
        st.warning("No hay actividades activas en el checklist. El administrador debe configurar al menos un encabezado activo.")
    else:
        st.markdown("### Actividades del checklist")
        st.caption("En cada actividad puedes cargar evidencia desde cámara o seleccionarla desde galería/archivos.")

        for concepto in active_concepts:
            with st.expander(f"Actividad: {concepto}", expanded=False):
                comentario = st.text_area(
                    "Comentario de tienda",
                    key=f"comentario_{tienda}_{concepto}"
                )

                cam_col, gal_col = st.columns(2)
                with cam_col:
                    st.markdown("**Abrir cámara**")
                    camera_file = st.camera_input(
                        "Tomar foto",
                        key=f"camara_{tienda}_{concepto}"
                    )
                with gal_col:
                    st.markdown("**Seleccionar desde galería / archivo**")
                    gallery_files = st.file_uploader(
                        "Cargar desde galería",
                        type=["jpg", "jpeg", "png", "webp", "pdf"],
                        accept_multiple_files=True,
                        key=f"galeria_{tienda}_{concepto}"
                    )

                if st.button("Guardar evidencia de esta actividad", type="primary", key=f"guardar_{tienda}_{concepto}"):
                    files_to_save = []
                    if camera_file is not None:
                        files_to_save.append(camera_file)
                    if gallery_files:
                        files_to_save.extend(gallery_files)

                    if not files_to_save:
                        st.warning("Carga al menos una evidencia desde cámara o galería.")
                    else:
                        new_rows = []
                        store_dir = EVIDENCE_DIR / tienda / str(semana) / concepto.replace("/", "-")
                        store_dir.mkdir(parents=True, exist_ok=True)

                        for file in files_to_save:
                            evidence_id = str(uuid.uuid4())[:8]
                            original_name = getattr(file, "name", "camara.png") or "camara.png"
                            safe_name = f"{evidence_id}_{original_name}"
                            path = store_dir / safe_name
                            path.write_bytes(file.getbuffer())
                            new_rows.append({
                                "ID": evidence_id,
                                "Semana": semana,
                                "Tienda": tienda,
                                "Concepto": concepto,
                                "Archivo": str(path),
                                "Comentario_Tienda": comentario,
                                "Responsable": responsable,
                                "Fecha_Carga": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "Estatus": "Pendiente",
                                "Comentario_Admin": "",
                                "Fecha_Revision": ""
                            })

                        evidencias_new = pd.concat([evidencias, pd.DataFrame(new_rows)], ignore_index=True)
                        save_df(evidencias_new, EVIDENCE_FILE)
                        st.success("Evidencia guardada. Queda pendiente de validación por administrador.")
                        st.rerun()

    st.subheader("Mis evidencias cargadas")
    st.caption("Si cargaste una evidencia duplicada, puedes eliminarla con el botón rojo de menos.")
    mis_evidencias = evidencias[evidencias["Tienda"] == tienda].copy()

    if mis_evidencias.empty:
        st.info("Esta tienda todavía no tiene evidencias cargadas.")
    else:
        for _, ev in mis_evidencias.sort_values("Fecha_Carga", ascending=False).iterrows():
            c_info, c_status, c_delete = st.columns([6, 2, 1])
            with c_info:
                st.markdown(
                    f"**{ev['Concepto']}**  \n"
                    f"Semana: {ev['Semana']} | Responsable: {ev['Responsable']} | Fecha: {ev['Fecha_Carga']}"
                )
                if str(ev.get("Comentario_Tienda", "")):
                    st.caption(f"Comentario: {ev.get('Comentario_Tienda', '')}")
            with c_status:
                st.write(f"Estatus: **{ev['Estatus']}**")
            with c_delete:
                if st.button("🔴 -", key=f"delete_ev_{ev['ID']}", help="Eliminar evidencia duplicada"):
                    evidencias_new = delete_evidence_record(evidencias, ev["ID"])
                    save_df(evidencias_new, EVIDENCE_FILE)
                    st.success("Evidencia eliminada.")
                    st.rerun()

        st.dataframe(mis_evidencias, width="stretch", hide_index=True)

with tab3:
    st.subheader("Validación de evidencias")
    if not is_admin:
        st.warning("Esta sección es solo para administrador.")
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            filtro_tienda = st.selectbox("Filtrar tienda", ["Todas"] + TIENDAS_DEFAULT)
        with f2:
            filtro_status = st.selectbox("Filtrar estatus", ["Todos", "Pendiente", "Aceptada", "Rechazada"])
        with f3:
            filtro_concepto = st.selectbox("Filtrar concepto", ["Todos"] + active_concepts)

        df_val = evidencias.copy()
        if filtro_tienda != "Todas":
            df_val = df_val[df_val["Tienda"] == filtro_tienda]
        if filtro_status != "Todos":
            df_val = df_val[df_val["Estatus"] == filtro_status]
        if filtro_concepto != "Todos":
            df_val = df_val[df_val["Concepto"] == filtro_concepto]

        if df_val.empty:
            st.info("No hay evidencias con esos filtros.")
        else:
            for idx, row in df_val.iterrows():
                with st.expander(f"{status_icon(row['Estatus'])} {row['Tienda']} | {row['Concepto']} | {row['Fecha_Carga']}"):
                    st.write(f"**Responsable:** {row['Responsable']}")
                    st.write(f"**Comentario tienda:** {row['Comentario_Tienda']}")
                    st.write(f"**Estatus actual:** {row['Estatus']}")
                    archivo = str(row["Archivo"])
                    if archivo and Path(archivo).exists():
                        if Path(archivo).suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                            st.image(archivo, width="stretch")
                        else:
                            st.write(f"Archivo: {Path(archivo).name}")
                    comentario_admin = st.text_area("Comentario administrador", value=str(row.get("Comentario_Admin", "")), key=f"coment_{row['ID']}")
                    for _col in ["Estatus", "Comentario_Admin", "Fecha_Revision"]:
                        if _col in evidencias.columns:
                            evidencias[_col] = evidencias[_col].fillna("").astype(str)
                    a, b, c = st.columns(3)
                    if a.button("Aceptar", key=f"aceptar_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Aceptada"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if b.button("Rechazar", key=f"rechazar_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Rechazada"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if c.button("Pendiente", key=f"pendiente_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Pendiente"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()

        st.divider()
        st.subheader("Descarga de concentrado")
        zip_buffer = make_zip_by_store(evidencias)
        st.download_button(
            "⬇️ Descargar evidencias por tienda ZIP",
            data=zip_buffer,
            file_name=f"Evidencias_ORION_{semana}.zip",
            mime="application/zip"
        )

with tab4:
    st.subheader("Configuración del checklist")
    if not is_admin:
        st.warning("Esta sección es solo para administrador.")
    else:
        st.caption("Edita los encabezados del checklist. Cada encabezado será un concepto obligatorio para cargar evidencias.")
        edited = st.data_editor(
            config,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Concepto": st.column_config.TextColumn("Encabezado / Concepto", required=True),
                "Peso": st.column_config.NumberColumn("Peso", min_value=0, step=1),
                "Activo": st.column_config.CheckboxColumn("Activo")
            }
        )
        if st.button("Guardar configuración", type="primary"):
            edited = edited.dropna(subset=["Concepto"])
            edited["Concepto"] = edited["Concepto"].astype(str).str.strip().str.upper()
            edited = edited[edited["Concepto"] != ""]
            save_df(edited, CONFIG_FILE)
            st.success("Configuración guardada.")
            st.rerun()

        st.info("Para cambiar tiendas fijas, edita la lista TIENDAS_DEFAULT dentro de app.py.")
