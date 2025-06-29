#  ──────────────────────────────────────────────────────────────────────────────
#  Devika – main entry-point (migrated from Flask to FastAPI)
#  KEEP THE IMPORT/INIT ORDER – the initial comment above is still valid, but
#  we no longer need gevent monkey-patching because FastAPI/uvicorn natively
#  supports asynchronous I/O.
#  ──────────────────────────────────────────────────────────────────────────────
from src.init import init_devika
init_devika()


from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body
from src.socket_instance import socketio, emit_agent
import os
from threading import Thread
import tiktoken
import asyncio

from src.apis.project import router as project_router
from src.config import Config
from src.logger import Logger, route_logger
from src.project import ProjectManager
from src.state import AgentState
from src.agents import Agent
from src.llm import LLM

# Imports for Freeact integration
from freeact import CodeActAgent, LiteCodeActModel, execution_environment
from freeact.agent import CodeActModelTurn, CodeExecution  # Importando classes para processar o stream
from rich.console import Console


app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3000",
        "http://localhost:3000",
        "https://localhost:3001",
        "http://localhost:3001",
        "https://0.0.0.0:3000",
        "http://0.0.0.0:3000",
        "https://0.0.0.0:3001",
        "http://0.0.0.0:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register HTTP routers
app.include_router(project_router)

TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")

os.environ["TOKENIZERS_PARALLELISM"] = "false"

manager = ProjectManager()
config = Config()
logger = Logger()
agent_state_manager = AgentState()

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
# FreeAct can take longer than standard LLM inference because it may need to
# install packages, download data sets or run heavy Python code inside the
# ipybox container.  We therefore allow a bigger timeout window (default
# 300 s).  The value can be overridden via the `FREEACT_TIMEOUT` environment
# variable without changing code.
FREEACT_TIMEOUT: int = int(os.getenv("FREEACT_TIMEOUT", "300"))



# initial socket
@socketio.on('socket_connect')
def test_connect(sid, data):
    print("Socket connected :: ", data)
    emit_agent("socket_response", {"data": "Server Connected"})


@app.get("/api/data")
@route_logger(logger)
def data(request: Request):
    project = manager.get_project_list()
    models = LLM().list_models()
    search_engines = ["Bing", "Google", "DuckDuckGo"]
    return {"projects": project, "models": models, "search_engines": search_engines}


@app.post("/api/messages")
@route_logger(logger)
def get_messages(request: Request, data: dict = Body(...)):
    """
    Return all messages for the requested project.
    """
    project_name = data.get("project_name")
    messages = manager.get_messages(project_name)
    return {"messages": messages}


# Main socket
@socketio.on('user-message')
def handle_message(sid, data):
    logger.info(f"User message: {data}")
    message = data.get('message')
    base_model = data.get('base_model')
    project_name = data.get('project_name')
    search_engine = data.get('search_engine').lower()

    agent = Agent(base_model=base_model, search_engine=search_engine)

    state = agent_state_manager.get_latest_state(project_name)
    if not state:
        thread = Thread(target=lambda: agent.execute(message, project_name))
        thread.start()
    else:
        if agent_state_manager.is_agent_completed(project_name):
            thread = Thread(target=lambda: agent.subsequent_execute(message, project_name))
            thread.start()
        else:
            emit_agent("info", {"type": "warning", "message": "previous agent doesn't completed it's task."})
            last_state = agent_state_manager.get_latest_state(project_name)
            if last_state["agent_is_active"] or not last_state["completed"]:
                thread = Thread(target=lambda: agent.execute(message, project_name))
                thread.start()
            else:
                thread = Thread(target=lambda: agent.subsequent_execute(message, project_name))
                thread.start()

@app.post("/api/is-agent-active")
@route_logger(logger)
def is_agent_active(request: Request, data: dict = Body(...)):
    project_name = data.get("project_name")
    is_active = agent_state_manager.is_agent_active(project_name)
    return {"is_active": is_active}


@app.post("/api/get-agent-state")
@route_logger(logger)
def get_agent_state(request: Request, data: dict = Body(...)):
    project_name = data.get("project_name")
    agent_state = agent_state_manager.get_latest_state(project_name)
    return {"state": agent_state}


@app.get("/api/get-browser-snapshot")
@route_logger(logger)
def browser_snapshot(request: Request, snapshot_path: str):
    return FileResponse(snapshot_path, filename=os.path.basename(snapshot_path))


