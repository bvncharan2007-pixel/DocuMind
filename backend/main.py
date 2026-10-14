from pathlib import Path

frontend_dist = Path(__file__).resolve().parent.parent / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}")
    async def serve_frontend_routes(full_path: str):
        file_path = frontend_dist / full_path

        if file_path.is_file():
            return FileResponse(file_path)

        return FileResponse(frontend_dist / "index.html")