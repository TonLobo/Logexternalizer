"""
Exportação de XMLs para CSV, PDF e XML formatado.
Usa fontes TTF do sistema (Arial + Consolas) para suporte completo a Unicode.
"""
import csv
import io
from datetime import datetime
from xml_parser import pretty_print_xml

# Fontes TTF disponíveis no Windows
_FONT_ARIAL    = r"C:\Windows\Fonts\arial.ttf"
_FONT_ARIAL_B  = r"C:\Windows\Fonts\arialbd.ttf"
_FONT_ARIAL_I  = r"C:\Windows\Fonts\ariali.ttf"
_FONT_MONO     = r"C:\Windows\Fonts\consola.ttf"   # Consolas — monoespaçada Unicode
_FONT_MONO_B   = r"C:\Windows\Fonts\consolab.ttf"


# ── CSV ────────────────────────────────────────────────────────────────────

def export_csv(rows: list[dict], columns: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore",
                            delimiter=";", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8-sig")   # BOM para Excel BR


# ── XML formatado ──────────────────────────────────────────────────────────

def export_xml_formatted(xml_content: str) -> bytes:
    formatted = pretty_print_xml(xml_content)
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    if formatted.lstrip().startswith("<?xml"):
        return formatted.encode("utf-8")
    return (header + formatted).encode("utf-8")


# ── PDF ────────────────────────────────────────────────────────────────────

def _build_pdf():
    """Cria instância FPDF com fontes Unicode registradas."""
    from fpdf import FPDF
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)

    pdf.add_font("Arial",    style="",  fname=_FONT_ARIAL)
    pdf.add_font("Arial",    style="B", fname=_FONT_ARIAL_B)
    pdf.add_font("Arial",    style="I", fname=_FONT_ARIAL_I)
    pdf.add_font("Consolas", style="",  fname=_FONT_MONO)
    pdf.add_font("Consolas", style="B", fname=_FONT_MONO_B)
    return pdf


def _write_header(pdf, titulo: str, subtitulo: str, tipo: str):
    pdf.set_font("Arial", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, titulo, new_x="LMARGIN", new_y="NEXT")

    if subtitulo:
        pdf.set_font("Arial", "", 9)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(0, 5, subtitulo, new_x="LMARGIN", new_y="NEXT")

    if tipo:
        badge_color = (29, 78, 216) if tipo == "request" else (6, 95, 70)
        pdf.set_fill_color(*badge_color)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 8)
        pdf.cell(24, 5, tipo.upper(), new_x="LMARGIN", new_y="NEXT", fill=True)

    pdf.set_text_color(30, 30, 30)
    pdf.ln(3)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(4)


def _write_xml_lines(pdf, formatted: str):
    pdf.set_font("Consolas", "", 7)
    pdf.set_text_color(20, 20, 20)
    for line in formatted.splitlines():
        line = line.replace("\t", "    ")
        try:
            pdf.cell(0, 3.5, line, new_x="LMARGIN", new_y="NEXT")
        except Exception:
            pdf.cell(0, 3.5, "[linha com caracteres não renderizáveis]",
                     new_x="LMARGIN", new_y="NEXT")


def _write_footer(pdf):
    pdf.set_y(-12)
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(150, 150, 150)
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.cell(0, 5, f"Gerado em {ts} - SAJ / Softplan", align="C")


def export_pdf(
    xml_content: str,
    titulo: str = "XML Log",
    subtitulo: str = "",
    tipo: str = "",
) -> bytes:
    """Gera PDF de um único XML (request ou response)."""
    pdf = _build_pdf()
    pdf.add_page()
    _write_header(pdf, titulo, subtitulo, tipo)
    _write_xml_lines(pdf, pretty_print_xml(xml_content))
    _write_footer(pdf)
    return bytes(pdf.output())


def export_pdf_par(
    xml_request: str | None,
    xml_response: str | None,
    titulo: str = "Log de Integração",
    subtitulo: str = "",
) -> bytes:
    """Gera PDF com request e response em páginas separadas."""
    pdf = _build_pdf()

    for tipo, xml_content in [("request", xml_request), ("response", xml_response)]:
        if not xml_content:
            continue
        pdf.add_page()
        _write_header(pdf, titulo, subtitulo, tipo)
        _write_xml_lines(pdf, pretty_print_xml(xml_content))
        _write_footer(pdf)

    return bytes(pdf.output())