@app.get("/api/get-browser-session")
@route_logger(logger)
def get_browser_session(request: Request, project_name: str):
    agent_state = agent_state_manager.get_latest_state(project_name)
    if not agent_state:
        return {"session": None}
    else:
        browser_session = agent_state["browser_session"]
        return {"session": browser_session}


@app.get("/api/get-terminal-session")
@route_logger(logger)
def get_terminal_session(request: Request, project_name: str):
    agent_state = agent_state_manager.get_latest_state(project_name)
    if not agent_state:
        return {"terminal_state": None}
    else:
        terminal_state = agent_state["terminal_session"]
        return {"terminal_state": terminal_state}


@app.post("/api/run-code")
@route_logger(logger)
def run_code(request: Request, data: dict = Body(...)):
    project_name = data.get("project_name")
    code = data.get("code")
    # TODO: Implement code execution logic
    return {"message": "Code execution started"}


@app.post("/api/calculate-tokens")
@route_logger(logger)
def calculate_tokens(request: Request, data: dict = Body(...)):
    prompt = data.get("prompt")
    tokens = len(TIKTOKEN_ENC.encode(prompt))
    return {"token_usage": tokens}


@app.get("/api/token-usage")
@route_logger(logger)
def token_usage(request: Request, project_name: str):
    token_count = agent_state_manager.get_latest_token_usage(project_name)
    return {"token_usage": token_count}


@app.get("/api/logs")
def real_time_logs():
    log_file = logger.read_log_file()
    return {"logs": log_file}


@app.post("/api/settings")
@route_logger(logger)
def set_settings(request: Request, data: dict = Body(...)):
    config.update_config(data)
    return {"message": "Settings updated"}


@app.get("/api/settings")
@route_logger(logger)
def get_settings(request: Request):
    configs = config.get_config()
    return {"settings": configs}


@app.get("/api/status")
@route_logger(logger)
def status(request: Request):
    return {"status": "server is running!"}


# Custom WebSocket Console for Freeact
class WebSocketConsole(Console):
    def __init__(self, client_sid):
        super().__init__()
        self.client_sid = client_sid
        self.non_interactive = True  # Flag to indicate non-interactive mode

    def print(self, text, **kwargs):
        # Send output directly to WebSocket
        emit_agent("freeact_output", {"text": str(text)}, log=False)

    def input(self, prompt=""):
        # In non-interactive mode, don't prompt for input
        # Just log that input was requested but not provided
        logger.info(f"FreeAct requested input (non-interactive mode): {prompt}")
        emit_agent("freeact_info", {"message": "Agent requested input, but running in non-interactive mode"}, log=False)
        # Return a default value instead of empty string to avoid "non-empty message" errors
        return "continue"


