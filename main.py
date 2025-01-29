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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

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
def fetch_monitoring_data(city: str, river: str, point: str, date: str):
    query = """
    SELECT pH, TURBIDEZ, OD, TEMPERATURA, COLIFORMES, TDS, DBO, NITROGENIO_TOTAL, FOSFORO_TOTAL
    FROM monitoring_data WHERE city = %s AND river = %s AND point = %s AND collection_date = %s
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (city, river, point, date))
            result = cursor.fetchone()
            if result:
                columns = ["pH", "TURBIDEZ", "OD", "TEMPERATURA", "COLIFORMES", "TDS", "DBO", "NITROGENIO_TOTAL", "FOSFORO_TOTAL"]
                return dict(zip(columns, result))
            else:
                raise HTTPException(status_code=404, detail="No data found for the specified filters.")
    finally:
        conn.close()

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
    response = requests.post(f"{SUPABASE_URL}/rest/v1/custom_analysis", headers=HEADERS, json=request.dict())
    if response.status_code == 201:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao realizar análise personalizada.")

@app.get("/iqa/graph", tags=["IQA"], summary="Geração de gráfico de IQA")
def iqa_graph():
    response = requests.get(f"{SUPABASE_URL}/rest/v1/graph_data", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar dados do gráfico.")

@app.get("/monitoring/graph-map", tags=["Monitoramento"], summary="Gráfico e Mapa do Monitoramento")
def monitoring_graph_map():
    response = requests.get(f"{SUPABASE_URL}/rest/v1/monitoring_graph_map", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar dados do gráfico e mapa.")

@app.post("/generate-pdf", tags=["Relatórios"], summary="Gera um relatório em PDF")
def generate_pdf():
    return {"message": "Relatório PDF gerado."}

@app.post("/monitoring/analysis", tags=["Monitoramento"], summary="Análise dos dados de monitoramento")
def monitoring_analysis():
    response = requests.get(f"{SUPABASE_URL}/rest/v1/monitoring_analysis", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar análise de monitoramento.")

@app.post("/iqa/analysis", tags=["IQA"], summary="Análise do Índice de Qualidade da Água (IQA)")
def analyze_iqa():
    response = requests.get(f"{SUPABASE_URL}/rest/v1/iqa_analysis", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=500, detail="Erro ao buscar análise de IQA.")
