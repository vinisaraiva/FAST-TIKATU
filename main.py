from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import psycopg2
import psycopg2.extras
import os
import openai
from fpdf import FPDF
import re  # Adicionado para manipulação de strings
from typing import Dict


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


# Definição da classe IQARequest para validação
class IQARequest(BaseModel):
    city: str
    river: str
    point: str
    date: str

# Definição da classe AnalysisRequest para análise personalizada
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

# Função para conectar ao banco de dados Supabase
def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Função para consultar os dados necessários no banco
def fetch_monitoring_data(city: str, river: str, point: str, date: str):
    query = (
        "SELECT pH, TURBIDEZ, OD, TEMPERATURA, COLIFORMES, TDS, DBO, NITROGENIO_TOTAL, FOSFORO_TOTAL "
        "FROM monitoring_data WHERE city = %s AND river = %s AND point = %s AND collection_date = %s"
    )

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (city, river, point, date))
            result = cursor.fetchone()
            conn.close()

            if result:
                # Converte os resultados para um dicionário
                columns = ["pH", "TURBIDEZ", "OD", "TEMPERATURA", "COLIFORMES", "TDS", "DBO", "NITROGENIO_TOTAL", "FOSFORO_TOTAL"]
                return dict(zip(columns, result))
            else:
                raise HTTPException(status_code=404, detail="No data found for the specified filters.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching monitoring data: {str(e)}")

# Função para calcular o IQA
def calcular_iqa(city: str, river: str, point: str, date: str):
    try:
        # Busca os dados do banco de dados
        valores_parametros = fetch_monitoring_data(city, river, point, date)

        # Convertendo os valores para float, se possível
        faltantes = []
        for key in valores_parametros:
            if isinstance(valores_parametros[key], str):
                valores_parametros[key] = re.sub(r"[^0-9.,]", "", valores_parametros[key]).replace(",", ".")
            try:
                valores_parametros[key] = float(valores_parametros[key])
            except (ValueError, TypeError):
                valores_parametros[key] = None
                faltantes.append(key)

        if any(v is None for v in valores_parametros.values()):
            return None, f"Erro: Parâmetros faltantes ou inválidos: {', '.join(faltantes)}. Não é possível calcular o IQA sem todos os parâmetros."

        # Pesos dos parâmetros utilizados no cálculo do IQA
        pesos = {
            "OD": 0.17,
            "COLIFORMES": 0.15,
            "DBO": 0.10,
            "NITROGENIO_TOTAL": 0.10,
            "FOSFORO_TOTAL": 0.10,
            "TURBIDEZ": 0.08,
            "TDS": 0.08,
            "pH": 0.12,
            "TEMPERATURA": 0.10,
        }

        # Função para converter os valores dos parâmetros para a escala de 0 a 100 (qi)
        def converter_para_qi(param, valor):
            conversao_qi = {
                "OD": 80 if valor >= 6 else 50,
                "COLIFORMES": 30 if valor >= 1000 else 70,
                "DBO": 60 if valor <= 5 else 30,
                "NITROGENIO_TOTAL": 70 if valor <= 10 else 40,
                "FOSFORO_TOTAL": 90 if valor <= 0.1 else 50,
                "TURBIDEZ": 85 if valor <= 10 else 40,
                "TDS": 75 if valor <= 500 else 50,
                "pH": 90 if 6.5 <= valor <= 8.5 else 60,
                "TEMPERATURA": 70 if valor <= 25 else 50,
            }
            return conversao_qi.get(param, 50)

        # Converte cada valor de parâmetro para qi
        valores_parametros_qi = {
            param: converter_para_qi(param, valor)
            for param, valor in valores_parametros.items()
        }

        # Cálculo da média ponderada para obter o IQA
        iqa = sum(
            valores_parametros_qi[param] * pesos.get(param, 0)
            for param in valores_parametros_qi
        ) / sum(pesos.values())

        return iqa, None
    except Exception as e:
        return None, str(e)

# Inicializando o FastAPI e rota de cálculo
app = FastAPI()

@app.post("/calculate-iqa")
async def calculate_iqa(request: IQARequest):
    iqa, error = calcular_iqa(request.city, request.river, request.point, request.date)
    if error:
        return {"error": error}
    return {"iqa": iqa}

