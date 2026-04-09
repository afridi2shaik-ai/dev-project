from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

ui_router = APIRouter()
templates = Jinja2Templates(directory="src/app/templates")

# @ui_router.get("/", response_class=HTMLResponse, include_in_schema=False)
# async def home(request: Request):
#     return RedirectResponse(url="/client/")


@ui_router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def custom_docs(request: Request):
    return templates.TemplateResponse("stoplight_elements.html", {"request": request})


@ui_router.get("/websocket-client", response_class=HTMLResponse, include_in_schema=False)
async def websocket_client(request: Request):
    return templates.TemplateResponse("websocket_client.html", {"request": request})


@ui_router.get("/webrtc-client", response_class=HTMLResponse, include_in_schema=False)
async def webrtc_client(request: Request):
    return templates.TemplateResponse("webrtc_client.html", {"request": request})

@ui_router.get("/websocket-chat", response_class=HTMLResponse, include_in_schema=False)
async def websocket_chat(request: Request):
    return templates.TemplateResponse("websocket_chat.html", {"request": request})