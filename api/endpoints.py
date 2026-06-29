from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
import html
import io
import re
import textwrap
import zipfile

from database.session import get_db
from database.models import ResearchJob
from schemas.job import ResearchRequest, ResearchResponse, ResearchStatusResponse
from services.research import run_research_background, subscribe, unsubscribe
from services.llm_usage import get_daily_usage, groq_daily_limit_per_key, today_key, utc_now

from sqlalchemy import select
from typing import List, Optional
from core.config import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "DeepSight Engine"}


def _split_api_keys(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\s,;]+", value or "") if part.strip()]


def _configured_groq_keys() -> list[str]:
    keys = []
    for name in ("GROQ_API_KEYS", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY"):
        keys.extend(_split_api_keys(getattr(settings, name, None) or ""))

    seen = set()
    deduped = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


@router.get("/status/ai")
async def ai_status():
    provider = "groq"
    model = "llama-3.1-8b-instant"
    api_keys = _configured_groq_keys()
    per_key_limit = groq_daily_limit_per_key()
    total_capacity = per_key_limit * max(1, len(api_keys))
    usage_rows = await get_daily_usage(provider, model, api_keys) if api_keys else {}
    used_tokens = sum(int(getattr(row, "tokens_used", 0) or 0) for row in usage_rows.values())
    remaining_percent = max(0, min(100, round(100 - ((used_tokens / total_capacity) * 100))))

    now = utc_now()
    blocked_keys = [
        row for row in usage_rows.values()
        if getattr(row, "blocked_until", None) and row.blocked_until > now
    ]

    llm_healthy = bool(api_keys) and len(blocked_keys) < len(api_keys) and remaining_percent > 0
    search_healthy = bool(getattr(settings, "TAVILY_API_KEY", None))
    severity = "green"
    headline = "DeepSight AI Status"
    advisory = ""

    if not llm_healthy or not search_healthy:
        severity = "red"
        advisory = "DeepSight is temporarily unable to process new research requests"
    elif remaining_percent <= 10:
        severity = "yellow"
        advisory = "Heavy research requests may be delayed."

    return {
        "headline": headline,
        "severity": severity,
        "llm_provider": "Healthy" if llm_healthy else "Needs attention",
        "daily_ai_capacity_remaining_percent": remaining_percent,
        "daily_ai_capacity_label": f"{remaining_percent}% Remaining",
        "search_provider": "Healthy" if search_healthy else "Needs attention",
        "advisory": advisory,
        "provider": "Groq",
        "model": model,
        "configured_keys": len(api_keys),
        "daily_token_limit_per_key": per_key_limit,
        "tokens_used_today": used_tokens,
        "date": today_key(),
    }

async def get_current_user_email(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None
) -> str:
    """
    Dependency to authenticate users using Google OAuth ID tokens or a Demo Token.
    Returns the user's verified email.
    """
    auth_token = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization.split(" ")[1]
    elif token:
        auth_token = token
        
    if not auth_token or auth_token == "null" or auth_token == "undefined":
        raise HTTPException(status_code=401, detail="Missing authorization token")
        
    # Check for presentation/demo token (e.g. mock:demo@deepsight.ai)
    if auth_token.startswith("mock:"):
        return auth_token.split("mock:")[1]
        
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        # If client ID is not configured in .env, we allow using the token directly as email
        # to ensure the LinkedIn live demo works out-of-the-box.
        return auth_token
        
    try:
        idinfo = id_token.verify_oauth2_token(auth_token, google_requests.Request(), client_id)
        return idinfo['email']
    except Exception as e:
        # Fallback for local demo run if Client ID is configured but token is local email
        if not auth_token.strip().startswith("AIza") and "@" in auth_token: 
            return auth_token
        raise HTTPException(status_code=401, detail=f"Invalid Google Token: {str(e)}")

@router.get("/config")
async def get_app_config():
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID
    }

