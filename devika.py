#  ──────────────────────────────────────────────────────────────────────────────
#  Devika – main entry-point (migrated from Flask to FastAPI)
#  KEEP THE IMPORT/INIT ORDER – the initial comment above is still valid, but
#  we no longer need gevent monkey-patching because FastAPI/uvicorn natively
#  supports asynchronous I/O.
#  ──────────────────────────────────────────────────────────────────────────────
from src.init import init_devika
init_devika()


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from src.socket_instance import socketio, socketio_app, emit_agent
import os
from threading import Thread
import tiktoken

from src.apis.project import router as project_router
from src.config import Config
from src.logger import Logger, route_logger
from src.project import ProjectManager
from src.state import AgentState
from src.agents import Agent
from src.llm import LLM


app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register HTTP routers
app.include_router(project_router)

# Mount Socket.IO ASGI application
app.mount("/ws", socketio_app)


TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")

os.environ["TOKENIZERS_PARALLELISM"] = "false"

manager = ProjectManager()
AgentState = AgentState()
config = Config()
logger = Logger()


# initial socket
@socketio.on('socket_connect')
def test_connect(data):
    print("Socket connected :: ", data)
    emit_agent("socket_response", {"data": "Server Connected"})


@app.get("/api/data")
@route_logger(logger)
async def data(request: Request):
    project = manager.get_project_list()
    models = LLM().list_models()
    search_engines = ["Bing", "Google", "DuckDuckGo"]
    return JSONResponse({"projects": project, "models": models, "search_engines": search_engines})


@app.post("/api/messages")
async def get_messages(request: Request):
    data = await request.json()
    project_name = data.get("project_name")
    messages = manager.get_messages(project_name)
    return JSONResponse({"messages": messages})


# Main socket
@socketio.on('user-message')
def handle_message(data):
    logger.info(f"User message: {data}")
    message = data.get('message')
    base_model = data.get('base_model')
    project_name = data.get('project_name')
    search_engine = data.get('search_engine').lower()

    agent = Agent(base_model=base_model, search_engine=search_engine)

    state = AgentState.get_latest_state(project_name)
    if not state:
        thread = Thread(target=lambda: agent.execute(message, project_name))
        thread.start()
    else:
        if AgentState.is_agent_completed(project_name):
            thread = Thread(target=lambda: agent.subsequent_execute(message, project_name))
            thread.start()
        else:
            emit_agent("info", {"type": "warning", "message": "previous agent doesn't completed it's task."})
            last_state = AgentState.get_latest_state(project_name)
            if last_state["agent_is_active"] or not last_state["completed"]:
                thread = Thread(target=lambda: agent.execute(message, project_name))
                thread.start()
            else:
                thread = Thread(target=lambda: agent.subsequent_execute(message, project_name))
                thread.start()

@app.post("/api/is-agent-active")
@route_logger(logger)
async def is_agent_active(request: Request):
    data = await request.json()
    project_name = data.get("project_name")
    is_active = AgentState.is_agent_active(project_name)
    return JSONResponse({"is_active": is_active})


@app.post("/api/get-agent-state")
@route_logger(logger)
async def get_agent_state(request: Request):
    data = await request.json()
    project_name = data.get("project_name")
    agent_state = AgentState.get_latest_state(project_name)
    return JSONResponse({"state": agent_state})


@app.get("/api/get-browser-snapshot")
@route_logger(logger)
async def browser_snapshot(snapshot_path: str):
    return FileResponse(snapshot_path, filename=os.path.basename(snapshot_path))


@app.get("/api/get-browser-session")
@route_logger(logger)
async def get_browser_session(project_name: str):
    agent_state = AgentState.get_latest_state(project_name)
    if not agent_state:
        return JSONResponse({"session": None})
    else:
        browser_session = agent_state["browser_session"]
        return JSONResponse({"session": browser_session})


@app.get("/api/get-terminal-session")
@route_logger(logger)
async def get_terminal_session(project_name: str):
    agent_state = AgentState.get_latest_state(project_name)
    if not agent_state:
        return JSONResponse({"terminal_state": None})
    else:
        terminal_state = agent_state["terminal_session"]
        return JSONResponse({"terminal_state": terminal_state})


@app.post("/api/run-code")
@route_logger(logger)
async def run_code(request: Request):
    data = await request.json()
    project_name = data.get("project_name")
    code = data.get("code")
    # TODO: Implement code execution logic
    return JSONResponse({"message": "Code execution started"})


@app.post("/api/calculate-tokens")
@route_logger(logger)
async def calculate_tokens(request: Request):
    data = await request.json()
    prompt = data.get("prompt")
    tokens = len(TIKTOKEN_ENC.encode(prompt))
    return JSONResponse({"token_usage": tokens})


@app.get("/api/token-usage")
@route_logger(logger)
async def token_usage(project_name: str):
    token_count = AgentState.get_latest_token_usage(project_name)
    return JSONResponse({"token_usage": token_count})


@app.get("/api/logs")
async def real_time_logs():
    log_file = logger.read_log_file()
    return JSONResponse({"logs": log_file})


@app.post("/api/settings")
@route_logger(logger)
async def set_settings(request: Request):
    data = await request.json()
    config.update_config(data)
    return JSONResponse({"message": "Settings updated"})


@app.get("/api/settings")
@route_logger(logger)
async def get_settings():
    configs = config.get_config()
    return JSONResponse({"settings": configs})


@app.get("/api/status")
@route_logger(logger)
async def status():
    return JSONResponse({"status": "server is running!"})

if __name__ == "__main__":
    logger.info("Devika is up and running!")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1337, reload=False)
