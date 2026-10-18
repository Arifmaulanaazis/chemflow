"""Materi workshop terbundel yang terautentikasi dan metadata sitasi bersama."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from chemflow.citations import references, render


def router():
    routes=APIRouter(prefix="/api")
    @routes.get("/citations")
    def citations():return references()
    @routes.get("/citations/bibtex")
    def bibtex():return PlainTextResponse(render("bibtex"),headers={"Content-Disposition":'attachment; filename="chemflow-citations.bib"'})
    @routes.get("/library")
    def library():return [{"id":"guide","title":"Panduan & workshop ChemFlow","pages":56,"formats":["pdf","pptx"]}]
    @routes.get("/library/{document}/file")
    def file(document:str,format:str="pdf"):
        if document!="guide" or format not in {"pdf","pptx"}:raise HTTPException(404,"Materi tidak ditemukan.")
        path=Path(__file__).resolve().parents[1]/"resources"/("chemflow."+format)
        if not path.is_file():raise HTTPException(503,"Materi belum disertakan pada instalasi ini.")
        return FileResponse(path,media_type="application/pdf" if format=="pdf" else "application/vnd.openxmlformats-officedocument.presentationml.presentation",filename=path.name,content_disposition_type="inline" if format=="pdf" else "attachment")
    return routes
