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
    summary: str
    content: str
    date: Optional[str]
    image_url: Optional[str]

# Simulação de armazenamento de notícias
news_storage = [
    {
        "id": 1,
        "title": "New Water Quality Report Released",
        "summary": "The latest report on water quality shows improvements in key areas.",
        "content": "The latest report on water quality has been released, showing improvements in key areas. Detailed insights into the report highlight progress in reducing pollution levels.",
        "date": "2025-01-01",
        "image_url": "https://example.com/images/report.jpg"
    },
    {
        "id": 2,
        "title": "Community Efforts to Clean Rivers",
        "summary": "Local communities join forces to clean rivers in their areas.",
        "content": "Local communities have joined forces to clean the rivers in their areas. These efforts include organized clean-up drives and awareness campaigns.",
        "date": "2025-01-15",
        "image_url": "https://example.com/images/cleaning.jpg"
    }
]

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

# Rota para listar todas as notícias
@app.get("/news")
async def get_news():
    """
    Retorna todas as notícias para exibição inicial nos cards.
    Inclui título, resumo, data e URL da imagem.
    """
    return {"news": [
        {
            "id": news["id"],
            "title": news["title"],
            "summary": news["summary"],
            "date": news["date"],
            "image_url": news["image_url"]
        }
        for news in news_storage
    ]}

# Rota para detalhar uma notícia específica
@app.get("/news/{news_id}")
async def get_news_item(news_id: int):
    """
    Retorna o conteúdo completo de uma notícia com base no ID.
    Inclui título, conteúdo completo, data e URL da imagem.
    """
    for news in news_storage:
        if news.get("id") == news_id:
            return news
    raise HTTPException(status_code=404, detail="News item not found.")

# Rota para adicionar uma nova notícia
@app.post("/news")
async def create_news(news_item: NewsItem):
    """
    Adiciona uma nova notícia ao sistema.
    """
    news_item.id = len(news_storage) + 1
    news_storage.append(news_item.dict())
    return {"message": "News item created successfully.", "news_item": news_item}

# Rota para atualizar uma notícia existente
@app.put("/news/{news_id}")
async def update_news(news_id: int, news_item: NewsItem):
    """
    Atualiza uma notícia existente com base no ID.
    """
    for idx, news in enumerate(news_storage):
        if news.get("id") == news_id:
            news_storage[idx].update(news_item.dict())
            return {"message": "News item updated successfully.", "news_item": news_storage[idx]}
    raise HTTPException(status_code=404, detail="News item not found.")

# Rota para remover uma notícia existente
@app.delete("/news/{news_id}")
async def delete_news(news_id: int):
    """
    Remove uma notícia existente com base no ID.
    """
    global news_storage
    news_storage = [news for news in news_storage if news.get("id") != news_id]
    return {"message": "News item deleted successfully."}

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
        analysis_result = generate_analysis_with_openAI(prompt)

        return {"parameters": request.parameters, "analysis": analysis_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
