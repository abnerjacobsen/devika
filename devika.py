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
import inspect

from src.apis.project import router as project_router
from src.config import Config
from src.logger import Logger, route_logger
from src.project import ProjectManager
from src.state import AgentState
from src.agents import Agent
from src.llm import LLM

# Imports for Freeact integration
from freeact import CodeActAgent, LiteCodeActModel, execution_environment
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
                    mcp_tool_names = await provider.register_mcp_servers(
                        {
                            "pubmed": {
                                "command": "uvx",
                                "args": ["--quiet", "pubmedmcp@0.1.3"],
                                "env": {"UV_PYTHON": "3.12"},
                            }
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
                    turn = agent.run(user_query=message)
                    
                    logger.debug(f"FreeAct turn object type: {type(turn)}")
                    logger.debug(f"FreeAct turn object attributes: {dir(turn)}")

                    # Process the turn object and send relevant messages via WebSocket
                    if not turn:
                        logger.debug("FreeAct turn object is None.")
                        return

                    # 1) Caso o objeto traga lista de mensagens estruturadas
                    if hasattr(turn, "messages") and turn.messages:
                        logger.debug("FreeAct turn has 'messages' attribute.")
                        for msg in turn.messages:
                            # Cada msg pode ser dict ou str
                            emit_agent(
                                "freeact_output",
                                {"text": msg if isinstance(msg, str) else str(msg)},
                                log=False,
                            )
                    # 2) Algumas versões expõem 'answer' ou 'content'
                    elif hasattr(turn, "answer") and turn.answer:
                        logger.debug("FreeAct turn has 'answer' attribute.")
                        emit_agent("freeact_output", {"text": str(turn.answer)}, log=False)
                    elif hasattr(turn, "content") and turn.content:
                        logger.debug("FreeAct turn has 'content' attribute.")
                        emit_agent("freeact_output", {"text": str(turn.content)}, log=False)
                    elif hasattr(turn, "response") and turn.response: # New check
                        logger.debug("FreeAct turn has 'response' attribute (method or value).")
                        response_obj = turn.response
                        # Se for um método/callable, execute-o e trate coroutines corretamente
                        if callable(response_obj):
                            try:
                                _tmp = response_obj()
                                # _tmp pode ser coroutine; se for, aguarde sua execução
                                if asyncio.iscoroutine(_tmp):
                                    response_obj = await _tmp
                                else:
                                    response_obj = _tmp
                            except Exception as exc:
                                logger.error(f"Error invoking turn.response(): {exc}")
                                response_obj = None

                        # Emit the obtained response if available
                        if response_obj is not None and str(response_obj).strip():
                            emit_agent("freeact_output", {"text": str(response_obj)}, log=False)
                        else:
                            logger.debug("FreeAct turn.response is None/empty after invocation, not emitting.")
                    elif hasattr(turn, "output") and turn.output: # New check
                        logger.debug("FreeAct turn has 'output' attribute.")
                        emit_agent("freeact_output", {"text": str(turn.output)}, log=False)
                    elif hasattr(turn, "result") and turn.result: # New check
                        logger.debug("FreeAct turn has 'result' attribute.")
                        emit_agent("freeact_output", {"text": str(turn.result)}, log=False)
                    elif callable(getattr(turn, "get_response", None)): # New check for method
                        logger.debug("FreeAct turn has 'get_response()' method.")
                        emit_agent("freeact_output", {"text": str(turn.get_response())}, log=False)
                    elif callable(getattr(turn, "get_output", None)): # New check for method
                        logger.debug("FreeAct turn has 'get_output()' method.")
                        emit_agent("freeact_output", {"text": str(turn.get_output())}, log=False)
                    # 3) Fallback – converte todo o objeto para string legível
                    else:
                        logger.debug("FreeAct turn has no known content attributes, falling back to str(turn).")
                        emit_agent("freeact_output", {"text": str(turn)}, log=False)

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
