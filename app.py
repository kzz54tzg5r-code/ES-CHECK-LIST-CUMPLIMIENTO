import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from zipfile import ZipFile
from io import BytesIO
import uuid

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
        df = pd.read_csv(EVIDENCE_FILE)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df[cols]
    df = pd.DataFrame(columns=cols)
    save_df(df, EVIDENCE_FILE)
    return df


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


def calculate_matrix(evidencias: pd.DataFrame, config: pd.DataFrame, semana: str) -> pd.DataFrame:
    conceptos = config[config["Activo"] == True]["Concepto"].tolist()
    rows = []
    ev_sem = evidencias[evidencias["Semana"].astype(str) == str(semana)] if semana != "Todas" else evidencias.copy()
    for tienda in TIENDAS_DEFAULT:
        row = {"Tienda": tienda}
        accepted = 0
        required = len(conceptos)
        for concepto in conceptos:
            subset = ev_sem[(ev_sem["Tienda"] == tienda) & (ev_sem["Concepto"] == concepto)]
            if not subset.empty and (subset["Estatus"] == "Aceptada").any():
                row[concepto] = "✅"
                accepted += 1
            elif not subset.empty and (subset["Estatus"] == "Rechazada").any():
                row[concepto] = "❌"
            elif not subset.empty:
                row[concepto] = "🟡"
            else:
                row[concepto] = "⬜"
        row["% Cumplimiento"] = fmt_pct((accepted / required * 100) if required else 0)
        rows.append(row)
    return pd.DataFrame(rows)


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
matrix = calculate_matrix(evidencias, config, semana)
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
    st.caption("El cumplimiento solo considera evidencias aceptadas por administrador.")
    st.dataframe(matrix, use_container_width=True, hide_index=True)

    excel_matrix = BytesIO()
    matrix.to_excel(excel_matrix, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Descargar checklist en Excel",
        data=excel_matrix.getvalue(),
        file_name=f"Checklist_Evidencias_{semana}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with tab2:
    st.subheader("Carga de evidencias por tienda")
    st.caption("Los conceptos disponibles salen automáticamente de los encabezados activos del checklist.")

    tienda = st.selectbox("Tienda", TIENDAS_DEFAULT)
    concepto = st.selectbox("Concepto del checklist", active_concepts if active_concepts else ["Sin conceptos activos"])
    responsable = st.text_input("Responsable")
    comentario = st.text_area("Comentario de tienda")
    files = st.file_uploader(
        "Cargar evidencia",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True
    )

    if st.button("Guardar evidencia", type="primary"):
        if not files:
            st.warning("Carga al menos una evidencia.")
        elif not active_concepts:
            st.warning("No hay conceptos activos en el checklist.")
        else:
            new_rows = []
            store_dir = EVIDENCE_DIR / tienda / str(semana) / concepto.replace("/", "-")
            store_dir.mkdir(parents=True, exist_ok=True)
            for file in files:
                evidence_id = str(uuid.uuid4())[:8]
                safe_name = f"{evidence_id}_{file.name}"
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
    st.dataframe(evidencias[evidencias["Tienda"] == tienda], use_container_width=True, hide_index=True)

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
                            st.image(archivo, use_container_width=True)
                        else:
                            st.write(f"Archivo: {Path(archivo).name}")
                    comentario_admin = st.text_area("Comentario administrador", value=str(row.get("Comentario_Admin", "")), key=f"coment_{row['ID']}")
                    a, b, c = st.columns(3)
                    if a.button("✅ Aceptar", key=f"aceptar_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Aceptada"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if b.button("❌ Rechazar", key=f"rechazar_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Rechazada"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if c.button("🟡 Pendiente", key=f"pendiente_{row['ID']}"):
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
            use_container_width=True,
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