# Function to run the freeact agent in a thread
def run_freeact_agent(message, project_name, client_sid):
    try:
        logger.info(f"Starting Freeact agent with message: {message} for sid: {client_sid}")
        emit_agent("freeact_status", {"status": "starting"}, log=False)

        async def run_agent():
            async with execution_environment(
                ipybox_tag="ghcr.io/gradion-ai/ipybox:basic",
            ) as env:
                async with env.code_provider() as provider:
                    # Register both **PubMed** and **Firecrawl** MCP servers
                    mcp_tool_names = await provider.register_mcp_servers(
                        {
                            "pubmed": {
                                "command": "uvx",
                                "args": ["--quiet", "pubmedmcp@0.1.3"],
                                "env": {"UV_PYTHON": "3.12"},
                            },
                            "firecrawl": {
                                "command": "npx",
                                "args": ["-y", "firecrawl-mcp"],
                                "env": {
                                    # Pass the API key from Devika configuration
                                    "FIRECRAWL_API_KEY": config.get_firecrawl_api_key()
                                },
                            },
                        }
                    )
                    skill_sources = await provider.get_sources(
                        module_names=["freeact_skills.search.google.stream.api"],
                        mcp_tool_names=mcp_tool_names,
                    )

                async with env.code_executor() as executor:
                    model = LiteCodeActModel(
                        model_name="gpt-4o-mini",
                        # Usa a chave configurada no sistema Devika
                        api_key=config.get_openai_api_key(),
                        reasoning_effort="low",
                        drop_params=True,
                        skill_sources=skill_sources,
                    )
                    agent = CodeActAgent(model=model, executor=executor)

                    # Executa o agente sem injetar um Console customizado.
                    # Isso evita que o objeto seja serializado em chamadas
                    # internas da biblioteca (problema JSON serializable).
                    try:
                        # Em vez de processar o resultado final, processamos o stream de atividades
                        # para separar Model response, Code action e Execution result
                        agent_turn = agent.run(user_query=message)

                        # Helper para consumir o stream
                        async def _consume_stream():
                            async for activity in agent_turn.stream():
                                # Processamos cada tipo de atividade e enviamos eventos específicos
                                if isinstance(activity, CodeActModelTurn):
                                    # Obtemos a resposta do modelo (pode ser um coroutine)
                                    response = (
                                        await activity.response()
                                        if asyncio.iscoroutinefunction(activity.response)
                                        else activity.response()
                                    )

                                    # Enviamos o texto da resposta do modelo
                                    if response.text:
                                        emit_agent(
                                            "freeact_model_response",
                                            {"text": response.text},
                                            log=False,
                                        )

                                    # Se houver código, enviamos como Code action
                                    if response.code:
                                        emit_agent(
                                            "freeact_code_action",
                                            {"code": response.code},
                                            log=False,
                                        )

                                    # Enviamos estatísticas de uso se disponíveis
                                    if hasattr(response, "usage") and response.usage:
                                        usage_dict = (
                                            response.usage
                                            if isinstance(response.usage, dict)
                                            else response.usage.__dict__
                                        )
                                        emit_agent(
                                            "freeact_usage",
                                            {"usage": usage_dict},
                                            log=False,
                                        )

                                elif isinstance(activity, CodeExecution):
                                    # Processamos o resultado da execução
                                    result = (
                                        await activity.result()
                                        if asyncio.iscoroutinefunction(activity.result)
                                        else activity.result()
                                    )

                                    # Enviamos o resultado da execução
                                    emit_agent(
                                        "freeact_execution_result",
                                        {"result": result.text},
                                        log=False,
                                    )

                                    # Se houver imagens produzidas, enviamos informação
                                    if hasattr(result, "images") and result.images:
                                        paths = [str(path) for path in result.images.keys()]
                                        if paths:
                                            emit_agent(
                                                "freeact_images",
                                                {"paths": paths},
                                                log=False,
                                            )

                        # Aplicamos timeout ao consumo completo do stream
                        await asyncio.wait_for(_consume_stream(), timeout=FREEACT_TIMEOUT)

                    except asyncio.TimeoutError:
                        logger.error(
                            "FreeAct execution exceeded the configured "
                            f"timeout of {FREEACT_TIMEOUT} s."
                        )
                        emit_agent(
                            "freeact_error",
                            {
                                "error": (
                                    "A execução demorou demais e foi cancelada "
                                    f"({FREEACT_TIMEOUT} s). Tente simplificar a "
                                    "pergunta ou aumentar a variável "
                                    "`FREEACT_TIMEOUT`."
                                )
                            },
                            log=False,
                        )
                        return

        asyncio.run(run_agent())
        emit_agent("freeact_status", {"status": "completed"}, log=False)

    except Exception as e:
        logger.error(f"Freeact agent error: {str(e)}")
        emit_agent("freeact_error", {"error": str(e)}, log=False)


# New endpoint for Freeact agent
@app.post("/api/freeact-message")
@route_logger(logger)
def freeact_message(request: Request, data: dict = Body(...)):
    message = data.get("message")
    project_name = data.get("project_name")
    client_sid = data.get("sid")  # Expect sid in the request body

    if not message or not project_name or not client_sid:  # Check for sid
        return {"error": "Missing message, project_name, or sid"}

    logger.info(f"Received Freeact message: {message} for project {project_name} from sid: {client_sid}")

    # Start a thread to run the freeact agent
    # Pass the client_sid to the thread target
    thread = Thread(target=lambda: run_freeact_agent(message, project_name, client_sid))
    thread.start()

    return {"status": "Freeact agent started"}


# --------------------------------------------------------------------------- #
# Integrate Socket.IO at the *root* of the ASGI application instead of `/ws`.
# We first finish registering every FastAPI route on the existing ``app`` and
# only then wrap it with the Socket.IO ASGIApp.  This way the frontend can
# connect using the same base URL it already expects.
# --------------------------------------------------------------------------- #
from socketio import ASGIApp as _ASGIApp  # local import to avoid circular deps

# NOTE: re-assigning the variable ``app`` is safe because all route decorators
# above have already executed and attached their endpoints.
app = _ASGIApp(socketio, other_asgi_app=app)  # type: ignore[assignment]

if __name__ == "__main__":
    logger.info("Devika is up and running!")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1337, reload=False)
