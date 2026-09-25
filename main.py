import os
import uvicorn
import config


def main() -> None:
    reload = os.getenv("UNDARR_RELOAD", "").lower() in ("1", "true")
    uv_config = uvicorn.Config(
        "app.server:app",
        host=config.HOST,
        port=config.PORT,
        reload=reload,
    )
    server = uvicorn.Server(uv_config)
    server.run()


if __name__ == "__main__":
    main()
