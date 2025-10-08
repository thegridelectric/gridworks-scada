import socket

from aiohttp.web_request import Request
from aiohttp.web_response import Response

from gwproto.data_classes.components.web_server_component import WebServerComponent
from gwproto.named_types.web_server_gt import WebServerGt, DEFAULT_WEB_SERVER_NAME
from actors.scada_actor import ScadaActor
from scada_app_interface import ScadaAppInterface
from gwsproto.named_types import BaseurlFailureAlert, PicoCommsParams

class PicoActorBase(ScadaActor):
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._setup_pico_endpoints()
    
    def _setup_pico_endpoints(self):
        """Setup common pico endpoints for this actor"""
        self.services.add_web_route(
            server_name=DEFAULT_WEB_SERVER_NAME,
            method="POST",
            path=f"/{self.name}/pico-comms-params",
            handler=self._handle_pico_comms_params,
        )
        
        self.services.add_web_route(
            server_name=DEFAULT_WEB_SERVER_NAME,
            method="POST",
            path=f"/{self.name}/baseurl-failure-alert",
            handler=self._handle_baseurl_failure_alert,
        )
    
    async def _handle_pico_comms_params(self, request: Request) -> Response:
        try:
            text = await request.text()

            # Parse incoming request
            try:
                params = PicoCommsParams.model_validate_json(text)
            except Exception as e:
                self.log(f"Invalid PicoCommsParams format: {e}")
                return Response(status=400, text="Invalid message format")

            # Get the SCADA's actual network configuration

            # Get local IP address (there are better ways but this is simple)
            # This assumes the SCADA is on the same network as the pico
            local_ip = request.url.host  # IP the request came to

            try:
                actual_ip = request.transport.get_extra_info('sockname')[0]
            except:
                actual_ip = params.BaseUrl # TODO - safer extraction of IP than the above

            # Get the port from the web server component in layout
            web_server_components = self.layout.get_components_by_type(WebServerComponent)
            if web_server_components:
                # Usually just one, named "default"
                web_server = web_server_components[0]
                if len(web_server_components) > 1:
                    raise Exception("RETHINK HOW PICO ACTOR BASE GETS ITS PORT")
                port = web_server.gt.WebServer.Port
            else:
                port = 8080  # fallback

            # Get hostname for DNS
            hostname = socket.gethostname()
            # Remove .local if present, then add it back
            base_hostname = hostname.replace('.local', '')
            dns_name = f"{base_hostname}.local"

            # Build the correct URLs
            correct_base_url = f"http://{actual_ip}:{port}"
            correct_backup_url = f"http://{dns_name}:{port}"

            # Log if pico has wrong URLs
            if params.BaseUrl != correct_base_url:
                self.log(
                    f"Pico {params.HwUid} has incorrect BaseUrl: "
                    f"{params.BaseUrl} should be {correct_base_url}"
                )

            if params.BackupUrl != correct_backup_url:
                self.log(
                    f"Pico {params.HwUid} has incorrect BackupUrl: "
                    f"{params.BackupUrl} should be {correct_backup_url}"
                )

            # Send back the CORRECT URLs, overriding what the pico sent
            response = PicoCommsParams(
                HwUid=params.HwUid,
                BaseUrl=correct_base_url,  # Enforce IP address
                BackupUrl=correct_backup_url  # Enforce DNS name
            )

            return Response(
                    text=response.model_dump_json(),
                    content_type='application/json',
                    status=200
            )

        except Exception as e:
            self.log(f"Error in pico-comms-params: {e}")
            return Response(status=500)

    async def _handle_baseurl_failure_alert(self, request: Request) -> Response:
        """Handle baseurl failure alert from pico"""
        try:
            text = await request.text()

            # Parse and validate as BaseurlFailureAlert
            try:
                alert = BaseurlFailureAlert.model_validate_json(text)
            except ValueError as e:
                self.log(f"Invalid BaseurlFailureAlert format: {e}")
                return Response(status=400, text="Invalid message format")

            # Log the alert with structured information
            self.log(
                f"BASEURL FAILURE ALERT - "
                f"Pico {alert.HwUid} ({alert.ActorNodeName}) "
                f"failed to reach {alert.BaseUrl} - "
                f"Message: {alert.Message}"
            )

            # TODO: Integrate with error reporting service (e.g., Bugsnag)
            # ... or send up as BaseurlFailureAlert?

            return Response(status=200)
            
        except Exception as e:
            self.log(f"Error handling baseurl-failure-alert: {e}")
            return Response(status=500)