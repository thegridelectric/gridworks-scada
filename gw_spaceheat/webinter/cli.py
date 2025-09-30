import asyncio
import logging
from typing import Annotated, Optional
import dotenv
import rich
import typer
from aiohttp import web
from aiohttp.web import Request, WebSocketResponse
from aiohttp_cors import setup as cors_setup, ResourceOptions
from webinter.settings import WebInterSettings
from webinter.websocket_server import WebInterMQTTBridge

# CLI app for handling command-line interface and arguments
cli_app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks Scada Web Interface",
)

# Global MQTT bridge instance for WebSocket communication
bridge: Optional[WebInterMQTTBridge] = None

def get_settings(
    target_gnode: str,
    env_file: str = ".env",
    verbose: int = 0,
    paho_verbose: int = 0,
    web_port: int = 8080,
    web_host: str = "localhost"
) -> WebInterSettings:
    """
    Get the settings for the web interface from the environment file, 
    and overwrite with command line arguments if provided.
    """
    settings = WebInterSettings(_env_file=dotenv.find_dotenv(env_file))
    settings = settings.update_paths_name("webinter")
    
    if target_gnode:
        settings.target_gnode = target_gnode
    settings.web_port = web_port
    settings.web_host = web_host
    settings.websocket_path = f'/ws{target_gnode.split('.')[-2]}'
    settings.verbosity = logging.INFO if verbose == 1 else logging.DEBUG
    settings.paho_verbosity = logging.INFO if paho_verbose == 1 else logging.DEBUG

    return settings

async def websocket_handler(request: Request) -> WebSocketResponse:
    """
    Handles WebSocket connections for the web interface.
    Establishes WebSocket connections and delegates message handling to the
    MQTT bridge.
    """
    ws = WebSocketResponse()
    await ws.prepare(request)
    
    if bridge:
        try:
            await bridge.websocket_handler(ws, request.path)
        except Exception as e:
            logging.getLogger(__name__).exception(f"WebSocket handler error: {e}")
            try:
                await ws.close()
            except Exception:
                pass
    
    return ws

async def init_web_app(settings: WebInterSettings) -> web.Application:
    """Start the MQTT connection and initialize the web app"""
    global bridge
    bridge = WebInterMQTTBridge(settings)
    bridge.start_mqtt()

    web_app = web.Application()
    
    # Configure CORS
    cors = cors_setup(web_app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add CORS to the WebSocket route
    cors.add(web_app.router.add_get(settings.websocket_path, websocket_handler))
    
    return web_app

# Register the serve command with the CLI app
@cli_app.command()
def serve(
    target: str = "",
    env_file: str = ".env",
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
    paho_verbose: Annotated[int, typer.Option("--paho-verbose", count=True)] = 0,
    web_port: Annotated[int, typer.Option("--port", "-p")] = 8080,
    web_host: Annotated[str, typer.Option("--host")] = "localhost"
) -> None:
    """Start the web interface server."""
    settings = get_settings(target, env_file, verbose, paho_verbose, web_port, web_host)
    rich.print(settings)
    
    # Setup logging
    logging.basicConfig(level=settings.verbosity)
    
    async def run_server():
        web_app = await init_web_app(settings)
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, settings.web_host, settings.web_port)
        await site.start()
        
        rich.print(f"Web interface running at http://{settings.web_host}:{settings.web_port}")
        rich.print("Press Ctrl+C to stop")
        
        try:
            await asyncio.Future()
        except KeyboardInterrupt:
            rich.print("Shutting down...")
        finally:
            if bridge:
                await bridge.cleanup()
            await site.stop()
            await runner.cleanup()
    
    asyncio.run(run_server())

if __name__ == "__main__":
    cli_app()
