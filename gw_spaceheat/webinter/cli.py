import asyncio
import logging
from pathlib import Path
from typing import Annotated
from typing import Optional

import dotenv
import rich
import typer
from aiohttp import web, WSMsgType
from aiohttp.web import Request, WebSocketResponse

from webinter.settings import WebInterSettings
from webinter.websocket_server import WebInterMQTTBridge

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks Scada Web Interface",
)

DEFAULT_TARGET: str = "d1.isone.me.versant.keene.orange.scada"

def get_settings(
    target: str = "",
    env_file: str = ".env",
    verbose: int = 0,
    paho_verbose: int = 0,
    web_port: int = 8080,
    web_host: str = "localhost"
) -> WebInterSettings:
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    print("DEBUG: Creating WebInterSettings...")
    settings = WebInterSettings(
        _env_file=dotenv.find_dotenv(env_file),
    )
    print("DEBUG: Settings created, calling update_paths_name...")
    settings = settings.update_paths_name("webinter")
    print("DEBUG: update_paths_name completed")
    
    if target:
        settings.target_gnode = target
    elif not settings.target_gnode:
        settings.target_gnode = DEFAULT_TARGET
    
    settings.web_port = web_port
    settings.web_host = web_host
    
    if verbose:
        if verbose == 1:
            verbosity = logging.INFO
        else:
            verbosity = logging.DEBUG
        settings.verbosity = verbosity
    if paho_verbose:
        if paho_verbose == 1:
            paho_verbosity = logging.INFO
        else:
            paho_verbosity = logging.DEBUG
        settings.paho_verbosity = paho_verbosity
    return settings

# Global bridge instance
bridge: Optional[WebInterMQTTBridge] = None

async def websocket_handler(request: Request) -> WebSocketResponse:
    """Handle WebSocket connections"""
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

async def index_handler(request: Request) -> web.Response:
    """Serve the main HTML page"""
    html_path = Path(__file__).parent / "index.html"
    with open(html_path, 'r') as f:
        html_content = f.read()
    
    return web.Response(text=html_content, content_type='text/html')

async def init_app(settings: WebInterSettings) -> web.Application:
    """Initialize the web application"""
    global bridge
    
    # Create MQTT bridge
    bridge = WebInterMQTTBridge(settings)
    
    # Create web app
    app = web.Application()
    
    # Add routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/ws', websocket_handler)
    
    # Start MQTT client
    bridge.start_mqtt()
    
    return app

@app.command()
def serve(
    target: str = "",
    env_file: str = ".env",
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True
        )
    ] = 0,
    paho_verbose: Annotated[
        int,
        typer.Option(
            "--paho-verbose", count=True
        )
    ] = 0,
    web_port: Annotated[
        int,
        typer.Option(
            "--port", "-p"
        )
    ] = 8080,
    web_host: Annotated[
        str,
        typer.Option(
            "--host"
        )
    ] = "localhost"
) -> None:
    """Start the web interface server."""
    settings = get_settings(target, env_file, verbose, paho_verbose, web_port, web_host)
    rich.print(settings)
    
    # Setup logging
    logging.basicConfig(level=settings.verbosity)
    
    async def run_server():
        app = await init_app(settings)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.web_host, settings.web_port)
        await site.start()
        
        rich.print(f"Web interface running at http://{settings.web_host}:{settings.web_port}")
        rich.print("Press Ctrl+C to stop")
        
        try:
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            rich.print("Shutting down...")
        finally:
            # Clean up bridge resources
            if bridge:
                await bridge.cleanup()
            
            # Clean up aiohttp server
            await site.stop()
            await runner.cleanup()
    
    asyncio.run(run_server())

@app.command()
def config(
    target: str = "",
    env_file: str = ".env",
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True
        )
    ] = 0,
    paho_verbose: Annotated[
        int,
        typer.Option(
            "--paho-verbose", count=True
        )
    ] = 0
) -> None:
    """Show web interface settings."""
    settings = get_settings(target, env_file, verbose, paho_verbose)
    rich.print(
        f"Env file: <{env_file}>  exists: {bool(env_file and Path(env_file).exists())}"
    )
    rich.print(settings)
    missing_tls_paths_ = settings.check_tls_paths_present(raise_error=False)
    if missing_tls_paths_:
        rich.print(missing_tls_paths_)

def version_callback(value: bool):
    if value:
        print("gws webinter 0.1.0")
        raise typer.Exit()

@app.callback()
def _main(
    _version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit."
        ),
    ] = None,
) -> None: ...

if __name__ == "__main__":
    app()
