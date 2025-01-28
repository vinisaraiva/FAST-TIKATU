from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
from fpdf import FPDF
import openai
import re

# Configuração inicial do FastAPI
app = FastAPI(title="Tikatu API", version="1.0.0")

# URLs das APIs externas
SHEETDB_DADOS_API_URL = "https://sheetdb.io/api/v1/85u4y2iziptre"
SHEETDB_RIOCHAMAGUNGA_API_URL = "https://sheetdb.io/api/v1/vlop1cs9uqewu"

# Configuração da API OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Classes de modelo para validação de dados
class MonitoringData(BaseModel):
    city: Optional[str]
    river: Optional[str]
    parameter: Optional[str]
    point: Optional[str]
    date: Optional[str]

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
    content: str
    date: Optional[str]

# Simulação de armazenamento de notícias
news_storage = []

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

# Rota de análise personalizada
@app.post("/custom/analysis")
async def custom_analysis(request: AnalysisRequest):
    """
    Endpoint para realizar análise manual com IA dos parâmetros personalizados informados pelo usuário.
    Deve ser acionado pelo botão correspondente no front-end.
    """
    try:
        # Verificar se pelo menos um parâmetro foi preenchido
        if not request.parameters or all(value is None or value == "" for value in request.parameters.values()):
            raise HTTPException(status_code=400, detail="At least one parameter must be provided to generate the analysis.")

        # Construir o prompt para análise personalizada
        prompt = build_prompt_for_custom_analysis(request)

        # Gera análise com OpenAI
        analysis_result = generate_analysis_with_openai(prompt)

        return {"parameters": request.parameters, "analysis": analysis_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rota de gráfico para monitoramento
@app.get("/monitoring/graph")
async def get_monitoring_graph(
    city: str,
    river: str,
    parameter: str,
    points: List[str] = Query(...),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Endpoint para retornar dados filtrados para renderização de gráficos na tela de monitoramento.
    Suporta filtros por cidade, rio, parâmetro, pontos de coleta e intervalo de datas.
    """
    try:
        response = requests.get(SHEETDB_RIOCHAMAGUNGA_API_URL)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch monitoring data.")

        data = response.json()

        # Filtrar os dados com base nos parâmetros fornecidos
        filtered_data = [
            entry for entry in data
            if entry.get("CIDADE") == city
            and entry.get("RIO") == river
            and entry.get("PONTOS") in points
            and parameter in entry
            and (
                (not start_date and not end_date) or
                (start_date and end_date and start_date <= entry.get("DATA_COLETA") <= end_date) or
                (start_date and not end_date and entry.get("DATA_COLETA") == start_date)
            )
        ]

        # Preparar os dados para o gráfico
        graph_data = {}
        for entry in filtered_data:
            point = entry.get("PONTOS")
            date = entry.get("DATA_COLETA")
            value = float(entry.get(parameter, 0))

            if point not in graph_data:
                graph_data[point] = []
            graph_data[point].append({"date": date, "value": value})

        return {"graph_data": graph_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rota de gráfico para IQA
@app.get("/iqa/graph")
async def get_iqa_graph(city: str, river: str, points: List[str]):
    """
    Endpoint para retornar os valores de IQA para renderização de gráficos na tela de IQA.
    A análise com IA NÃO É AUTOMÁTICA, sendo necessária a chamada manual via botão no front-end.
    """
    try:
        response = requests.get(SHEETDB_RIOCHAMAGUNGA_API_URL)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch monitoring data.")

        data = response.json()

        # Filtrar os dados com base na cidade, rio e pontos de coleta
        filtered_data = [
            entry for entry in data
            if entry.get("CIDADE") == city and entry.get("RIO") == river and entry.get("PONTOS") in points
        ]

        # Calcular o IQA
        iqa_results = calculate_iqa(filtered_data)

        # Retornar os valores de IQA para o gráfico
        return {"iqa_results": iqa_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rota de cálculo do IQA com análise
@app.post("/iqa/analysis")
async def analyze_iqa_data(city: str, river: str, points: List[str]):
    """
    Endpoint para realizar análise de IQA manualmente ao acionar o botão na tela de IQA.
    Recebe os pontos filtrados e gera uma análise detalhada com base nos valores de IQA.
    """
    try:
        response = requests.get(SHEETDB_RIOCHAMAGUNGA_API_URL)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch monitoring data.")

        data = response.json()

        # Filtrar os dados com base na cidade, rio e pontos de coleta
        filtered_data = [
            entry for entry in data
            if entry.get("CIDADE") == city and entry.get("RIO") == river and entry.get("PONTOS") in points
        ]

        # Calcular o IQA
        iqa_results = calculate_iqa(filtered_data)

        # Construir o prompt para análise do IQA
        prompt = build_prompt_for_iqa_analysis(iqa_results)

        # Gera análise com OpenAI
        analysis_result = generate_analysis_with_openai(prompt)

        return {"iqa_results": iqa_results, "analysis": analysis_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

