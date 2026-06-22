# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from zipfile import ZipFile
from io import BytesIO
import uuid
import html
import base64
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import landscape, A3
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Circle, String

# =============================
# ORION - CHECKLIST EVIDENCIAS
# =============================

st.set_page_config(
    page_title="ES Check List Evidencias",
    page_icon="✅",
    layout="wide"
)

ADMIN_PASSWORD = "admin123"
DATA_DIR = Path("data_orion")
ASSETS_DIR = Path("assets")
PRICE_LOGO = ASSETS_DIR / "price_shoes.png"
PRICE_LOGO_B64 = ""
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

def now_mx() -> datetime:
    """Hora local de México para reportes y PDF."""
    try:
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now()


def register_pdf_fonts():
    """Registra fuente Unicode para palomita/tache en PDF."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    try:
        if Path(candidates[0]).exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans", candidates[0]))
        if Path(candidates[1]).exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", candidates[1]))
        return "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"



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
        "Fecha_Actualizacion": now_mx().strftime("%Y-%m-%d %H:%M:%S"),
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



def matrix_to_admin_editor(matrix_df: pd.DataFrame, conceptos: list[str]) -> pd.DataFrame:
    """Convierte la matriz visual a tabla editable con casillas circulares."""
    editor = matrix_df[["Tienda"] + conceptos].copy()
    reverse = {
        "OK": "✓",
        "NO": "✕",
        "PEND": "!",
        "N/A": "N/A",
        "": ""
    }
    for concepto in conceptos:
        editor[concepto] = editor[concepto].map(reverse).fillna("⚪")
    if "% Cumplimiento" in matrix_df.columns:
        editor["% Cumplimiento"] = matrix_df["% Cumplimiento"].astype(str)
    return editor


def save_admin_editor_to_manual(editor_df: pd.DataFrame, manual_df: pd.DataFrame, semana: str, conceptos: list[str]) -> pd.DataFrame:
    """Guarda lo editado dentro de la tabla del checklist general en la base manual."""
    base = manual_df.copy()
    status_map = {
        "✓": "Aceptada",
        "✕": "Rechazada",
        "!": "Pendiente",
        "N/A": "N/A",
        "": "",
        "Aceptada": "Aceptada",
        "Rechazada": "Rechazada",
        "Pendiente": "Pendiente",
        "N/A": "N/A",
        "Sin marcar": "",
    }
    for _, row in editor_df.iterrows():
        tienda = str(row.get("Tienda", ""))
        if not tienda:
            continue
        for concepto in conceptos:
            accion = str(row.get(concepto, ""))
            estatus = status_map.get(accion, "")
            base = upsert_manual(base, semana, tienda, concepto, estatus, "Modificado desde matriz principal")
    return base

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
                    cell = '<span style="color:#2ca25f;font-size:24px;font-weight:900;">✓</span>'
                elif val == "NO":
                    cell = '<span style="color:#e31a1c;font-size:24px;font-weight:900;">✕</span>'
                elif val == "PEND":
                    cell = '<span style="color:#f39c12;font-size:24px;font-weight:900;">!</span>'
                elif val == "N/A":
                    cell = '<span style="color:#6b7280;font-size:14px;font-weight:900;">N/A</span>'
                elif val == "":
                    cell = ''
                else:
                    cell = html.escape(val)
                html_parts.append(f"<td>{cell}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table>")
    return "".join(html_parts)


def _load_font(size: int, bold: bool = False):
    """Carga una fuente clara para exportar imagen en alta resolución."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def make_matrix_image(df: pd.DataFrame, title: str) -> BytesIO:
    """Genera PNG legible del checklist general con textos visibles y alta calidad."""
    font = _load_font(90, bold=True)
    font_small = _load_font(82, bold=True)
    title_font = _load_font(120, bold=True)

    header_bg = (47, 103, 168)
    gray_bg = (166, 166, 166)
    even_bg = (217, 232, 246)
    odd_bg = (255, 255, 255)
    border = (20, 20, 20)
    white = (255, 255, 255)
    black = (38, 40, 55)
    green = (105, 173, 147)
    red = (239, 47, 50)
    amber = (197, 139, 74)
    gray = (154, 154, 154)
    blue_text = (35, 85, 140)

    cols = list(df.columns)
    col_widths = []
    for col in cols:
        if col == "Tienda":
            base = 380
        elif col == "% Cumplimiento":
            base = 650
        else:
            base = max(760, min(1150, 44 * len(str(col)) + 300))
        col_widths.append(base)

    row_h = 240
    title_h = 340
    margin = 44
    width = sum(col_widths) + margin * 2
    height = title_h + row_h * (len(df) + 1) + margin * 2
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, title_h + margin], fill=(247, 249, 255))
    draw.text((margin, 56), title, fill=blue_text, font=title_font)

    y = title_h
    x = margin
    for i, col in enumerate(cols):
        bg = gray_bg if i == 0 or col == "% Cumplimiento" else header_bg
        draw.rectangle([x, y, x + col_widths[i], y + row_h], fill=bg, outline=border, width=3)
        lines = wrap_text_to_width(draw, str(col), font, col_widths[i] - 20)
        line_gap = 100
        total_h = len(lines) * line_gap
        ty = y + (row_h - total_h) / 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((x + (col_widths[i] - tw) / 2, ty), line, fill=white, font=font)
            ty += line_gap
        x += col_widths[i]

    for r, (_, row) in enumerate(df.iterrows()):
        y = title_h + row_h * (r + 1)
        bg = even_bg if r % 2 else odd_bg
        x = margin
        for i, col in enumerate(cols):
            val = str(row[col])
            draw.rectangle([x, y, x + col_widths[i], y + row_h], fill=bg, outline=border, width=3)

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
                dot = 90
                text_bbox = draw.textbbox((0, 0), text_val, font=font_small)
                text_w = text_bbox[2] - text_bbox[0]
                text_h = text_bbox[3] - text_bbox[1]
                total_w = dot + 18 + text_w
                start_x = x + (col_widths[i] - total_w) / 2
                dot_y = y + (row_h - dot) / 2
                draw.ellipse([start_x, dot_y, start_x + dot, dot_y + dot], fill=dot_color, outline=border, width=2)
                draw.text((start_x + dot + 18, y + (row_h - text_h) / 2 - 5), text_val, fill=black, font=font_small)
            else:
                text_val = val
                lines = wrap_text_to_width(draw, text_val, font_small, col_widths[i] - 20)
                line_gap = 95
                total_h = len(lines) * line_gap
                ty = y + (row_h - total_h) / 2
                for line in lines:
                    text_bbox = draw.textbbox((0, 0), line, font=font_small)
                    tw = text_bbox[2] - text_bbox[0]
                    draw.text((x + (col_widths[i] - tw) / 2, ty), line, fill=black, font=font_small)
                    ty += line_gap
            x += col_widths[i]

    # Exportar en ultra alta resolución con textos grandes y nítidos.
    # Se duplica el lienzo antes de guardar para que al descargar, abrir o pegar
    # en PowerPoint/WhatsApp no se pierda la lectura del texto.
    try:
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    except Exception:
        img = img.resize((img.width * 2, img.height * 2))

    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=False, dpi=(600, 600))
    buffer.seek(0)
    return buffer



