from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import psycopg2
import psycopg2.extras
import os
import requests
import openai
from fpdf import FPDF
import re

app = FastAPI(
    title="Tikatu API",
    description="API para monitoramento da qualidade da água e análise de IQA",
    version="1.0.0"
)

# Configuração do Supabase
#SUPABASE_URL = os.getenv("SUPABASE_URL")
#SUPABASE_KEY = os.getenv("SUPABASE_KEY")
#HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

SUPABASE_DB_URL = f"postgresql://postgres:{os.getenv('SUPABASE_TK_PWD')}@db.jxbsqnkdtdmshfwidphc.supabase.co:5432/postgres"


# Configuração da API OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Modelo para requisição de IQA
class IQARequest(BaseModel):
    city: str
    river: str
    point: str
    date: str

# Modelo para análise personalizada
class AnalysisRequest(BaseModel):
    parameters: dict
    collection_site: Optional[str]
    water_body_type: Optional[str]
    weather_conditions: Optional[str]
    human_activities: Optional[str]
    usage: Optional[str]
    coordinates: Optional[str]
    collection_date: Optional[str]
    collection_time: Optional[str]

# Conexão com o banco de dados Supabase
def get_db_connection():
    try:
        conn = psycopg2.connect(os.getenv("SUPABASE_DB_URL"), sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Busca dados de monitoramento no banco
def fetch_monitoring_data(city: str, river: str, points: List[str], start_date: str, end_date: str):
    """
    Busca dados de monitoramento no banco de dados com filtros de cidade, rio, pontos e intervalo de datas.
    :param city: Cidade.
    :param river: Rio.
    :param points: Lista de pontos de coleta.
    :param start_date: Data inicial (formato YYYY-MM-DD).
    :param end_date: Data final (formato YYYY-MM-DD).
    :return: Lista de dados de monitoramento.
    """
    query = """
    SELECT pH, TURBIDEZ, OD, TEMPERATURA, COLIFORMES, TDS, DBO, NITROGENIO_TOTAL, FOSFORO_TOTAL, collection_date, point
    FROM monitoring_data
    WHERE city = %s AND river = %s AND point IN %s AND collection_date BETWEEN %s AND %s
    ORDER BY collection_date, point
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(query, (city, river, tuple(points), start_date, end_date))
            results = cursor.fetchall()
            if results:
                return [dict(row) for row in results]
            else:
                raise HTTPException(status_code=404, detail="Nenhum dado encontrado para os filtros especificados.")
    finally:
        conn.close()


def generate_analysis(data: dict, context: str = "análise geral") -> str:
    """
    Gera uma análise com base nos dados fornecidos usando a API da OpenAI.
    :param data: Dados a serem analisados.
    :param context: Contexto da análise (ex: "monitoramento", "IQA", "análise personalizada").
    :return: Texto da análise gerada.
    """
    try:
        prompt = f"""
        Com base nos seguintes dados de {context}, forneça uma análise detalhada:
        {data}
        """
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar análise com OpenAI: {str(e)}")


def generate_pdf(content: str, filename: str = "relatorio.pdf"):
    """
    Gera um relatório em PDF com o conteúdo fornecido.
    :param content: Conteúdo do relatório.
    :param filename: Nome do arquivo PDF.
    :return: Caminho do arquivo PDF gerado.
    """
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, content)
        pdf.output(filename)
        return filename
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


# Cálculo do IQA
def calcular_iqa(city: str, river: str, point: str, date: str):
    valores_parametros = fetch_monitoring_data(city, river, point, date)
    pesos = {"OD": 0.17, "COLIFORMES": 0.15, "DBO": 0.10, "NITROGENIO_TOTAL": 0.10, "FOSFORO_TOTAL": 0.10, "TURBIDEZ": 0.08, "TDS": 0.08, "pH": 0.12, "TEMPERATURA": 0.10}
    valores_parametros_qi = {param: 80 if valores_parametros[param] else 50 for param in valores_parametros}
    iqa = sum(valores_parametros_qi[param] * pesos[param] for param in valores_parametros_qi) / sum(pesos.values())
    return iqa, None

@app.post("/calculate-iqa", tags=["IQA"], summary="Calcula o Índice de Qualidade da Água (IQA)")
def calculate_iqa(request: IQARequest):
    iqa, error = calcular_iqa(request.city, request.river, request.point, request.date)
    if error:
        return {"error": error}
    return {"iqa": iqa}

@app.post("/custom-analysis", tags=["Análises Personalizadas"], summary="Realiza uma análise personalizada da qualidade da água")
def custom_analysis(request: AnalysisRequest):
    response = requests.post(f"{SUPABASE_DB_URL}/rest/v1/custom_analysis", headers=HEADERS, json=request.dict())
    if response.status_code == 201:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao realizar análise personalizada.")

@app.get("/iqa/graph", tags=["IQA"], summary="Geração de gráfico de IQA")
def iqa_graph():
    response = requests.get(f"{SUPABASE_DB_URL}/rest/v1/graph_data", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar dados do gráfico.")

@app.get("/monitoring/graph-map", tags=["Monitoramento"], summary="Gráfico e Mapa do Monitoramento")
def monitoring_graph_map():
    response = requests.get(f"{SUPABASE_DB_URL}/rest/v1/monitoring_graph_map", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar dados do gráfico e mapa.")

@app.post("/generate-pdf", tags=["Relatórios"], summary="Gera um relatório em PDF")
def generate_pdf():
    return {"message": "Relatório PDF gerado."}

@app.post("/monitoring/analysis", tags=["Monitoramento"], summary="Análise dos dados de monitoramento")
def monitoring_analysis():
    response = requests.get(f"{SUPABASE_DB_URL}/rest/v1/monitoring_analysis", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar análise de monitoramento.")

@app.post("/iqa/analysis", tags=["IQA"], summary="Análise do Índice de Qualidade da Água (IQA)")
def analyze_iqa():
    response = requests.get(f"{SUPABASE_DB_URL}/rest/v1/iqa_analysis", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar análise de IQA.")

@app.get("/news", tags=["Notícias"], summary="Lista notícias para a home")
def list_news(limit: int = Query(10, description="Número máximo de notícias a serem retornadas")):
    query = f"""
    SELECT id, title, summary, date, image_url
    FROM news
    ORDER BY date DESC
    LIMIT {limit}
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            if results:
                return [dict(row) for row in results]
            else:
                raise HTTPException(status_code=404, detail="Nenhuma notícia encontrada.")
    finally:
        conn.close()

@app.get("/news/{news_id}", tags=["Notícias"], summary="Exibe uma notícia completa")
def get_news(news_id: int):
    query = """
    SELECT id, title, summary, content, date, image_url
    FROM news
    WHERE id = %s
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(query, (news_id,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            else:
                raise HTTPException(status_code=404, detail="Notícia não encontrada.")
    finally:
        conn.close()

@app.post("/iqa/analysis", tags=["IQA"], summary="Gera análise do Índice de Qualidade da Água (IQA)")
def iqa_analysis(city: str, river: str, points: List[str], start_date: str, end_date: str):
    # Busca dados de monitoramento
    data = fetch_monitoring_data(city, river, points, start_date, end_date)
    
    # Calcula o IQA para cada ponto e data
    iqa_results = []
    for entry in data:
        iqa, _ = calcular_iqa(city, river, entry["point"], entry["collection_date"])
        iqa_results.append({"point": entry["point"], "date": entry["collection_date"], "iqa": iqa})
    
    # Gera análise com OpenAI
    analysis = generate_analysis(iqa_results, context="análise do Índice de Qualidade da Água (IQA)")
    
    # Gera PDF com a análise
    pdf_filename = generate_pdf(analysis, filename=f"analise_iqa_{city}_{river}.pdf")
    
    return FileResponse(pdf_filename, media_type="application/pdf", filename=pdf_filename)

@app.post("/custom-analysis", tags=["Análises Personalizadas"], summary="Gera análise personalizada da qualidade da água")
def custom_analysis(request: AnalysisRequest):
    # Gera análise com OpenAI
    analysis = generate_analysis(request.dict(), context="análise personalizada da qualidade da água")
    
    # Gera PDF com a análise
    pdf_filename = generate_pdf(analysis, filename="analise_personalizada.pdf")
    
    return FileResponse(pdf_filename, media_type="application/pdf", filename=pdf_filename)


@app.post("/monitoring/analysis", tags=["Monitoramento"], summary="Gera análise dos dados de monitoramento")
def monitoring_analysis(city: str, river: str, points: List[str], start_date: str, end_date: str):
    # Busca dados de monitoramento
    data = fetch_monitoring_data(city, river, points, start_date, end_date)
    
    # Gera análise com OpenAI
    analysis = generate_analysis(data, context="monitoramento da qualidade da água")
    
    # Gera PDF com a análise
    pdf_filename = generate_pdf(analysis, filename=f"analise_monitoramento_{city}_{river}.pdf")
    
    return FileResponse(pdf_filename, media_type="application/pdf", filename=pdf_filename)
