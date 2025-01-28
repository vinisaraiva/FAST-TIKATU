from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import requests
import os
from fpdf import FPDF
import openai
import re
import psycopg2
import psycopg2.extras

# Configuração inicial do FastAPI
app = FastAPI(title="Tikatu API", version="1.0.0")

# Configuração do Supabase
SUPABASE_DB_URL = "postgresql://postgres:<PASSWORD>@db.jxbsqnkdtdmshfwidphc.supabase.co:5432/postgres"

# Função para conectar ao banco de dados Supabase
def get_db_connection():
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Modelo para dados de monitoramento
class MonitoringData(BaseModel):
    city: Optional[str]
    river: Optional[str]
    parameter: Optional[str]
    point: Optional[List[str]]
    start_date: Optional[str]
    end_date: Optional[str]

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

# Endpoint para inserir novos dados de monitoramento
@app.post("/monitoring")
async def add_monitoring_data(data: MonitoringData):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO monitoring_data (city, river, point, collection_date, collection_time, gps, turbidity, conductivity, ph, temperature, salinity, nitrogen_total, phosphorus_total, tds, coliforms, dbo, od, latitude, longitude, observation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    data.city, data.river, data.point, data.start_date, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
                )
            )
            conn.commit()
            return {"message": "Monitoring data added successfully."}
    finally:
        conn.close()
