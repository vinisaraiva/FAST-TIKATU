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
#SUPABASE_DB_URL = "postgresql://postgres:<PASSWORD>@db.jxbsqnkdtdmshfwidphc.supabase.co:5432/postgres"
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

class NewsItem(BaseModel):
    id: Optional[int]
    title: str
    summary: str
    content: str
    date: Optional[str]
    image_url: Optional[str]

# Função para gerar PDFs dinâmicos
def generate_analysis_pdf(analysis_result: dict, pdf_path: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Título
    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt="Water Quality Analysis Report", ln=True, align='C')
    pdf.ln(10)

    # Corpo do relatório
    pdf.set_font("Arial", size=12)
    for key, value in analysis_result.items():
        pdf.cell(0, 10, txt=f"{key}: {value}", ln=True)

    pdf.output(pdf_path)

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
def build_prompt_for_custom_analysis(request: AnalysisRequest):
    prompt = f"""
    Analysis of water collected in a {request.collection_site}:
    Collection date: {request.collection_date} at {request.collection_time}.
    Location: {request.coordinates}.

    Environmental conditions:
    - Type of water body: {request.water_body_type}
    - Recent weather conditions: {request.weather_conditions}
    - Nearby human activities: {request.human_activities}
    - What will be the use of the water: {request.usage}

    Physicochemical parameters:
    """
    for key, value in request.parameters.items():
        prompt += f"- {key}: {value}\n"

    prompt += "\nAct as an expert with a PhD in water parameter analysis, but you need to respond with language accessible to diverse audiences. Generate an initial analysis of water quality based on this information."
    return prompt

# Endpoint para listar dados de monitoramento com filtros
@app.get("/monitoring")
async def get_monitoring_data(
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
            return {"monitoring_data": monitoring_data}
    finally:
        conn.close()

# Endpoint para listar dados de IQA com filtros específicos
@app.get("/iqa")
async def get_iqa_data(
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
            return {"iqa_data": iqa_data}
    finally:
        conn.close()

# Endpoint para gerar análise personalizada
@app.post("/custom/analysis")
async def custom_analysis(request: AnalysisRequest):
    try:
        if not request.parameters or all(value is None or value == "" for value in request.parameters.values()):
            raise HTTPException(status_code=400, detail="At least one parameter must be provided to generate the analysis.")

        prompt = build_prompt_for_custom_analysis(request)
        analysis_result = generate_analysis_with_openai(prompt)

        return {"parameters": request.parameters, "analysis": analysis_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para listar todas as notícias
@app.get("/news")
async def get_news():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM news;")
            news = cursor.fetchall()
            return {"news": news}
    finally:
        conn.close()

# Endpoint para detalhar uma notícia específica
@app.get("/news/{news_id}")
async def get_news_item(news_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM news WHERE id = %s;", (news_id,))
            news_item = cursor.fetchone()
            if not news_item:
                raise HTTPException(status_code=404, detail="News item not found.")
            return news_item
    finally:
        conn.close()

# Endpoint para adicionar uma nova notícia
@app.post("/news")
async def create_news(news_item: NewsItem):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO news (title, summary, content, date, image_url)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (news_item.title, news_item.summary, news_item.content, news_item.date, news_item.image_url)
            )
            conn.commit()
            return {"message": "News item created successfully."}
    finally:
        conn.close()

# Endpoint para atualizar uma notícia
@app.put("/news/{news_id}")
async def update_news(news_id: int, news_item: NewsItem):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE news
                SET title = %s, summary = %s, content = %s, date = %s, image_url = %s
                WHERE id = %s;
                """,
                (news_item.title, news_item.summary, news_item.content, news_item.date, news_item.image_url, news_id)
            )
            conn.commit()
            return {"message": "News item updated successfully."}
    finally:
        conn.close()

# Endpoint para remover uma notícia
@app.delete("/news/{news_id}")
async def delete_news(news_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM news WHERE id = %s;", (news_id,))
            conn.commit()
            return {"message": "News item deleted successfully."}
    finally:
        conn.close()
