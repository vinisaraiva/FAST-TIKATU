from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
import psycopg2.extras
import os
import openai
from fpdf import FPDF

# Configuração inicial do FastAPI
app = FastAPI(title="Tikatu API", version="1.0.0")

# Configuração do Supabase
SUPABASE_DB_URL = f"postgresql://postgres:{os.getenv('SUPABASE_TK_PWD')}@db.jxbsqnkdtdmshfwidphc.supabase.co:5432/postgres"

# Configuração da API OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Função para conectar ao banco de dados Supabase
def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Classes de modelo para validação de dados
class MonitoringData(BaseModel):
    city: Optional[str]
    river: Optional[str]
    parameter: Optional[str]
    point: Optional[List[str]]
    start_date: Optional[str]
    end_date: Optional[str]

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

# Função para realizar análise com OpenAI
def generate_analysis_with_openai(prompt):
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=500
        )
        return response.choices[0].text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating analysis: {str(e)}")

# Função para construir prompts específicos
def build_prompt_for_monitoring_analysis(monitoring_data):
    prompt = """
    Analyze the following water monitoring data:
    """
    for entry in monitoring_data:
        prompt += f"Point {entry['point']} on {entry['collection_date']}:
"
        for key, value in entry.items():
            if key not in ['point', 'collection_date', 'id']:
                prompt += f"  - {key}: {value}\n"
    prompt += "\nGenerate an analysis considering environmental impact and potential causes."
    return prompt

def build_prompt_for_iqa_analysis(iqa_data):
    prompt = """
    Analyze the Water Quality Index (WQI) for the following points:
    """
    for entry in iqa_data:
        prompt += f"Point {entry['point']}:
"
        for key, value in entry.items():
            if key not in ['point', 'id']:
                prompt += f"  - {key}: {value}\n"
    prompt += "\nProvide a detailed analysis considering WQI values and their implications."
    return prompt

# Endpoint para análise da tela de monitoramento
@app.post("/monitoring/analysis")
async def analyze_monitoring_data(
    city: Optional[str] = None,
    river: Optional[str] = None,
    parameter: Optional[str] = None,
    points: Optional[List[str]] = Query(None),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            query = "SELECT * FROM monitoring_data WHERE 1=1"
            params = []

            if city:
                query += " AND city = %s"
                params.append(city)

            if river:
                query += " AND river = %s"
                params.append(river)

            if parameter:
                query += f" AND {parameter} IS NOT NULL"

            if points:
                query += " AND point = ANY(%s)"
                params.append(points)

            if start_date and end_date:
                query += " AND collection_date BETWEEN %s AND %s"
                params.extend([start_date, end_date])
            elif start_date:
                query += " AND collection_date >= %s"
                params.append(start_date)
            elif end_date:
                query += " AND collection_date <= %s"
                params.append(end_date)

            cursor.execute(query, params)
            monitoring_data = cursor.fetchall()

            if not monitoring_data:
                raise HTTPException(status_code=404, detail="No monitoring data found for the specified filters.")

            prompt = build_prompt_for_monitoring_analysis(monitoring_data)
            analysis_result = generate_analysis_with_openai(prompt)

            return {"monitoring_data": monitoring_data, "analysis": analysis_result}
    finally:
        conn.close()

# Endpoint para análise da tela de IQA
@app.post("/iqa/analysis")
async def analyze_iqa_data(
    city: Optional[str] = None,
    river: Optional[str] = None,
    points: Optional[List[str]] = Query(None)
):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            query = "SELECT city, river, point, turbidity, ph, temperature, coliforms, od FROM monitoring_data WHERE 1=1"
            params = []

            if city:
                query += " AND city = %s"
                params.append(city)

            if river:
                query += " AND river = %s"
                params.append(river)

            if points:
                query += " AND point = ANY(%s)"
                params.append(points)

            cursor.execute(query, params)
            iqa_data = cursor.fetchall()

            if not iqa_data:
                raise HTTPException(status_code=404, detail="No IQA data found for the specified filters.")

            prompt = build_prompt_for_iqa_analysis(iqa_data)
            analysis_result = generate_analysis_with_openai(prompt)

            return {"iqa_data": iqa_data, "analysis": analysis_result}
    finally:
        conn.close()
