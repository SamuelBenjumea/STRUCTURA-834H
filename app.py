"""Structura 834H - panel de integridad estructural de la hoja topadora."""
from pathlib import Path
from datetime import date, datetime
import sqlite3
import uuid
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from inteligencia import estudiar_punto, informe_punto, pdf_informe

ROOT = Path(__file__).parent
XLSX = ROOT / '834H_historial_grietas.xlsx'
DB = ROOT / 'inspecciones_nuevas.db'
CODES = ['HT-01', 'HT-02', 'HT-03', 'HT-04']
COLORS = {'Normal': '#1cbb88', 'Alerta': '#f6b745', 'Crítico': '#ef6175', 'N/I': '#8fa0b6'}

st.set_page_config(page_title='STRUCTURA | CAT 834H', page_icon='🛠️', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp{background:#0b1220;color:#e9f0ff}
[data-testid="stSidebar"]{background:#111c2e}
[data-testid="stMetric"]{background:#17253b;border:1px solid #2c3e59;border-radius:14px;padding:16px}
h1,h2,h3{letter-spacing:-.025em}
[data-testid="stDataFrame"]{border:1px solid #2b3b52;border-radius:10px}
</style>''', unsafe_allow_html=True)

def tabla_legible(df):
    """Formatea únicamente la tabla mostrada; no modifica los datos del análisis."""
    resultado = df.copy()
    if 'Fecha' in resultado.columns:
        fechas = pd.to_datetime(resultado['Fecha'], errors='coerce')
        resultado['Fecha'] = fechas.dt.strftime('%d/%m/%Y').fillna('Sin fecha')
    if 'Comentario' in resultado.columns:
        comentarios = resultado['Comentario'].astype('string').str.strip()
        comentarios = comentarios.replace({'': pd.NA, 'None': pd.NA, 'nan': pd.NA, 'NaN': pd.NA})
        resultado['Comentario'] = comentarios.fillna('Sin observaciones')
    return resultado

def status(length, caution, danger):
    if pd.isna(length): return 'N/I'
    if length >= danger: return 'Crítico'
    if length >= caution: return 'Alerta'
    return 'Normal'

@st.cache_data(show_spinner=False)
def load_excel(mtime):
    history = pd.read_excel(XLSX, sheet_name='Historial')
    points = pd.read_excel(XLSX, sheet_name='Puntos')
    history.columns = history.columns.str.strip()
    points.columns = points.columns.str.strip()
    history = history[history['Código'].isin(CODES)].copy()
    points = points[points['Código'].isin(CODES)].copy()
    history['Fecha'] = pd.to_datetime(history['Fecha'], errors='coerce')
    history['L actual (mm)'] = pd.to_numeric(history['L actual (mm)'], errors='coerce')
    history['Horas (h)'] = pd.to_numeric(history['Horas (h)'], errors='coerce')
    points['Caution (mm)'] = pd.to_numeric(points['Caution (mm)'], errors='coerce')
    points['Danger (mm)'] = pd.to_numeric(points['Danger (mm)'], errors='coerce')
    return history, points

def db_connection():
    con = sqlite3.connect(DB)
    con.execute('''CREATE TABLE IF NOT EXISTS inspecciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL, equipo TEXT NOT NULL, horas REAL NOT NULL,
        inspector TEXT NOT NULL, codigo TEXT NOT NULL,
        longitud REAL, comentario TEXT NOT NULL,
        UNIQUE(fecha, equipo, horas, codigo)
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS fotografias (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL, fecha TEXT NOT NULL, archivo TEXT NOT NULL, nombre_original TEXT NOT NULL)''')
    return con

def load_added():
    with db_connection() as con:
        extra = pd.read_sql_query('SELECT fecha,equipo,horas,inspector,codigo,longitud,comentario FROM inspecciones',con)
    if extra.empty:
        return pd.DataFrame(columns=['Fecha','Equipo','Horas (h)','Inspector','Zona','Código','Descripción','L actual (mm)','Comentario','Imagen','Fuente'])
    extra.columns = ['Fecha','Equipo','Horas (h)','Inspector','Código','L actual (mm)','Comentario']
    extra['Fecha'] = pd.to_datetime(extra['Fecha'])
    extra['Zona'] = 'Hoja topadora'
    extra['Descripción'] = ''
    extra['Imagen'] = ''
    extra['Fuente'] = 'Nueva inspección'
    return extra

if not XLSX.exists():
    st.error('No se encontró 834H_historial_grietas.xlsx junto a app.py.')
    st.stop()

base, points = load_excel(XLSX.stat().st_mtime)
fechas_invalidas = base[base['Fecha'] > pd.Timestamp.today() + pd.Timedelta(days=30)].copy()
base = base[base['Fecha'] <= pd.Timestamp.today() + pd.Timedelta(days=30)].copy()
base['Fuente'] = 'Excel original'
extra = load_added()
history = pd.concat([base,extra], ignore_index=True)
history = history.merge(points[['Código','Caution (mm)','Danger (mm)']],on='Código',how='left')
history = history.sort_values(['Código','Fecha','Horas (h)']).reset_index(drop=True)
history['Estado'] = history.apply(lambda r:status(r['L actual (mm)'],r['Caution (mm)'],r['Danger (mm)']),axis=1)
metadata = points.set_index('Código')
latest = history.dropna(subset=['Fecha']).groupby('Código',sort=False).tail(1).set_index('Código').reindex(CODES)

with st.sidebar:
    st.markdown('## ◈ STRUCTURA')
    st.caption('Integridad estructural | Equipo 834-01')
    view = st.radio('Navegación', ['Panel general','Tendencias y riesgos','Mapa e imágenes','Historial y filtros','Nueva inspección','Informe inteligente','Calidad de datos','Respaldo de datos'], label_visibility='collapsed')
    st.divider()
    selected = st.selectbox('Punto de interés',CODES,format_func=lambda c:f"{c} — {metadata.loc[c,'Descripción']}")
    st.caption('CAT 834H · Hoja topadora · 4 puntos')

st.title('CAT 834H  /  Hoja topadora')
st.caption('Plataforma de apoyo a decisiones de mantenimiento · Datos históricos + nuevas inspecciones registradas localmente')
if not fechas_invalidas.empty:
    st.caption(f'Control de calidad: {len(fechas_invalidas)} registros del Excel tienen fecha futura inverosímil (2042) y no se consideran para el estado actual ni las proyecciones; pueden revisarse en Calidad de datos.')

if view == 'Panel general':
    counts = latest['Estado'].value_counts()
    a,b,c,d=st.columns(4)
    a.metric('Puntos monitoreados',len(CODES))
    b.metric('En alerta',int(counts.get('Alerta',0)))
    c.metric('Críticos',int(counts.get('Crítico',0)))
    d.metric('Última inspección',latest['Fecha'].max().strftime('%d/%m/%Y'))
    st.subheader('Estado actual de los puntos')
    cols=st.columns(4)
    for col,code in zip(cols,CODES):
        r=latest.loc[code]
        col.markdown(f"**{code}**  · :{('green' if r['Estado']=='Normal' else 'orange' if r['Estado']=='Alerta' else 'red')}[{r['Estado']}]")
        col.metric('Longitud',f"{r['L actual (mm)']:g} mm" if pd.notna(r['L actual (mm)']) else 'N/I')
        col.caption(f"Caution {r['Caution (mm)']:g} mm  ·  Danger {r['Danger (mm)']:g} mm")
    st.divider()
    fig=go.Figure()
    fig.add_trace(go.Bar(x=CODES,y=[latest.loc[k,'L actual (mm)'] for k in CODES],name='Longitud actual',marker_color='#45b7ed'))
    fig.add_trace(go.Scatter(x=CODES,y=[metadata.loc[k,'Caution (mm)'] for k in CODES],name='Caution',mode='lines+markers',line=dict(color='#f6b745',dash='dash')))
    fig.add_trace(go.Scatter(x=CODES,y=[metadata.loc[k,'Danger (mm)'] for k in CODES],name='Danger',mode='lines+markers',line=dict(color='#ef6175',dash='dash')))
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b1220',plot_bgcolor='#0b1220',yaxis_title='Longitud de grieta (mm)',height=370)
    st.plotly_chart(fig,use_container_width=True)
    at_risk=latest[latest['Estado'].isin(['Alerta','Crítico'])]
    if not at_risk.empty:
        st.warning('Atención: '+', '.join(at_risk.index.tolist())+' supera(n) Caution. Aumentar frecuencia de inspección y planificar evaluación de reparación. Si se alcanza Danger, reparar antes de continuar operando (según formato IE-834).')
    st.info('Los estados son comparaciones con umbrales del formato. No sustituyen una evaluación estructural o de seguridad.')

elif view == 'Tendencias y riesgos':
    st.subheader(f'Tendencia de {selected}')
    segment=history[history['Código']==selected].sort_values(['Fecha','Horas (h)']).copy()
    cau=float(metadata.loc[selected,'Caution (mm)']);dan=float(metadata.loc[selected,'Danger (mm)'])
    ax=st.radio('Eje horizontal',['Fecha','Horas (h)'],horizontal=True)
    valid=segment.dropna(subset=[ax,'L actual (mm)'])
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=valid[ax],y=valid['L actual (mm)'],mode='lines+markers',name='Mediciones',line=dict(color='#49b8f5',width=3),marker=dict(size=8),customdata=valid[['Comentario']].fillna('').to_numpy(),hovertemplate='%{x}<br>%{y:.1f} mm<br>%{customdata[0]}<extra></extra>'))
    fig.add_hline(y=cau,line_dash='dash',line_color='#f6b745',annotation_text='Caution')
    fig.add_hline(y=dan,line_dash='dash',line_color='#ef6175',annotation_text='Danger')
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b1220',plot_bgcolor='#0b1220',height=460,yaxis_title='Longitud (mm)',xaxis_title=ax)
    st.plotly_chart(fig,use_container_width=True)
    last=valid.iloc[-1]
    st.write(f"**Último estado:** {status(last['L actual (mm)'],cau,dan)} — {last['L actual (mm)']:g} mm el {last['Fecha']:%d/%m/%Y}.")
    # No inferir propagación continua a través de reparaciones ni descensos de medida.
    dif=valid['L actual (mm)'].diff()
    interruptions=valid[(dif < 0) | valid['Comentario'].fillna('').str.contains('soldadura|reparaci',case=False,regex=True)]
    if not interruptions.empty:
        st.warning('El historial tiene descensos de medición y/o menciones de reparación. No se extrapolan tendencias a través de esos eventos. Revisa los comentarios.')
    clean=valid.copy()
    # Segmentar tras el último descenso o reparación.
    interrupts=clean.index[((clean['L actual (mm)'].diff()<0) | clean['Comentario'].fillna('').str.contains('soldadura|reparaci',case=False,regex=True))]
    if len(interrupts):
        clean=clean.loc[interrupts[-1]:]
    if len(clean)>=3 and clean['Horas (h)'].nunique()>=3:
        xs=clean['Horas (h)'].to_numpy(dtype=float)
        ys=clean['L actual (mm)'].to_numpy(dtype=float)
        slope=np.polyfit(xs-xs[0],ys,1)[0]
        st.metric('Tendencia lineal del tramo reciente',f'{slope:.4f} mm/h')
        if slope>0 and pd.notna(last['Horas (h)']):
            remaining=max(0,(dan-float(last['L actual (mm)']))/slope)
            st.info(f'Proyección exploratoria a Danger: ~{remaining:,.0f} horas de operación, si se mantiene la tasa lineal reciente. No constituye una fecha límite segura ni una predicción validada.')
        else:st.info('No se proyecta cruce de Danger: la pendiente del tramo no es positiva.')
    else:st.info('No hay suficientes mediciones comparables en el tramo reciente para estimar una tendencia.')
    st.dataframe(tabla_legible(segment[['Fecha','Horas (h)','L actual (mm)','Estado','Comentario','Fuente']].sort_values('Fecha',ascending=False)),hide_index=True,use_container_width=True)

elif view == 'Mapa e imágenes':
    st.subheader('Ubicación de inspección — hoja topadora')
    st.image(str(ROOT/'assets/esquema_hoja.png'),caption='Esquema tomado del formato IE-834, página 3',use_container_width=True)
    st.image(str(ROOT/'assets/foto_hoja.jpg'),caption='Fotografía general de la hoja topadora tomada del formato IE-834',width=680)
    st.markdown(f"**Punto seleccionado: {selected}** — {metadata.loc[selected,'Descripción']}")
    st.info('La fotografía suministrada es una vista general, no evidencia individual de cada grieta.')
    with db_connection() as con:
        fotos=pd.read_sql_query('SELECT fecha,archivo,nombre_original FROM fotografias WHERE codigo=? ORDER BY fecha DESC',con,params=(selected,))
    if not fotos.empty:
        st.subheader('Fotografías registradas para ' + selected)
        for _,f in fotos.iterrows():
            ruta=ROOT/'assets'/'inspecciones'/f['archivo']
            if ruta.exists(): st.image(str(ruta),caption=f"{selected} · {f['fecha']} · {f['nombre_original']}",width=580)


elif view == 'Historial y filtros':
    st.subheader('Consulta de inspecciones')
    codes=st.multiselect('Puntos',CODES,default=CODES)
    min_d=history['Fecha'].min().date();max_d=history['Fecha'].max().date()
    dates=st.date_input('Rango de fechas',(min_d,max_d),min_value=min_d,max_value=max_d)
    subset=history[history['Código'].isin(codes)].copy()
    if isinstance(dates,(list,tuple)) and len(dates)==2:
        subset=subset[(subset['Fecha'].dt.date>=dates[0])&(subset['Fecha'].dt.date<=dates[1])]
    choices=st.multiselect('Estado',['Normal','Alerta','Crítico','N/I'],default=['Normal','Alerta','Crítico','N/I'])
    subset=subset[subset['Estado'].isin(choices)]
    subset=subset.sort_values(['Fecha','Código'],ascending=[False,True])
    st.metric('Registros filtrados',len(subset))
    display_cols=['Fecha','Horas (h)','Código','L actual (mm)','Caution (mm)','Danger (mm)','Estado','Comentario','Fuente']
    st.dataframe(tabla_legible(subset[display_cols]),hide_index=True,use_container_width=True)
    st.download_button('Descargar registros filtrados (CSV)',data=subset[display_cols].to_csv(index=False).encode('utf-8-sig'),file_name='834H_hoja_historial.csv',mime='text/csv')

elif view == 'Nueva inspección':
    st.subheader('Registrar nueva inspección')
    st.caption('Esta funcionalidad guarda datos nuevos en una base SQLite local; nunca modifica el Excel original.')
    with st.form('form_inspection',clear_on_submit=False):
        a,b=st.columns(2)
        day=a.date_input('Fecha',value=date.today())
        hrs=b.number_input('Horas de operación (h)',min_value=0.0,step=1.0,format='%.1f')
        code=a.selectbox('Punto',CODES)
        inspector=b.text_input('Inspector',value='INSP-01')
        inspected=st.checkbox('Punto inspeccionado',value=True)
        length=st.number_input('Longitud medida (mm)',min_value=0.0,step=1.0,disabled=not inspected)
        comment=st.text_area('Observaciones / reparaciones')
        photo=st.file_uploader('Fotografía del punto (opcional; JPG o PNG, máximo 5 MB)',type=['jpg','jpeg','png'])
        submit=st.form_submit_button('Guardar inspección',type='primary')
    if submit:
        if not inspector.strip(): st.error('Debes indicar el inspector.')
        elif hrs < float(history['Horas (h)'].max()):
            st.error('Las horas son inferiores al último registro disponible. Verifica el horómetro antes de continuar.')
        elif pd.Timestamp(day)<history['Fecha'].max():
            st.error('La fecha es anterior a la última inspección. Esta versión permite registrar inspecciones posteriores.')
        elif photo is not None and photo.size>5*1024*1024: st.error('La imagen excede 5 MB.')
        else:
            try:
                with db_connection() as con:
                    con.execute('INSERT INTO inspecciones (fecha,equipo,horas,inspector,codigo,longitud,comentario) VALUES (?,?,?,?,?,?,?)',
                        (day.isoformat(),'834-01',hrs,inspector.strip(),code,length if inspected else None,comment.strip()))
                if photo is not None:
                    folder=ROOT/'assets'/'inspecciones';folder.mkdir(parents=True,exist_ok=True)
                    extension=photo.name.rsplit('.',1)[-1].lower()
                    filename=uuid.uuid4().hex+'.'+extension
                    (folder/filename).write_bytes(photo.getvalue())
                    with db_connection() as con:
                        con.execute('INSERT INTO fotografias (codigo,fecha,archivo,nombre_original) VALUES (?,?,?,?)',(code,day.isoformat(),filename,photo.name))
                state=status(length if inspected else np.nan,float(metadata.loc[code,'Caution (mm)']),float(metadata.loc[code,'Danger (mm)']))
                st.success(f'Inspección guardada. Estado resultante de {code}: {state}.')
                st.rerun()
            except sqlite3.IntegrityError:st.error('Ya existe una inspección para ese punto, fecha y horas de operación.')
    st.info('Importante: registrar una reparación en observaciones no significa que la grieta fue eliminada. Registrar después la medición real.')

elif view == 'Informe inteligente':
    st.subheader('Informe automático de mantenimiento')
    st.caption('Análisis por reglas, basado en registros y umbrales. No utiliza un modelo generativo ni consulta servicios externos.')
    ranking = []
    for code in CODES:
        meta=metadata.loc[code]
        result=estudiar_punto(history[history['Código']==code],float(meta['Caution (mm)']),float(meta['Danger (mm)']))
        ranking.append({'Punto':code,'Estado':result['estado'],'Proximidad Danger (%)':round(result['porcentaje'],1) if result['porcentaje'] is not None else None,'Margen Danger (mm)':result['margen'],'Proyección (h)':None if result['horas_danger'] is None else round(result['horas_danger'])})
    st.dataframe(pd.DataFrame(ranking).sort_values('Proximidad Danger (%)',ascending=False),hide_index=True,use_container_width=True)
    for code in CODES:
        meta=metadata.loc[code]
        with st.expander(f"{code} · {meta['Descripción']}", expanded=code==selected):
            st.write(informe_punto(code,str(meta['Descripción']),history[history['Código']==code],float(meta['Caution (mm)']),float(meta['Danger (mm)'])))
    st.download_button('📄 Descargar informe completo en PDF', pdf_informe(history,points,latest),'Informe_STRUCTURA_834H.pdf',mime='application/pdf',use_container_width=True)
    st.info('La prioridad debe validarse con ingeniería y condiciones de operación. Una proyección lineal no establece tiempo seguro de operación.')

elif view == 'Respaldo de datos':
    st.subheader('Respaldo y portabilidad')
    st.write('Exporta el historial consolidado para compartirlo o archivarlo. El Excel original no se modifica.')
    st.download_button('Descargar historial completo (CSV)',history.to_csv(index=False).encode('utf-8-sig'),'structura_834H_historial_completo.csv','text/csv',use_container_width=True)
    if DB.exists():
        st.download_button('Descargar base de inspecciones nuevas (SQLite)', DB.read_bytes(),'inspecciones_nuevas.db','application/octet-stream',use_container_width=True)
    st.caption('Si cambias de computador, conserva el Excel, la carpeta assets y el archivo inspecciones_nuevas.db para no perder nuevas inspecciones.')

elif view == 'Calidad de datos':
    st.subheader('Auditoría del historial')
    st.caption('Reglas exploratorias; una disminución puede representar reparación, corrección o variación de medición.')
    raw=history.sort_values(['Código','Fecha','Horas (h)']).copy()
    raw['Cambio (mm)']=raw.groupby('Código')['L actual (mm)'].diff()
    raw['Cambio horas']=raw.groupby('Código')['Horas (h)'].diff()
    anomalies=raw[(raw['Cambio (mm)']<0)|(raw['Cambio horas']<0)|raw['Comentario'].fillna('').str.contains('soldadura|reparaci',case=False,regex=True)]
    st.metric('Eventos por revisar',len(anomalies))
    st.dataframe(tabla_legible(anomalies[['Código','Fecha','Horas (h)','L actual (mm)','Cambio (mm)','Comentario','Fuente']]),hide_index=True,use_container_width=True)
    st.markdown('**Criterios:** descensos en longitud, descensos de horómetro y menciones de reparación/soldadura. Revisar contexto antes de etiquetar como error.')
    if not fechas_invalidas.empty:
        st.error(f'{len(fechas_invalidas)} filas tienen una fecha futura incompatible con el resto del historial; se excluyeron del cálculo del estado actual.')
        st.dataframe(tabla_legible(fechas_invalidas[['Fecha','Código','Horas (h)','L actual (mm)','Comentario']]),hide_index=True,use_container_width=True)
