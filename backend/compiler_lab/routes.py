"""
HTTP layer for the Compiler Lab.

POST /compile            -> runs the pipeline and returns the output of every phase
GET  /compile/languages  -> languages the UI can offer, with a sample program each

Right now only phase 1 (lexical analysis) exists. Each later phase will simply
add another key under "phases", so the frontend never needs a new endpoint.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .languages import LANGUAGES, get_language
from .lexer import lex

router = APIRouter(prefix="/compile", tags=["compiler-lab"])

MAX_SOURCE_CHARS = 100_000


class CompileRequest(BaseModel):
    language: str = "c"
    source_code: str


@router.get("/languages")
def list_languages():
    return [
        {"id": l.id, "name": l.name, "notes": l.notes, "sample": l.sample}
        for l in LANGUAGES.values()
    ]


@router.post("")
def compile_source(payload: CompileRequest):
    try:
        lang = get_language(payload.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if len(payload.source_code) > MAX_SOURCE_CHARS:
        raise HTTPException(status_code=413, detail=f"Source too large (max {MAX_SOURCE_CHARS} characters).")
    if not payload.source_code.strip():
        raise HTTPException(status_code=400, detail="Please enter some source code first.")

    lexical = lex(lang, payload.source_code)
    return {
        "language": lang.id,
        "language_name": lang.name,
        "available_phases": ["lexical"],
        "phases": {"lexical": lexical},
    }