def pdf_status_icon(status: str):
    """Icono vectorial para PDF: no usa BytesIO, PNG ni ImageReader."""
    if status == "":
        return ""

    colors_map = {
        "OK": colors.HexColor("#2CA25F"),
        "PEND": colors.HexColor("#F39C12"),
        "NO": colors.HexColor("#E31A1C"),
        "N/A": colors.HexColor("#6B7280"),
    }
    labels = {
        "OK": "✓",
        "PEND": "!",
        "NO": "✕",
        "N/A": "N/A",
    }

    d = Drawing(20, 20)
    d.add(Circle(10, 10, 9, fillColor=colors_map.get(status, colors.grey), strokeColor=None))

    label = labels.get(status, "")
    if status == "N/A":
        d.add(String(10, 7, label, textAnchor="middle", fontName="Helvetica-Bold", fontSize=6, fillColor=colors.white))
    else:
        d.add(String(10, 5.5, label, textAnchor="middle", fontName="Helvetica-Bold", fontSize=11, fillColor=colors.white))

    return d



def pdf_activity_kpi_table(df: pd.DataFrame, cols: list[str], styles) -> Table | None:
    """Tabla superior para PDF con % de cumplimiento por actividad."""
    activity_cols = [c for c in cols if c not in ["Tienda", "% Cumplimiento"]]
    if not activity_cols:
        return None

    kpi_style_title = ParagraphStyle(
        "KpiTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        alignment=1,
        textColor=colors.HexColor("#202235"),
    )
    kpi_style_pct = ParagraphStyle(
        "KpiPct",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        alignment=1,
    )
    kpi_style_small = ParagraphStyle(
        "KpiSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        alignment=1,
        textColor=colors.HexColor("#555555"),
    )

    row = []
    col_widths = []

    for actividad in activity_cols:
        serie = df[actividad].astype(str)
        requeridas = int((serie != "N/A").sum())
        aceptadas = int((serie == "OK").sum())
        pct = round((aceptadas / requeridas * 100), 0) if requeridas else 0

        if pct >= 90:
            pct_color = "#2CA25F"
            bg = colors.HexColor("#E9F7EF")
        elif pct >= 70:
            pct_color = "#F39C12"
            bg = colors.HexColor("#FFF7D6")
        else:
            pct_color = "#E31A1C"
            bg = colors.HexColor("#FDECEC")

        kpi_style_pct_colored = ParagraphStyle(
            f"KpiPct{actividad}",
            parent=kpi_style_pct,
            textColor=colors.HexColor(pct_color),
        )

        card = [
            Paragraph(str(actividad), kpi_style_title),
            Paragraph(f"{pct:.0f}%", kpi_style_pct_colored),
            Paragraph(f"{aceptadas} / {requeridas} aceptadas", kpi_style_small),
        ]
        row.append(card)
        col_widths.append(2.25 * inch)

    tbl = Table([row], colWidths=col_widths)

    commands = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEEA")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    for idx, actividad in enumerate(activity_cols):
        serie = df[actividad].astype(str)
        requeridas = int((serie != "N/A").sum())
        aceptadas = int((serie == "OK").sum())
        pct = round((aceptadas / requeridas * 100), 0) if requeridas else 0
        if pct >= 90:
            bg = colors.HexColor("#E9F7EF")
        elif pct >= 70:
            bg = colors.HexColor("#FFF7D6")
        else:
            bg = colors.HexColor("#FDECEC")
        commands.append(("BACKGROUND", (idx, 0), (idx, 0), bg))

    tbl.setStyle(TableStyle(commands))
    return tbl


