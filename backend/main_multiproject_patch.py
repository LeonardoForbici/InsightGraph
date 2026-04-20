"""
main_multiproject_patch.py
==========================
Instruções de integração — NÃO importar em produção.
Este arquivo documenta exatamente o que foi adicionado ao main.py
para integrar o WorkspaceSupervisor e o projects_router.

Mudanças aplicadas em main.py (branch feature/live-multiproject-engine):

1. IMPORTS (após o bloco de imports existente, antes de 'configure_logging()'):

    from workspace_supervisor import WorkspaceSupervisor
    from projects_router import router as projects_router

2. VARIÁVEL GLOBAL (junto dos outros globals como event_engine, alert_engine):

    workspace_supervisor: Optional[WorkspaceSupervisor] = None

3. LIFESPAN STARTUP (após 'event_stream.start_broadcast_loop()'):

    # Multi-project engine — boot WorkspaceSupervisor
    global workspace_supervisor
    workspace_supervisor = WorkspaceSupervisor(
        registry_path=Path(os.getenv("PROJECTS_REGISTRY_PATH", "projects_registry.json")),
        event_stream=event_stream,
        ollama_url=OLLAMA_URL,
        ollama_model=OLLAMA_FAST_MODEL,
    )
    await workspace_supervisor.boot()
    logger.info(
        "WorkspaceSupervisor booted: %d workers iniciados",
        len(workspace_supervisor.workers),
    )

4. LIFESPAN TEARDOWN (antes de 'await event_stream.stop_broadcast_loop()'):

    # Stop WorkspaceSupervisor
    if workspace_supervisor:
        await workspace_supervisor.shutdown()
        logger.info("WorkspaceSupervisor encerrado")

5. ROUTER REGISTRATION (após 'app.add_middleware(CORSMiddleware, ...)'):

    app.include_router(projects_router, prefix="/api")
"""
