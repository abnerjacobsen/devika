# Migração de Flask para FastAPI

Este documento descreve **todas as etapas, decisões e alterações** realizadas para substituir o framework web **Flask** por **FastAPI** no projeto **Devika**.  
Ele é destinado a desenvolvedores do repositório que desejam entender a refatoração, atualizar seus ambientes locais ou contribuir com novas features usando FastAPI.

---

## 1. Resumo das Mudanças

| Área                     | Descrição                                                                                              |
|--------------------------|---------------------------------------------------------------------------------------------------------|
| Framework Web           | Substituído `Flask` + `Flask-SocketIO` por `FastAPI` + `python-socketio` (modo **ASGI**).                |
| Dependências            | Removidas: `flask`, `flask-cors`, `Flask-SocketIO`.<br>Adicionadas: `fastapi`, `uvicorn[standard]`, `python-socketio`, `python-multipart`. |
| Arquitetura             | Blueprints transformados em **Routers** FastAPI. Rotas síncronas convertidas para funções **async**.     |
| WebSockets              | Criado `src/socket_instance.py` usando `AsyncServer` do `python-socketio` com app ASGI montável.         |
| Logging                 | Decorador `route_logger` adaptado para trabalhar com `fastapi.Request` e `starlette.responses.Response`. |
| CORS                    | Uso de `CORSMiddleware` nativo.                                                                         |
| Execução                | Troca do servidor `Flask`/`gevent` por `uvicorn`.                                                       |

---

## 2. Arquivos Modificados

| Arquivo | Principais alterações |
|---------|-----------------------|
| **`requirements.txt`** | Remoção de libs Flask, inclusão do stack FastAPI. |
| **`devika.py`** | Reescrito como **entry-point FastAPI**: configuração de CORS, montagem do Socket.IO ASGI, conversão de todas rotas. |
| **`src/socket_instance.py`** | Reimplementado com `python-socketio.AsyncServer`; exporta `socketio_app` para ser `mount` em FastAPI. |
| **`src/apis/project.py`** | Blueprint → `APIRouter`; uso de Pydantic (`ProjectCreate`, `ProjectDelete`); sanitização manual de nomes de projeto. |
| **`src/logger.py`** | `route_logger` agora identifica `fastapi.Request`, lê corpo de resposta via `StarletteResponse`. |
| **Outros** | Imports atualizados em módulos que referenciavam Flask (`from flask import ...` → `from fastapi ...`). |

---

## 3. Como Executar a Aplicação com FastAPI

1. **Clonar/atualizar repositório** e trocar para a branch que contém a migração (`feature/migrate-flask-to-fastapi`) ou `main` caso já tenha sido _mergeada_.

2. **Criar ambiente virtual** (recomendado):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Instalar dependências**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Executar servidor**:
   ```bash
   uvicorn devika:app --host 0.0.0.0 --port 1337
   ```
   - O argumento `--reload` pode ser adicionado para _hot reload_ em ambiente de desenvolvimento.

5. **Acessar documentação automática**:
   - Swagger UI: `http://localhost:1337/docs`
   - Redoc: `http://localhost:1337/redoc`

6. **WebSockets**: continuam disponíveis em `/ws` via Socket.IO.

---

## 4. Diferenças Importantes Entre Flask e FastAPI

| Tema | Flask | FastAPI |
|------|-------|---------|
| Modelo de Concurrency | WSGI (síncrono) + gevent/eventlet para _async_ | ASGI nativo, suporte a **async/await** |
| Tipagem | Opcional | Forte uso de **type hints** & **Pydantic** |
| Docs HTTP | Extensões de terceiros | **OpenAPI/Swagger** gerados automaticamente |
| Performance | Boa, mas limitada ao modelo WSGI | Melhor aproveitamento de IO assíncrono |
| WebSockets | Requer extensões (Flask-SocketIO) | Integrável por `python-socketio`, `fastapi_websocket`, etc. |
| Middleware | WSGI | Starlette Middleware (ASGI) |

**Nota:** `gevent` não é mais necessário; `uvicorn` fornece loop de eventos eficiente (default `uvloop`).

---

## 5. Atualizando Dependências

```bash
# Desinstalar pacotes obsoletos (opcional)
pip uninstall flask flask-cors Flask-SocketIO -y

# Instalar dependências FastAPI já listadas no requirements
pip install -r requirements.txt
```

Caso use **Poetry** ou **Pipenv**, atualize os manifests correspondentes.

---

## 6. Possíveis Problemas & Soluções

| Problema | Causa | Solução Recomendada |
|----------|-------|---------------------|
| **Funções bloqueantes** travando loop async | Código que faz I/O síncrono (ex.: chamadas de rede, disk I/O pesado) | Rodar em threads (`run_in_executor`) ou usar bibliotecas assíncronas. |
| **Erro `RuntimeError: Task attached to a different loop`** | Tentativa de emitir Socket.IO fora do loop corrente | Utilizar `asyncio.create_task()` (já implementado em `emit_agent`). |
| **Headers CORS ausentes** | Domínio cliente não configurado | Adicionar domínio à lista `allow_origins` em `devika.py`. |
| **Uploads maiores que 30MB falham** | Limite default do Uvicorn/Starlette | Ajustar `--limit-concurrency`, `--limit-max-requests` ou stream manualmente. |
| **PDF/ZIP download não funciona** | Caminho incorreto após sanitização | Verificar `Config().get_pdfs_dir()` e permissões de arquivo. |

---

## 7. Benefícios Obtidos com a Migração

1. **Desempenho Superior** — FastAPI + `uvicorn` oferecem _throughput_ e latência menores mesmo em workloads I/O-bound.  
2. **Suporte nativo a `async`** — facilita chamadas paralelas a LLMs, browsers ou file system sem _blocking_.  
3. **Documentação Automática** — APIs expostas com OpenAPI/Swagger sem configuração adicional.  
4. **Validação Robusta** — Pydantic valida payloads de entrada, reduzindo erros de runtime.  
5. **Tipagem & Autocomplete** — Type hints melhoram DX nos IDEs e previnem bugs.  
6. **Simplificação** — elimina dependências extras (`Flask-Cors`, `Flask-SocketIO`, `gevent`), reduzindo _overhead_ de manutenção.  
7. **Escalabilidade** — execução em workers ASGI independentes com `gunicorn -k uvicorn.workers.UvicornWorker` permite _scale out_ simples.

---

**Parabéns!** A aplicação Devika agora roda sobre FastAPI. A comunidade agradece qualquer feedback ou PR de melhoria.  
Em caso de dúvidas, consulte a equipe ou abra uma _issue_.