def make_matrix_pdf(df: pd.DataFrame, title: str) -> BytesIO:
    """PDF corporativo optimizado para una sola hoja A3 horizontal."""
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A3),
        leftMargin=24,
        rightMargin=24,
        topMargin=22,
        bottomMargin=22
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitlePS", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=colors.HexColor("#202235"), alignment=2)
    bar_style = ParagraphStyle("BarPS", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.white)
    normal_style = ParagraphStyle("NormalPS", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=13)
    head_style = ParagraphStyle("HeadPS", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=1, textColor=colors.white)
    cell_style = ParagraphStyle("CellPS", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=1)

    elements = []

    if PRICE_LOGO.exists():
        logo = RLImage(str(PRICE_LOGO), width=1.45*inch, height=0.75*inch)
    else:
        logo = Paragraph("Price Shoes", styles["Heading2"])

    usable_width = landscape(A3)[0] - doc.leftMargin - doc.rightMargin

    header = Table(
        [[logo, Paragraph("ES Check List Evidencias", title_style)]],
        colWidths=[2.1*inch, usable_width - 2.1*inch]
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (0,0), "LEFT"),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    elements.append(header)

    bar = Table([[Paragraph("Corporativo · Producto Ropa", bar_style)]], colWidths=[usable_width])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#E6007E")),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    elements.append(bar)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"{title} | Generado: {now_mx().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Spacer(1, 6))

    legend_style = ParagraphStyle(
        "LegendPS",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8
    )

    legend = Table(
        [[
            pdf_status_icon("OK"),   Paragraph("Aceptada", legend_style),
            pdf_status_icon("PEND"), Paragraph("Pendiente", legend_style),
            pdf_status_icon("NO"),   Paragraph("Rechazada", legend_style),
            pdf_status_icon("N/A"),  Paragraph("N/A", legend_style),
            Paragraph("", legend_style),
            Paragraph("Sin marcar", legend_style),
        ]],
        colWidths=[
            0.35*inch, 1.15*inch,
            0.35*inch, 1.25*inch,
            0.35*inch, 1.30*inch,
            0.35*inch, 0.70*inch,
            0.20*inch, 1.20*inch
        ]
    )

    legend.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#D7DEEA")),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F7F9FF")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    elements.append(legend)
    elements.append(Spacer(1, 8))

    cols = list(df.columns)

    elements.append(Paragraph("<b>% de cumplimiento por actividad</b>", normal_style))
    elements.append(Spacer(1, 5))
    kpi_tbl = pdf_activity_kpi_table(df, cols, styles)
    if kpi_tbl is not None:
        elements.append(kpi_tbl)
        elements.append(Spacer(1, 10))

    page_width = landscape(A3)[0] - 48
    tienda_w = 0.9 * inch
    pct_w = 1.35 * inch
    activity_cols = [c for c in cols if c not in ["Tienda", "% Cumplimiento"]]
    activity_w = max(1.55*inch, (page_width - tienda_w - pct_w) / max(1, len(activity_cols)))

    col_widths = []
    for col in cols:
        if col == "Tienda":
            col_widths.append(tienda_w)
        elif col == "% Cumplimiento":
            col_widths.append(pct_w)
        else:
            col_widths.append(activity_w)

    display_map = {
        "OK": "✓",
        "NO": "✕",
        "PEND": "!",
        "N/A": "N/A",
        "": "",
    }

    rows_per_page = 10
    chunks = [df.iloc[i:i+rows_per_page] for i in range(0, len(df), rows_per_page)]

    for page_idx, chunk in enumerate(chunks):
        data = [[Paragraph(str(c), head_style) for c in cols]]
        status_values_by_cell = []

        for _, row in chunk.iterrows():
            pdf_row = []
            status_row = []
            for c in cols:
                raw_value = str(row[c])
                if c not in ["Tienda", "% Cumplimiento"]:
                    pdf_row.append(pdf_status_icon(raw_value))
                else:
                    pdf_row.append(Paragraph(str(row[c]), cell_style))
                status_row.append(raw_value)
            data.append(pdf_row)
            status_values_by_cell.append(status_row)

        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        commands = [
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2F67A8")),
            ("BACKGROUND", (0,0), (0,0), colors.HexColor("#A6A6A6")),
            ("BACKGROUND", (-1,0), (-1,0), colors.HexColor("#A6A6A6")),
            ("GRID", (0,0), (-1,-1), 0.65, colors.HexColor("#1B1B1B")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]

        semaforo_text = {
            "OK": colors.HexColor("#2CA25F"),
            "NO": colors.HexColor("#E31A1C"),
            "PEND": colors.HexColor("#F39C12"),
            "N/A": colors.HexColor("#6B7280"),
            "": colors.HexColor("#B8B8B8"),
        }
        semaforo_bg = {
            "OK": colors.HexColor("#E9F7EF"),
            "NO": colors.HexColor("#FDECEC"),
            "PEND": colors.HexColor("#FFF7D6"),
            "N/A": colors.HexColor("#F1F3F5"),
            "": None,
        }

        for ridx in range(1, len(data)):
            commands.append(("BACKGROUND", (0,ridx), (-1,ridx), colors.HexColor("#D9E8F6") if ridx % 2 == 0 else colors.white))

            for cidx, raw_value in enumerate(status_values_by_cell[ridx - 1]):
                col_name = cols[cidx]

                if col_name not in ["Tienda", "% Cumplimiento"]:
                    commands.append(("TEXTCOLOR", (cidx, ridx), (cidx, ridx), semaforo_text.get(raw_value, colors.black)))
                    bg_status = semaforo_bg.get(raw_value)
                    if bg_status is not None:
                        commands.append(("BACKGROUND", (cidx, ridx), (cidx, ridx), bg_status))

                if col_name == "% Cumplimiento":
                    try:
                        pct_value = float(str(raw_value).replace("%", ""))
                    except Exception:
                        pct_value = 0
                    if pct_value >= 90:
                        commands.append(("TEXTCOLOR", (cidx, ridx), (cidx, ridx), colors.HexColor("#2CA25F")))
                    elif pct_value >= 70:
                        commands.append(("TEXTCOLOR", (cidx, ridx), (cidx, ridx), colors.HexColor("#F39C12")))
                    else:
                        commands.append(("TEXTCOLOR", (cidx, ridx), (cidx, ridx), colors.HexColor("#E31A1C")))

        tbl.setStyle(TableStyle(commands))
        elements.append(tbl)

    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer


def safe_filename(value: str) -> str:
    """Limpia texto para usarlo como nombre de archivo."""
    value = str(value or "").strip()
    replacements = {
        "/": "-", "\\": "-", ":": "-", "*": "", "?": "", '"': "",
        "<": "", ">": "", "|": "", " ": "_"
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value or "SIN_DATO"


def make_zip_by_store(evidencias: pd.DataFrame, semana_zip: str = "") -> BytesIO:
    """Genera un ZIP con una sola carpeta de evidencias y el concentrado general.
    Cada imagen/archivo incluye fecha, tienda, actividad e ID en el nombre.
    """
    buffer = BytesIO()
    carpeta = safe_filename(f"ES_Check_List_Evidencias_{semana_zip}" if semana_zip else "ES_Check_List_Evidencias")
    with ZipFile(buffer, "w") as zip_file:
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            evidencias.to_excel(writer, sheet_name="Concentrado", index=False)
            resumen = (
                evidencias.groupby(["Semana", "Tienda", "Concepto", "Estatus"], dropna=False)
                .size()
                .reset_index(name="Total")
                if not evidencias.empty else pd.DataFrame(columns=["Semana", "Tienda", "Concepto", "Estatus", "Total"])
            )
            resumen.to_excel(writer, sheet_name="Resumen", index=False)
        zip_file.writestr(f"{carpeta}/Concentrado_Evidencias.xlsx", excel_buffer.getvalue())

        for _, row in evidencias.iterrows():
            archivo = str(row.get("Archivo", ""))
            if archivo and Path(archivo).exists():
                ext = Path(archivo).suffix or ".jpg"
                fecha = safe_filename(str(row.get("Fecha_Carga", "SIN_FECHA"))[:19])
                tienda = safe_filename(row.get("Tienda", "SIN_TIENDA"))
                concepto = safe_filename(row.get("Concepto", "SIN_ACTIVIDAD"))
                estatus = safe_filename(row.get("Estatus", "SIN_ESTATUS"))
                evidence_id = safe_filename(row.get("ID", Path(archivo).stem))
                zip_name = f"{carpeta}/{fecha}_{tienda}_{concepto}_{estatus}_{evidence_id}{ext}"
                zip_file.write(archivo, zip_name)
    buffer.seek(0)
    return buffer


def make_activity_control(evidencias: pd.DataFrame, config: pd.DataFrame, semana: str, manual: pd.DataFrame | None = None) -> pd.DataFrame:
    """Concentrado general por tienda y actividad con cumplimiento de cada punto."""
    conceptos = config[config["Activo"] == True]["Concepto"].tolist()
    ev_sem = evidencias[evidencias["Semana"].astype(str) == str(semana)] if semana != "Todas" else evidencias.copy()
    manual = manual if manual is not None else pd.DataFrame(columns=["Semana", "Tienda", "Concepto", "Estatus_Manual"])
    man_sem = manual[manual["Semana"].astype(str) == str(semana)] if semana != "Todas" else manual.copy()
    rows = []
    for tienda in TIENDAS_DEFAULT:
        for concepto in conceptos:
            ev = ev_sem[(ev_sem["Tienda"] == tienda) & (ev_sem["Concepto"] == concepto)]
            man = man_sem[(man_sem["Tienda"] == tienda) & (man_sem["Concepto"] == concepto)]
            manual_status = man["Estatus_Manual"].iloc[-1] if not man.empty else ""
            aceptadas = int((ev["Estatus"] == "Aceptada").sum()) if not ev.empty else 0
            rechazadas = int((ev["Estatus"] == "Rechazada").sum()) if not ev.empty else 0
            pendientes = int((ev["Estatus"] == "Pendiente").sum()) if not ev.empty else 0
            total = int(len(ev))
            if manual_status == "N/A":
                estatus_final = "N/A"
                cumplimiento = "N/A"
            elif manual_status == "Aceptada" or aceptadas > 0:
                estatus_final = "Cumple"
                cumplimiento = "100%"
            elif manual_status == "Rechazada" or rechazadas > 0:
                estatus_final = "No cumple"
                cumplimiento = "0%"
            elif manual_status == "Pendiente" or pendientes > 0:
                estatus_final = "Pendiente"
                cumplimiento = "0%"
            else:
                estatus_final = "Sin evidencia"
                cumplimiento = "0%"
            rows.append({
                "Semana": semana,
                "Tienda": tienda,
                "Actividad": concepto,
                "Estatus final": estatus_final,
                "% Cumplimiento actividad": cumplimiento,
                "Evidencias cargadas": total,
                "Aceptadas": aceptadas,
                "Pendientes": pendientes,
                "Rechazadas": rechazadas,
                "Marcación manual admin": manual_status,
            })
    return pd.DataFrame(rows)



def make_activity_kpis(matrix_df: pd.DataFrame, conceptos: list[str]) -> pd.DataFrame:
    """Calcula el porcentaje de cumplimiento por cada actividad/columna activa."""
    rows = []
    for concepto in conceptos:
        if concepto not in matrix_df.columns:
            continue
        serie = matrix_df[concepto].astype(str)
        requeridos = int((serie != "N/A").sum())
        aceptados = int((serie == "OK").sum())
        pendientes = int((serie == "PEND").sum())
        rechazados = int((serie == "NO").sum())
        na = int((serie == "N/A").sum())
        pct = round((aceptados / requeridos * 100), 0) if requeridos else 0
        rows.append({
            "Actividad": concepto,
            "% Cumplimiento": pct,
            "Aceptadas": aceptados,
            "Pendientes": pendientes,
            "Rechazadas": rechazados,
            "N/A": na,
            "Requeridas": requeridos,
        })
    return pd.DataFrame(rows)


def render_activity_cards(activity_df: pd.DataFrame) -> str:
    """Tarjetas superiores enlazadas a los encabezados activos del checklist."""
    if activity_df.empty:
        return "<div class='activity-wrap'><div class='activity-card'><div class='activity-title'>Sin actividades activas</div><div class='activity-number'>0%</div></div></div>"

    parts = ["<div class='activity-wrap'>"]
    for _, row in activity_df.iterrows():
        pct = float(row["% Cumplimiento"])
        cls = "good" if pct >= 90 else "mid" if pct >= 70 else "bad"
        actividad = html.escape(str(row["Actividad"]))
        aceptadas = int(row["Aceptadas"])
        requeridas = int(row["Requeridas"])
        width_pct = max(0, min(100, pct))
        parts.append(
            f"<div class='activity-card {cls}'>"
            f"<div class='activity-title'>{actividad}</div>"
            f"<div class='activity-number'>{pct:.0f}%</div>"
            f"<div class='activity-label'>Cumplimiento</div>"
            f"<div class='activity-bar'><span style='width:{width_pct:.0f}%'></span></div>"
            f"<div class='activity-foot'>{pct:.0f}% cumplimiento actividad · {aceptadas} / {requeridas} aceptadas</div>"
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)

def wrap_text_to_width(draw, text: str, font, max_width: int):
    """Divide texto en líneas para que sí se vea completo en la imagen PNG."""
    words = str(text).split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        test = word if not current else current + " " + word
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:3]


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
:root{
    --ps-blue:#00508C;
    --ps-dark:#202235;
    --ps-pink:#E6007E;
    --soft-blue:#D9E8F6;
}
.block-container{
    padding-top:1.4rem;
    max-width:98%;
}
.corp-header{
    background:#fff;
    border-radius:0 0 16px 16px;
    box-shadow:0 2px 12px rgba(0,0,0,.07);
    border:1px solid #eef1f7;
    margin:8px 0 24px 0;
    overflow:visible;
}
.corp-top{
    display:flex;
    align-items:center;
    justify-content:space-between;
    min-height:118px;
    padding:20px 28px 16px 28px;
}
.corp-logo{
    height:86px;
    max-width:220px;
    object-fit:contain;
    display:block;
}
.corp-title{
    font-size:32px;
    font-weight:900;
    color:#202235;
    text-align:right;
    line-height:1.2;
    margin-top:4px;
}
.corp-subtitle{
    font-size:16px;
    color:#6b7080;
    text-align:right;
    margin-top:10px;
}
.corp-bar{
    background:#E6007E;
    color:#fff;
    font-size:22px;
    font-weight:900;
    padding:10px 28px;
    border-radius:0 0 14px 14px;
}
.activity-wrap{display:flex;gap:14px;overflow-x:auto;padding:8px 0 14px 0;}
.activity-card{min-width:245px;background:#f7f9ff;border-radius:14px;padding:16px;border-left:7px solid #3366CC;box-shadow:0 2px 8px rgba(0,0,0,.06);}
.activity-card.good{border-left-color:#2ca25f}.activity-card.mid{border-left-color:#f39c12}.activity-card.bad{border-left-color:#e31a1c}
.activity-title{font-size:14px;font-weight:900;color:#2f3142;white-space:normal;min-height:34px;}
.activity-number{font-size:34px;font-weight:900;color:#3366CC;margin-top:8px;}
.activity-card.good .activity-number{color:#2ca25f}.activity-card.mid .activity-number{color:#f39c12}.activity-card.bad .activity-number{color:#e31a1c}
.activity-label{font-size:12px;color:#666;margin-top:2px}.activity-foot{font-size:12px;color:#555;margin-top:8px;}
.activity-bar{height:8px;background:#e4e6ef;border-radius:999px;margin-top:10px;overflow:hidden}.activity-bar span{display:block;height:100%;background:#3366CC;border-radius:999px;}
.activity-card.good .activity-bar span{background:#2ca25f}.activity-card.mid .activity-bar span{background:#f39c12}.activity-card.bad .activity-bar span{background:#e31a1c}
.portal-table{border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:15px;}
.portal-table th{background:#2f67a8;color:white;padding:8px;border:1px solid #1b1b1b;text-align:center;font-weight:800;}
.portal-table th:first-child,.portal-table th:last-child{background:#a6a6a6;color:white;}
.portal-table td{border:1px solid #1b1b1b;padding:7px;text-align:center;font-weight:700;}
.portal-table tr:nth-child(even) td{background:#d9e8f6;}
.portal-table tr:nth-child(odd) td{background:#ffffff;}
.portal-table td:first-child{font-weight:900;}
.dot{height:18px;width:18px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:middle;border:1px solid rgba(0,0,0,.25);}
.green{background:#69ad93}.red{background:#e85b35}.amber{background:#c58b4a}.gray{background:#9a9a9a}.blank{background:#ffffff}
/* Hace que la matriz editable conserve aspecto de casilla visual */
div[data-testid="stDataFrame"] div[role="gridcell"]{
    font-size:24px !important;
    text-align:center !important;
}
div[data-testid="stDataFrame"] div[role="columnheader"]{
    font-weight:900 !important;
}
</style>
""", unsafe_allow_html=True)

def render_corporate_header():
    logo_html = "<strong style='font-size:22px;color:#00508C;'>Price Shoes</strong>"
    try:
        if PRICE_LOGO.exists():
            logo_b64 = base64.b64encode(PRICE_LOGO.read_bytes()).decode("utf-8")
            logo_html = f'<img class="corp-logo" src="data:image/png;base64,{logo_b64}" />'
    except Exception:
        pass

    st.markdown(f"""
    <div class="corp-header">
      <div class="corp-top">
        <div>{logo_html}</div>
        <div>
          <div class="corp-title">ES Check List Evidencias</div>
          <div class="corp-subtitle">Matriz de cumplimiento por actividad</div>
        </div>
      </div>
      <div class="corp-bar">Corporativo · Producto Ropa</div>
    </div>
    """, unsafe_allow_html=True)

render_corporate_header()


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
    semana = st.text_input("Semana", value=f"SEM {now_mx().isocalendar().week}")

active_concepts = config[config["Activo"] == True]["Concepto"].tolist()

# KPIs por actividad
matrix = calculate_matrix(evidencias, config, semana, manual)
activity_kpis = make_activity_kpis(matrix, active_concepts)
st.markdown("### % de cumplimiento por actividad")
st.markdown(render_activity_cards(activity_kpis), unsafe_allow_html=True)

st.divider()

if is_admin:
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Checklist General",
        "📤 Cargar Evidencias",
        "🛡️ Validación Admin",
        "⚙️ Configuración"
    ])
else:
    tab1, tab2 = st.tabs([
        "📋 Checklist General",
        "📤 Cargar Evidencias"
    ])
    tab3 = tab4 = None

with tab1:
    st.subheader("Checklist de cumplimiento")
    st.caption("Administrador: selecciona una casilla para desplegar el menú de estatus. Tienda: visualiza el cumplimiento general.")

    if is_admin and active_concepts:
        editor_df_top = matrix_to_admin_editor(matrix, active_concepts)
        status_options = ["", "!", "✓", "✕", "N/A"]
        edited_matrix_top = st.data_editor(
            editor_df_top,
            width="stretch",
            hide_index=True,
            disabled=["Tienda", "% Cumplimiento"],
            key=f"editor_checklist_principal_{semana}",
            column_config={
                "Tienda": st.column_config.TextColumn("Tienda"),
                "% Cumplimiento": st.column_config.TextColumn("% Cumplimiento"),
                **{
                    concepto: st.column_config.SelectboxColumn(
                        concepto,
                        options=status_options,
                        required=True,
                    )
                    for concepto in active_concepts
                }
            }
        )

        st.caption("Leyenda: vacío = Sin marcar · ! = Pendiente · ✓ = Aceptada · ✕ = Rechazada · N/A = No aplica")

        if st.button("Guardar cambios de la matriz principal", type="primary", key=f"guardar_matriz_principal_{semana}"):
            manual_new = save_admin_editor_to_manual(edited_matrix_top, manual, semana, active_concepts)
            save_df(manual_new, MANUAL_FILE)
            st.success("Matriz actualizada correctamente.")
            st.rerun()
    else:
        st.markdown(render_portal_table(matrix), unsafe_allow_html=True)

    try:
        pdf_buffer = make_matrix_pdf(matrix, f"ES Check List Evidencias | {semana}")
        st.download_button(
            "📄 Descargar checklist como PDF",
            data=pdf_buffer.getvalue(),
            file_name=f"ES_Check_List_Evidencias_{semana}.pdf".replace(" ", "_"),
            mime="application/pdf"
        )
    except Exception as e:
        st.warning(f"No fue posible generar el PDF: {e}")

    if is_admin:
        st.divider()
        if not active_concepts:
            st.info("No hay encabezados activos en el checklist.")
        else:
            st.markdown("**Acción rápida por tiendas**")
            st.caption("Selecciona una o varias tiendas y marca todas sus actividades activas en un solo paso. Esto también actualiza el checklist general y sus porcentajes.")
            col_store, col_status, col_apply = st.columns([3, 2, 2])
            with col_store:
                seleccionar_todas = st.checkbox(
                    "Seleccionar todas las tiendas",
                    value=False,
                    key=f"seleccionar_todas_tiendas_{semana}"
                )

                if seleccionar_todas:
                    tiendas_masivas = TIENDAS_DEFAULT.copy()
                    st.success(f"{len(tiendas_masivas)} tiendas seleccionadas")
                else:
                    tiendas_masivas = st.multiselect(
                        "Tiendas",
                        TIENDAS_DEFAULT,
                        placeholder="Selecciona una o varias tiendas",
                        key=f"tiendas_masivas_{semana}"
                    )

            with col_status:
                estatus_masivo = st.selectbox(
                    "Marcar todas las actividades como",
                    ["Aceptada", "Pendiente", "Rechazada", "N/A", "Sin marcar"],
                    key=f"estatus_masivo_{semana}"
                )
            with col_apply:
                st.write("")
                st.write("")
                aplicar_masivo = st.button(
                    "Aplicar a tiendas seleccionadas",
                    type="primary",
                    key=f"aplicar_tiendas_{semana}"
                )

            if aplicar_masivo:
                if not tiendas_masivas:
                    st.warning("Selecciona al menos una tienda.")
                else:
                    manual_new = manual.copy()
                    estatus_guardar = "" if estatus_masivo == "Sin marcar" else estatus_masivo
                    total_actividades = 0

                    for tienda_masiva in tiendas_masivas:
                        for concepto_masivo in active_concepts:
                            manual_new = upsert_manual(
                                manual_new,
                                semana,
                                tienda_masiva,
                                concepto_masivo,
                                estatus_guardar,
                                f"Marcación masiva por tiendas: {estatus_masivo}"
                            )
                            total_actividades += 1

                    save_df(manual_new, MANUAL_FILE)
                    st.success(
                        f"Se actualizaron {len(tiendas_masivas)} tiendas "
                        f"({total_actividades} actividades) como {estatus_masivo}."
                    )
                    st.rerun()

            st.divider()
            st.markdown("**Menú detallado por punto seleccionado**")
            st.caption("Además de la tabla, puedes seleccionar tienda y actividad para ver evidencias ligadas y agregar comentario del administrador.")
            tienda_filtro_punto = st.selectbox("Tienda a revisar", TIENDAS_DEFAULT, key="tienda_filtro_punto")
            selected_concept = st.selectbox("Punto del checklist", active_concepts, key="selected_check_point_admin")

            man_row = manual[
                (manual["Semana"].astype(str) == str(semana))
                & (manual["Tienda"] == tienda_filtro_punto)
                & (manual["Concepto"] == selected_concept)
            ]
            current_status = man_row["Estatus_Manual"].iloc[-1] if not man_row.empty else ""
            current_comment = man_row["Comentario_Admin"].iloc[-1] if not man_row.empty else ""
            ev_subset = evidencias[
                (evidencias["Semana"].astype(str) == str(semana))
                & (evidencias["Tienda"] == tienda_filtro_punto)
                & (evidencias["Concepto"] == selected_concept)
            ]

            left_menu, right_evidence = st.columns([1, 2])
            with left_menu:
                opciones = ["Sin marcar", "Pendiente", "Aceptada", "Rechazada", "N/A"]
                visible_status = current_status if current_status else "Sin marcar"
                idx_default = opciones.index(visible_status) if visible_status in opciones else 0
                accion = st.radio("Qué quieres marcar en este punto", opciones, index=idx_default, key=f"accion_detalle_{tienda_filtro_punto}_{selected_concept}")
                comentario_punto = st.text_area("Comentario del administrador", value=str(current_comment) if str(current_comment) != "nan" else "", key=f"comentario_detalle_{tienda_filtro_punto}_{selected_concept}")
                if st.button("Guardar punto seleccionado", type="secondary", key=f"guardar_detalle_{tienda_filtro_punto}_{selected_concept}"):
                    manual_status = "" if accion == "Sin marcar" else accion
                    manual_new = upsert_manual(manual, semana, tienda_filtro_punto, selected_concept, manual_status, comentario_punto)
                    save_df(manual_new, MANUAL_FILE)
                    st.success("Punto actualizado.")
                    st.rerun()
            with right_evidence:
                st.markdown("**Evidencias ligadas a este punto**")
                if not ev_subset.empty:
                    st.dataframe(ev_subset[["ID", "Estatus", "Responsable", "Fecha_Carga", "Comentario_Tienda"]], width="stretch", hide_index=True)
                else:
                    st.info("Sin evidencias cargadas para este punto.")

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

                st.info("Las evidencias son confidenciales y se guardan únicamente dentro de este ORION. No se usan en otros sitios ni para otros fines.")
                fuente = st.radio(
                    "Origen de la evidencia",
                    ["Seleccionar desde galería / archivo", "Tomar foto con cámara"],
                    horizontal=True,
                    key=f"fuente_{tienda}_{concepto}"
                )
                camera_file = None
                gallery_files = []
                if fuente == "Tomar foto con cámara":
                    st.markdown("**Cámara activa únicamente para tomar foto**")
                    camera_file = st.camera_input(
                        "Tomar foto",
                        key=f"camara_{tienda}_{concepto}"
                    )
                else:
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
                            ext = Path(original_name).suffix or ".jpg"
                            fecha_nombre = now_mx().strftime("%Y-%m-%d_%H-%M-%S")
                            safe_name = f"{fecha_nombre}_{safe_filename(tienda)}_{safe_filename(concepto)}_{evidence_id}{ext}"
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
                                "Fecha_Carga": now_mx().strftime("%Y-%m-%d %H:%M:%S"),
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

if is_admin:
    with tab3:
        st.subheader("Control general de evidencias")
        control_df = make_activity_control(evidencias, config, semana, manual)
        st.caption("Concentrado general por tienda y actividad. Aquí se ve el cumplimiento de cada actividad del checklist.")
        st.dataframe(control_df, width="stretch", hide_index=True)

        control_excel = BytesIO()
        control_df.to_excel(control_excel, index=False, engine="openpyxl")
        st.download_button(
            "⬇️ Descargar control general por actividad",
            data=control_excel.getvalue(),
            file_name=f"Control_General_Evidencias_{semana}.xlsx".replace(" ", "_"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.divider()
        st.subheader("Validación individual de evidencias")
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
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = now_mx().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if b.button("Rechazar", key=f"rechazar_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Rechazada"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = now_mx().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()
                    if c.button("Pendiente", key=f"pendiente_{row['ID']}"):
                        evidencias.loc[evidencias["ID"] == row["ID"], "Estatus"] = "Pendiente"
                        evidencias.loc[evidencias["ID"] == row["ID"], "Comentario_Admin"] = comentario_admin
                        evidencias.loc[evidencias["ID"] == row["ID"], "Fecha_Revision"] = now_mx().strftime("%Y-%m-%d %H:%M:%S")
                        save_df(evidencias, EVIDENCE_FILE)
                        st.rerun()

        st.divider()
        st.subheader("Descarga de concentrado")
        zip_buffer = make_zip_by_store(evidencias, semana)
        st.download_button(
            "⬇️ Descargar evidencias por tienda ZIP",
            data=zip_buffer,
            file_name=f"ES_Check_List_Evidencias_{semana}.zip",
            mime="application/zip"
        )

if is_admin:
    with tab4:
        st.subheader("Configuración del checklist")
        st.caption("Edita los encabezados del checklist. Cada encabezado será un concepto obligatorio para cargar evidencias.")

        st.markdown("### Eliminar columna / actividad")
        if config.empty:
            st.info("No hay columnas configuradas para eliminar.")
        else:
            col_del_1, col_del_2 = st.columns([3, 1])
            with col_del_1:
                columna_eliminar = st.selectbox("Selecciona la columna que deseas eliminar", config["Concepto"].astype(str).tolist(), key="columna_eliminar_config")
            with col_del_2:
                st.write("")
                st.write("")
                if st.button("🗑️ Eliminar columna", type="secondary"):
                    config_new = config[config["Concepto"].astype(str) != str(columna_eliminar)].copy()
                    save_df(config_new, CONFIG_FILE)
                    manual_new = manual[manual["Concepto"].astype(str) != str(columna_eliminar)].copy()
                    save_df(manual_new, MANUAL_FILE)
                    st.success(f"Columna eliminada: {columna_eliminar}")
                    st.rerun()
            st.warning("Al eliminar una columna, dejará de aparecer en el checklist general. Las evidencias históricas cargadas se conservan en el archivo de evidencias.")

        st.divider()
        st.markdown("### Agregar o editar columnas")
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