@app.post("/custom-analysis")
async def custom_analysis(request: AnalysisRequest):
    prompt = build_prompt_for_custom_analysis(request)
    return {"prompt": prompt}

# Aqui deve ser reintroduzido o restante do código original


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

# Função para construir prompts específicos para análises personalizadas
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

# Função para criar PDFs dinâmicos
def generate_pdf(analysis_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Título
    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt="Custom Water Analysis Report", ln=True, align='C')
    pdf.ln(10)

    # Corpo do relatório
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=analysis_text)

    # Salvar PDF temporariamente
    pdf_path = "/tmp/analysis_report.pdf"
    pdf.output(pdf_path)
    return pdf_path

# Endpoint para gerar PDF
@app.post("/generate-pdf")
async def generate_pdf_endpoint(analysis_text: str):
    try:
        pdf_path = generate_pdf(analysis_text)
        return FileResponse(pdf_path, media_type="application/pdf", filename="analysis_report.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para análise personalizada
@app.post("/custom/analysis")
async def custom_analysis(request: AnalysisRequest):
    try:
        # Verificar se pelo menos um parâmetro foi preenchido
        if not request.parameters or all(value is None or value == "" for value in request.parameters.values()):
            raise HTTPException(status_code=400, detail="At least one parameter must be provided to generate the analysis.")

        # Construir o prompt para análise personalizada
        prompt = build_prompt_for_custom_analysis(request)

        # Gera análise com OpenAI
        analysis_result = generate_analysis_with_openai(prompt)

        return {
            "analysis": analysis_result,
            "pdf_generation_url": "/generate-pdf"  # URL para gerar o PDF
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para gráfico e mapa na tela de monitoramento
@app.get("/monitoring/graph-map")
async def get_monitoring_graph_map(
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
            query = "SELECT collection_date, point, latitude, longitude, " + parameter + " AS value FROM monitoring_data WHERE 1=1"
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

            if start_date and end_date:
                query += " AND collection_date BETWEEN %s AND %s"
                params.extend([start_date, end_date])

            cursor.execute(query, params)
            data = cursor.fetchall()

            if not data:
                raise HTTPException(status_code=404, detail="No data found for the specified filters.")

            return {"graph_map_data": data}
    finally:
        conn.close()

# Endpoint para gráfico dinâmico na tela de IQA
@app.get("/iqa/graph")
async def get_iqa_graph(
    city: Optional[str] = None,
    river: Optional[str] = None,
    points: Optional[List[str]] = Query(None)
):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            query = "SELECT point, turbidity, ph, temperature, coliforms, od FROM monitoring_data WHERE 1=1"
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
            data = cursor.fetchall()

            if not data:
                raise HTTPException(status_code=404, detail="No data found for the specified filters.")

            return {"iqa_graph_data": data}
    finally:
        conn.close()

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

            return {
                "monitoring_data": monitoring_data,
                "analysis": analysis_result,
                "pdf_generation_url": "/generate-pdf"  # URL para gerar o PDF
            }
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

            return {
                "iqa_data": iqa_data,
                "analysis": analysis_result,
                "pdf_generation_url": "/generate-pdf"  # URL para gerar o PDF
            }
    finally:
        conn.close()



from fastapi import HTTPException
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Optional
import psycopg2
import re

# Definição da classe IQARequest para validação
class IQARequest(BaseModel):
    city: str
    river: str
    point: str
    date: str

# Definição da classe AnalysisRequest para análise personalizada
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

# Função para conectar ao banco de dados Supabase
def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Função para consultar os dados necessários no banco
def fetch_monitoring_data(city: str, river: str, point: str, date: str):
    query = (
        "SELECT pH, TURBIDEZ, OD, TEMPERATURA, COLIFORMES, TDS, DBO, NITROGENIO_TOTAL, FOSFORO_TOTAL "
        "FROM monitoring_data WHERE city = %s AND river = %s AND point = %s AND collection_date = %s"
    )

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (city, river, point, date))
            result = cursor.fetchone()
            conn.close()

            if result:
                # Converte os resultados para um dicionário
                columns = ["pH", "TURBIDEZ", "OD", "TEMPERATURA", "COLIFORMES", "TDS", "DBO", "NITROGENIO_TOTAL", "FOSFORO_TOTAL"]
                return dict(zip(columns, result))
            else:
                raise HTTPException(status_code=404, detail="No data found for the specified filters.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching monitoring data: {str(e)}")

# Função para calcular o IQA
def calcular_iqa(city: str, river: str, point: str, date: str):
    try:
        # Busca os dados do banco de dados
        valores_parametros = fetch_monitoring_data(city, river, point, date)

        # Convertendo os valores para float, se possível
        faltantes = []
        for key in valores_parametros:
            if isinstance(valores_parametros[key], str):
                valores_parametros[key] = re.sub(r"[^0-9.,]", "", valores_parametros[key]).replace(",", ".")
            try:
                valores_parametros[key] = float(valores_parametros[key])
            except (ValueError, TypeError):
                valores_parametros[key] = None
                faltantes.append(key)

        if any(v is None for v in valores_parametros.values()):
            return None, f"Erro: Parâmetros faltantes ou inválidos: {', '.join(faltantes)}. Não é possível calcular o IQA sem todos os parâmetros."

        # Pesos dos parâmetros utilizados no cálculo do IQA
        pesos = {
            "OD": 0.17,
            "COLIFORMES": 0.15,
            "DBO": 0.10,
            "NITROGENIO_TOTAL": 0.10,
            "FOSFORO_TOTAL": 0.10,
            "TURBIDEZ": 0.08,
            "TDS": 0.08,
            "pH": 0.12,
            "TEMPERATURA": 0.10,
        }

        # Função para converter os valores dos parâmetros para a escala de 0 a 100 (qi)
        def converter_para_qi(param, valor):
            conversao_qi = {
                "OD": 80 if valor >= 6 else 50,
                "COLIFORMES": 30 if valor >= 1000 else 70,
                "DBO": 60 if valor <= 5 else 30,
                "NITROGENIO_TOTAL": 70 if valor <= 10 else 40,
                "FOSFORO_TOTAL": 90 if valor <= 0.1 else 50,
                "TURBIDEZ": 85 if valor <= 10 else 40,
                "TDS": 75 if valor <= 500 else 50,
                "pH": 90 if 6.5 <= valor <= 8.5 else 60,
                "TEMPERATURA": 70 if valor <= 25 else 50,
            }
            return conversao_qi.get(param, 50)

        # Converte cada valor de parâmetro para qi
        valores_parametros_qi = {
            param: converter_para_qi(param, valor)
            for param, valor in valores_parametros.items()
        }

        # Cálculo da média ponderada para obter o IQA
        iqa = sum(
            valores_parametros_qi[param] * pesos.get(param, 0)
            for param in valores_parametros_qi
        ) / sum(pesos.values())

        return iqa, None
    except Exception as e:
        return None, str(e)

# Função para construir o prompt para análise personalizada
def build_prompt_for_custom_analysis(request: AnalysisRequest):
    prompt = f"""
    Análise personalizada da qualidade da água coletada em {request.collection_site}:
    - Tipo de corpo de água: {request.water_body_type}
    - Condições climáticas: {request.weather_conditions}
    - Atividades humanas próximas: {request.human_activities}
    - Uso pretendido da água: {request.usage}
    - Coordenadas: {request.coordinates}
    - Data da coleta: {request.collection_date}
    - Hora da coleta: {request.collection_time}

    Parâmetros físico-químicos observados:
    {request.parameters}

    Gere uma análise detalhada da qualidade da água com base nesses dados.
    """
    return prompt

# Inicializando o FastAPI e rota de cálculo
app = FastAPI()

@app.post("/calculate-iqa")
async def calculate_iqa(request: IQARequest):
    iqa, error = calcular_iqa(request.city, request.river, request.point, request.date)
    if error:
        return {"error": error}
    return {"iqa": iqa}

@app.post("/custom-analysis")
async def custom_analysis(request: AnalysisRequest):
    prompt = build_prompt_for_custom_analysis(request)
    return {"prompt": prompt}
