import argparse
import subprocess
from pathlib import Path

try:
    from rich import print as richprint
except ImportError:
    richprint = print

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        usage="""python getkeys.py <certbot-key-name> <mqtt_name> <dest-rclone-name> <dest-cert-dir>
        
    Generate and copy TLS keys for gridworks-scada. 
    
    getkeys.py does the following: 
    1. Use ssh to generate keys on certbot.
    2. Use rclone to copy those keys to the desired location.
    3. Use ssh to *delete* the keys on certbot.
    
    getkeys.py requires: 
    1. The presence of the ssh key used by ssh and rclone. 
    2. Configured rclone remotes.
    
    See https://rclone.org/ for information about rclone. It can be on a Mac installed with: 
         
         brew install rclone
         
    Examples
    -------- 
         
    For scada
    ---------- 
    To generate and copy keys for the scada 'almond', ensure you have the ssh key for certbot in $HOME/.ssh and rclone
    remotes configured for 'certbot' and 'almond' and run:
    
        python gw_spaceheat/getkeys.py almond gridworks_mqtt almond /home/pi/.config/gridworks/scada/certs

    For test Ltn
    ------------
    To generate and copy keys for the test Ltn running on the 'cloudltn' machine used by the scada 'almond', ensure you
    have remotes configured for 'certbot' and 'cloudltn' and run: 
    
        python gw_spaceheat/getkeys.py almond-ltn scada_mqtt cloudltn /home/ubuntu/almond-ltn/.config/gridworks/ltn/certs
    
    To an arbitrary directory
    -------------------------
    To generate and dowload keys to an arbitary directory, e.g., "./certs", run:
     
        python gw_spaceheat/getkeys.py x certs "" .
    
    """,
    )
    parser.add_argument(
        "--certbot-host",
        default="certbot.electricity.works",
        help="Hostname used by ssh to reach certbot.",
    )
    parser.add_argument(
        "--certbot-ssh-user",
        default="ubuntu",
        help="Username used by ssh to reach certbot.",
    )
    parser.add_argument(
        "--certbot-ssh-key",
        default=f"{Path.home()}/.ssh/gridworks-hybrid.pem",
        help="SSH key used by ssh to reach certbot",
    )
    parser.add_argument(
        "--certbot-ca-certificate-path",
        default="/home/ubuntu/.local/share/gridworks/ca/ca.crt",
        help="Path to CA certificate on certbot.",
    )
    parser.add_argument(
        "--certbot-ca-private-key-path",
        default="/home/ubuntu/.local/share/gridworks/ca/private/ca_key.pem",
        help="Path to CA private key on certbot.",
    )
    parser.add_argument(
        "--certbot-certs-dir",
        default="/home/ubuntu/.local/share/gridworks/ca/certs",
        help="Base directory for storing certs on certbot.",
    )
    parser.add_argument(
        "--certbot-rclone-name",
        default="certbot",
        help="Name of the rclone remote used for certbot.",
    )
    parser.add_argument(
        "--certbot-dns",
        default=[],
        action="append",
        help=(
            "Network names allowed when contacting a server with this "
            "certificate. To generate, for example, a certificate used by the "
            "MQTT broker on a Pi reachable at localhost, 192.168.1.202 and "
            "somepi.local, specify: --certbot-dns localhost "
            "--certbot-dns 192.168.1.202 --certbot-certs somepi.local"
        )
    )
    parser.add_argument(
        "--force", action="store_true", help="Force regeneration of keys."
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only generate the keys, do not copy them.",
    )
    parser.add_argument(
        "--copy-only", action="store_true", help="Only copy the keys, do not generate them."
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Do not delete keys from certbot after copying them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands that would be executed but do not execute them.",
    )

    parser.add_argument(
        "certbot_key_name",
        help="Human friendly name used to identify these keys on certbot.",
    )
    parser.add_argument(
        "mqtt_name",
        help=(
            "Name of the MQTTConfig used in ProactorSettings-derived class to refer to the connection these "
            "keys enable. For example, For a scada use 'gridworks_mqtt', the name of the MQTTConfig used to communicate "
            "with the Ltn in ScadaSettings. For the test Ltn use 'scada_mqtt', the name of the MQTTConfig used to "
            "communicate with the scada in LtnSettings."
        ),
    )
    parser.add_argument(
        "dest_rclone_name",
        help=(
            'rclone remote to which files will be transferred. Use an explicit "" to transfer files to local '
            "machine."
        ),
    )
    parser.add_argument(
        "dest_certs_dir",
        help=(
            "Absolute path to destination directory on target machine. A scada with default config uses "
            "/home/pi/.config/gridworks/scada/certs."
        ),
    )
    args = parser.parse_args()

    commands = dict()
    certbot_certs_dir = f"{args.certbot_certs_dir}/{args.certbot_key_name}"
    force_text = "--force " if args.force else ""
    generate_key_command_str = (
        "gwcert key add "
        f"--ca-certificate-path {args.certbot_ca_certificate_path} "
        f"--ca-private-key-path {args.certbot_ca_private_key_path} "
        f"{force_text}"
        f"--certs-dir {certbot_certs_dir} "
        f"{args.mqtt_name}"
    )
    if args.certbot_dns:
        for server_name in args.certbot_dns:
            generate_key_command_str += f" --dns {server_name}"
    certbot_src_dir = f"{certbot_certs_dir}/{args.mqtt_name}"
    certbot_src_private_dir = f"{certbot_src_dir}/private"
    rclone_dest_name = f"{args.dest_rclone_name}:" if args.dest_rclone_name else ""
    rclone_dest_dir = f"{args.dest_certs_dir}/{args.mqtt_name}"
    rclone_dest_private_dir = f"{rclone_dest_dir}/private"
    delete_key_command_str = f"rm -rf {certbot_certs_dir}"

    def _remote_ssh_command(_command_str) -> list[str]:
        return [
            "ssh",
            "-A",
            f"{args.certbot_ssh_user}@{args.certbot_host}",
            "-i",
            args.certbot_ssh_key,
            f"bash -l -c '{_command_str}'",
        ]

    commands = dict(
        generate=_remote_ssh_command(generate_key_command_str),
        mkdir_certs=[
            "rclone",
            "mkdir",
            f"{rclone_dest_name}{rclone_dest_dir}",
        ],
        mkdir_private=[
            f"rclone",
            "mkdir",
            f"{rclone_dest_name}{rclone_dest_private_dir}",
        ],
        copy_ca_certificate=[
            "rclone",
            "copyto",
            f"{args.certbot_rclone_name}:{args.certbot_ca_certificate_path}",
            f"{rclone_dest_name}{rclone_dest_dir}/ca.crt",
        ],
        copy_certififate=[
            "rclone",
            "copyto",
            f"{args.certbot_rclone_name}:{certbot_src_dir}/{args.mqtt_name}.crt",
            f"{rclone_dest_name}{rclone_dest_dir}/{args.mqtt_name}.crt",
        ],
        copy_private_key=[
            "rclone",
            "copyto",
            f"{args.certbot_rclone_name}:{certbot_src_private_dir}/{args.mqtt_name}.pem",
            f"{rclone_dest_name}{rclone_dest_private_dir}/{args.mqtt_name}.pem",
        ],
        delete=_remote_ssh_command(delete_key_command_str),
        ls_target=[
            "rclone",
            "ls",
            f"{rclone_dest_name}{rclone_dest_dir}",
        ],
    )
    if args.generate_only:
        commands = dict(generate_command=commands["generate"])
    if args.copy_only:
        commands.pop("generate", None)
    if args.no_delete:
        commands.pop("delete", None)
    if args.dry_run:
        print("\nDry run. Showing Commands and exiting:\n")
        for cmd in commands.values():
            print(f"{' '.join(cmd)}")
        print()
    else:
        for i, (name, cmd) in enumerate(commands.items()):
            richprint(f"Running <{name}> command:\n\n\t{' '.join(cmd)}\n")
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                richprint(f"Command output:\n[\n{result.stderr.decode('utf-8')}\n]")
                raise RuntimeError(
                    f"ERROR. Command <{' '.join(cmd)}> failed with returncode:{result.returncode}"
                )
            if i == len(commands) - 1:
                richprint(result.stdout.decode("utf-8"))
                richprint("")
