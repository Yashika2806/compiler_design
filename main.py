"""
FastAPI application.

This is the thin web layer over everything we already built: it takes
Solidity source in over HTTP, runs it through lexer -> parser ->
semantic analyzer -> rule engine -> scorer -> report generator (all
unchanged from the pytest-tested version), saves a record to SQLite,
and returns the report as JSON.

Run locally with:  uvicorn api.main:app --reload
Then open:          http://127.0.0.1:8000/docs   (interactive Swagger UI)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from compiler.lexer import Lexer, LexerError
from compiler.parser import Parser, ParserError
from compiler.semantic_analyzer import analyze_contract
from rules.engine import run_all_rules
from scoring.risk_score import compute_score
from reporting.report_generator import build_report
from compiler_lab.routes import router as compile_router

from .database import init_db, save_analysis, list_history, get_analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Smart Contract Vulnerability Detection Tool",
    description="Static security analyzer for Solidity smart contracts.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the React dev server (localhost:3000/5173) to call this API later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Compiler Lab: multi-language, 6-phase compiler visualizer endpoints
app.include_router(compile_router)


class AnalyzeRequest(BaseModel):
    contract_name: str = "UnnamedContract"
    source_code: str


def _run_pipeline(contract_name: str, source: str) -> dict:
    try:
        tokens = Lexer(source).tokenize()
    except LexerError as e:
        raise HTTPException(status_code=400, detail=f"Lexer error: {e}")

    try:
        contracts = Parser(tokens).parse()
    except ParserError as e:
        raise HTTPException(status_code=400, detail=f"Parser error: {e}")

    if not contracts:
        raise HTTPException(status_code=400, detail="No contract declaration found in source.")

    # For our subset, analyze the first contract found in the file.
    info = analyze_contract(contracts[0])
    findings = run_all_rules(info, source)
    score = compute_score(findings)
    name = contract_name if contract_name != "UnnamedContract" else info.name
    report = build_report(name, source, findings, score)
    return report


@app.get("/")
def root():
    return {"status": "ok", "message": "Smart Contract Vulnerability Detection Tool API"}


@app.post("/analyze")
def analyze_pasted_code(payload: AnalyzeRequest):
    """Analyze Solidity source pasted directly as JSON."""
    report = _run_pipeline(payload.contract_name, payload.source_code)
    save_analysis(report["contract_name"], report)
    return report


@app.post("/analyze/upload")
async def analyze_uploaded_file(file: UploadFile = File(...)):
    """Analyze an uploaded .sol file."""
    if not file.filename.endswith(".sol"):
        raise HTTPException(status_code=400, detail="Please upload a .sol file.")
    contents = (await file.read()).decode("utf-8")
    contract_name = file.filename.removesuffix(".sol")
    report = _run_pipeline(contract_name, contents)
    save_analysis(report["contract_name"], report)
    return report


@app.get("/history")
def get_history(limit: int = 50):
    records = list_history(limit=limit)
    return [
        {
            "id": r.id,
            "contract_name": r.contract_name,
            "created_at": r.created_at,
            "security_score": r.security_score,
            "risk_level": r.risk_level,
            "total_findings": r.total_findings,
            "severity_counts": r.severity_counts(),
        }
        for r in records
    ]


@app.get("/history/{analysis_id}")
def get_history_report(analysis_id: int):
    record = get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return record.report()