@router.get("/research", response_model=List[ResearchResponse])
async def list_research_jobs(
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    # Filter jobs: show user's own jobs, or legacy jobs with no email (public fallback)
    result = await db.execute(
        select(ResearchJob)
        .where((ResearchJob.user_email == email) | (ResearchJob.user_email == None))
        .order_by(ResearchJob.created_at.desc())
    )
    jobs = result.scalars().all()
    return jobs

@router.post("/research", response_model=ResearchResponse)
async def create_research_job(
    request: ResearchRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    # Safety Check Guardrails
    sensitive_keywords = [
        'race', 'sex', 'nudity', 'adult content', 'pornography', 'porn', 
        'hate speech', 'discrimination', 'discriminate', 'discriminatory', 
        'explicit content', 'nude', 'sexual'
    ]
    import re
    goal_lower = request.goal.lower()
    has_sensitive = any(re.search(rf"\b{kw}\b", goal_lower) for kw in sensitive_keywords)
    if has_sensitive:
        raise HTTPException(
            status_code=400,
            detail="I cannot answer this query due to safety guidelines."
        )

    # Create job in DB
    new_job = ResearchJob(
        goal=request.goal,
        status="PENDING",
        user_email=email
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    # Start background task
    asyncio.create_task(
        run_research_background(
            job_id=new_job.id,
            goal=request.goal,
            system_prompt=request.system_prompt,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
            llm_api_key=request.llm_api_key,
            search_api_key=request.search_api_key
        )
    )
    
    return ResearchResponse(
        id=new_job.id,
        goal=new_job.goal,
        status=new_job.status,
        created_at=new_job.created_at
    )

@router.get("/research/{job_id}", response_model=ResearchStatusResponse)
async def get_research_status(
    job_id: str, 
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email)
):
    job = await db.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Check ownership
    if job.user_email and job.user_email != email:
        raise HTTPException(status_code=403, detail="Not authorized to view this research job")
        
    return ResearchStatusResponse(
        id=job.id,
        goal=job.goal,
        status=job.status,
        final_report=job.final_report,
        created_at=job.created_at
    )


def _report_to_markdown(report) -> tuple[str, str]:
    title = "Research Report"
    markdown = ""

    if isinstance(report, str):
        try:
            report = json.loads(report)
        except Exception:
            markdown = report

    if isinstance(report, dict):
        title = report.get("title") or title
        markdown = report.get("report_markdown") or report.get("markdown") or ""
        if markdown.strip().startswith("{"):
            try:
                nested = json.loads(markdown)
                if isinstance(nested, dict):
                    title = nested.get("title") or title
                    markdown = nested.get("report_markdown") or nested.get("markdown") or markdown
            except Exception:
                pass

    markdown = str(markdown or "").strip()
    if not markdown:
        markdown = title
    if not re.match(r"^\s*#\s+", markdown):
        markdown = f"# {title}\n\n{markdown}"
    return title, markdown


def _safe_filename(value: str, suffix: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())[:80].strip("-") or "research-report"
    return f"{name}.{suffix}"


def _markdown_blocks(markdown: str) -> list[tuple[str, str]]:
    blocks = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            blocks.append(("blank", ""))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            blocks.append((f"h{min(3, len(heading.group(1)))}", heading.group(2).strip()))
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            blocks.append(("bullet", bullet.group(1).strip()))
            continue
        numbered = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if numbered:
            blocks.append(("number", numbered.group(1).strip()))
            continue
        blocks.append(("p", line.strip()))
    return blocks


def _plain_text_from_markdown(markdown: str) -> str:
    lines = []
    for kind, text in _markdown_blocks(markdown):
        if kind == "blank":
            lines.append("")
        elif kind.startswith("h"):
            lines.append(text.upper() if kind == "h1" else text)
        elif kind == "bullet":
            lines.append(f"- {text}")
        elif kind == "number":
            lines.append(f"1. {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(markdown: str) -> bytes:
    plain = _plain_text_from_markdown(markdown)
    wrapped_lines = []
    for line in plain.splitlines():
        if not line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(line, width=95, replace_whitespace=False) or [""])

    lines_per_page = 48
    pages = [wrapped_lines[i:i + lines_per_page] for i in range(0, len(wrapped_lines), lines_per_page)] or [[]]

    objects: list[str] = ["", "", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    font_id = 3
    page_ids = []

    for page_lines in pages:
        commands = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for idx, line in enumerate(page_lines):
            safe_line = _pdf_escape(line[:180])
            if idx == 0:
                commands.append(f"({safe_line}) Tj")
            else:
                commands.append(f"T* ({safe_line}) Tj")
        commands.append("ET")
        stream = "\n".join(commands)
        content = f"<< /Length {len(stream.encode('utf-8'))} >>\nstream\n{stream}\nendstream"
        objects.append(content)
        content_id = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(len(objects))

    objects[0] = "<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"

    body = io.BytesIO()
    body.write(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(body.tell())
        body.write(f"{idx} 0 obj\n{obj}\nendobj\n".encode("utf-8"))

    xref_offset = body.tell()
    body.write(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    body.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    body.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("utf-8")
    )
    return body.getvalue()


def _docx_paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    escaped = html.escape(text, quote=False)
    return f"<w:p>{style_xml}<w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>"


def _build_docx(markdown: str) -> bytes:
    paragraphs = []
    for kind, text in _markdown_blocks(markdown):
        if kind == "blank":
            paragraphs.append("<w:p/>")
        elif kind == "h1":
            paragraphs.append(_docx_paragraph(text, "Heading1"))
        elif kind == "h2":
            paragraphs.append(_docx_paragraph(text, "Heading2"))
        elif kind == "h3":
            paragraphs.append(_docx_paragraph(text, "Heading3"))
        elif kind == "bullet":
            paragraphs.append(_docx_paragraph(f"- {text}"))
        elif kind == "number":
            paragraphs.append(_docx_paragraph(f"1. {text}"))
        else:
            paragraphs.append(_docx_paragraph(text))

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(paragraphs)}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return output.getvalue()


@router.get("/research/{job_id}/export/{export_format}")
async def export_research_report(
    job_id: str,
    export_format: str,
    db: AsyncSession = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    job = await db.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_email and job.user_email != email:
        raise HTTPException(status_code=403, detail="Not authorized to export this research job")
    if not job.final_report:
        raise HTTPException(status_code=400, detail="This research report is not ready for export yet.")

    title, markdown = _report_to_markdown(job.final_report)
    export_format = export_format.lower()
    if export_format == "pdf":
        filename = _safe_filename(title, "pdf")
        return Response(
            content=_build_pdf(markdown),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if export_format == "docx":
        filename = _safe_filename(title, "docx")
        return Response(
            content=_build_docx(markdown),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(status_code=400, detail="Unsupported export format. Use pdf or docx.")

@router.get("/research/{job_id}/stream")
async def stream_research_status(
    job_id: str, 
    request: Request,
    email: str = Depends(get_current_user_email)
):
    """
    Server Sent Events endpoint for streaming research progress.
    """
    async def event_generator():
        q = await subscribe(job_id)
        try:
            while True:
                # If client closes connection, request.is_disconnected() will be True eventually
                if await request.is_disconnected():
                    break
                    
                try:
                    # Wait for an event with a timeout to check for disconnects
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(event)
                    }
                    if event.get("node") in ["end", "error"]:
                        break
                except asyncio.TimeoutError:
                    pass
        finally:
            unsubscribe(job_id, q)

    return EventSourceResponse(event_generator())
