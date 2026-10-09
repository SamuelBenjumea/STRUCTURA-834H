"""Reglas transparentes de apoyo a mantenimiento, no diagnóstico estructural.
No envía datos a APIs externas. Las proyecciones son exploratorias.
"""
import io
import math
import re
from datetime import datetime
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

KEYWORDS = re.compile(r'reparaci[oó]n|soldadura|resane|interven', re.IGNORECASE)

def clasificar(longitud, caution, danger):
    if pd.isna(longitud): return 'N/I'
    if longitud >= danger: return 'Crítico'
    if longitud >= caution: return 'Alerta'
    return 'Normal'

def estudiar_punto(hist, caution, danger):
    """Segmenta series por reparaciones/caídas para no mezclar etapas.
    La regresión se calcula sobre las últimas mediciones del tramo actual.
    """
    h = hist.copy().sort_values(['Fecha','Horas (h)']).reset_index(drop=True)
    h['L actual (mm)'] = pd.to_numeric(h['L actual (mm)'], errors='coerce')
    h['Horas (h)'] = pd.to_numeric(h['Horas (h)'], errors='coerce')
    h['Comentario'] = h['Comentario'].fillna('').astype(str)
    valid = h.dropna(subset=['L actual (mm)','Horas (h)']).copy().reset_index(drop=True)
    if valid.empty:
        return dict(estado='N/I', longitud=None, porcentaje=None, margen=None, pendiente=None,
                    horas_danger=None, horas_caution=None, n=0, advertencias=['Sin mediciones válidas.'])
    cuts = (valid['L actual (mm)'].diff() < 0) | (valid['Horas (h)'].diff() <= 0) | valid['Comentario'].str.contains(KEYWORDS)
    idx = list(valid.index[cuts])
    tramo = valid.iloc[idx[-1]:] if idx else valid
    tramo = tramo.tail(8)
    last = valid.iloc[-1]
    current = float(last['L actual (mm)'])
    notes=[]
    if idx: notes.append('El historial presenta reparación, disminución de longitud o inconsistencia de horómetro; se reinicia el tramo analizado.')
    if current >= danger: notes.append('Límite Danger alcanzado: el formato IE-834 exige reparar antes de continuar operando.')
    elif current >= caution: notes.append('Superó Caution: aumentar frecuencia de inspección y programar reparación.')
    else: notes.append('Bajo Caution: mantener inspección según programa vigente.')
    slope = None
    if len(tramo) >= 3 and tramo['Horas (h)'].nunique() >= 3:
        x=tramo['Horas (h)'].to_numpy(dtype=float)
        y=tramo['L actual (mm)'].to_numpy(dtype=float)
        if np.ptp(x)>0:
            slope=float(np.polyfit(x-x[0],y,1)[0])
            if slope <= 0: notes.append('La tasa estimada no es positiva; no se calcula tiempo hasta Danger.')
    else: notes.append('Menos de tres registros comparables en el tramo actual; proyección no disponible.')
    def restante(lim):
        if current >= lim: return 0.0
        if slope is None or slope <= 0: return None
        value=(lim-current)/slope
        return float(value) if math.isfinite(value) else None
    return dict(estado=clasificar(current,caution,danger), longitud=current,
                porcentaje=current/danger*100, margen=danger-current, pendiente=slope,
                horas_danger=restante(danger), horas_caution=restante(caution),
                n=int(len(tramo)), advertencias=notes)

def informe_punto(codigo, descripcion, historial, caution, danger):
    r=estudiar_punto(historial,caution,danger)
    pct='N/D' if r['porcentaje'] is None else f"{r['porcentaje']:.1f}%"
    parts=[f"{codigo} — {descripcion}",f"Estado: {r['estado']}.",
           f"Longitud: {r['longitud'] if r['longitud'] is not None else 'N/I'} mm; Caution: {caution:g} mm; Danger: {danger:g} mm.",
           f"Ocupación relativa de Danger: {pct}."]
    if r['pendiente'] is not None:
        parts.append(f"Tendencia del último tramo: {r['pendiente']:.4f} mm/h, con {r['n']} registros comparables.")
    if r['horas_danger'] is not None and r['horas_danger']>0:
        parts.append(f"Cruce exploratorio de Danger en aproximadamente {r['horas_danger']:,.0f} horas adicionales SI la pendiente permanece constante; no es un plazo seguro ni una predicción validada.")
    parts += r['advertencias']
    return ' '.join(parts)

def pdf_informe(history, points, latest, equipo='834-01'):
    """Genera un informe automático reproducible en PDF sin servicios externos."""
    buf=io.BytesIO()
    document=SimpleDocTemplate(buf,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=42)
    ss=getSampleStyleSheet(); ss.add(ParagraphStyle(name='Accent834',parent=ss['Heading2'],textColor=colors.HexColor('#183c62'),spaceBefore=14))
    story=[Paragraph('STRUCTURA 834H | Informe de integridad estructural',ss['Title']),
           Paragraph(f'Equipo {equipo} · Zona: Hoja topadora · Emitido: {datetime.now():%d/%m/%Y %H:%M}',ss['Normal']),Spacer(1,16)]
    summary=[['Punto','Longitud (mm)','Caution','Danger','Estado']]
    for _,p in points.iterrows():
        code=p['Código']; last=latest.loc[code]
        length=last['L actual (mm)']
        summary.append([code,'N/I' if pd.isna(length) else f'{length:g}',f"{p['Caution (mm)']:g}",f"{p['Danger (mm)']:g}",str(last['Estado'])])
    t=Table(summary,colWidths=[76,104,87,87,105],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#183c62')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#edf4f8')]),('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#cbd5e1')),('BOTTOMPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9)]))
    story.extend([t,Spacer(1,18),Paragraph('Evaluación por punto',ss['Heading2'])])
    for _,p in points.iterrows():
        code=p['Código']; text=informe_punto(code,str(p['Descripción']),history[history['Código']==code],float(p['Caution (mm)']),float(p['Danger (mm)']))
        story.append(KeepTogether([Paragraph(code,ss['Accent834']),Paragraph(text.replace('&','&amp;').replace('<','&lt;'),ss['BodyText']),Spacer(1,8)]))
    story.extend([Spacer(1,16),Paragraph('Alcance y precauciones',ss['Heading2']),Paragraph('La clasificación se obtiene de los umbrales Caution y Danger indicados en el formato IE-834. Las estimaciones de crecimiento suponen linealidad local y no representan una evaluación de mecánica de fractura ni autorizan la operación. Validar datos, accesibilidad y reparaciones con mantenimiento e inspección.',ss['BodyText']),Spacer(1,9),Paragraph('Fuente: 834H_historial_grietas.xlsx y formato IE-834. Nuevas inspecciones locales, si existen, se incluyen en la fecha de emisión.',ss['BodyText'])])
    document.build(story)
    return buf.getvalue()
