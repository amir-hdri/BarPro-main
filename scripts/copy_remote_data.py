import json
import logging
import socket
import sys
import time
import paramiko
import socks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

IP = "95.38.233.90"
USERNAME = "ubuntu"
PASSWORD = "Amaterasoo1"

def find_local_proxy():
    """Probe local ports to find active SOCKS5 proxy (v2ray/Nekoray/Clash)."""
    common_ports = [1080, 10808, 20808, 7890, 1089]
    for port in common_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    logger.info(f"Auto-detected active local proxy at 127.0.0.1:{port}")
                    return port
        except Exception:
            pass
    return None

def connect_ssh(retries=5, delay=5):
    """Establish SSH connection, automatically using local proxy if available."""
    proxy_port = find_local_proxy()
    
    for attempt in range(1, retries + 1):
        if proxy_port:
            logger.info(f"Connecting to remote server at {IP} via local SOCKS5 proxy on port {proxy_port} (Attempt {attempt}/{retries})...")
        else:
            logger.info(f"Connecting directly to remote server at {IP} (Attempt {attempt}/{retries})...")
            
        try:
            if proxy_port:
                # Create a SOCKS5 socket
                s = socks.socksocket()
                s.set_proxy(socks.SOCKS5, "127.0.0.1", proxy_port)
                s.connect((IP, 22))
                
                # Setup paramiko on top of the proxied socket
                transport = paramiko.Transport(s)
                transport.connect(username=USERNAME, password=PASSWORD)
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh._transport = transport
            else:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(IP, username=USERNAME, password=PASSWORD, timeout=15)
                
            logger.info("Connected successfully via SSH.")
            return ssh
        except Exception as e:
            logger.warning(f"Connection attempt {attempt} failed: {e}")
            if attempt < retries:
                logger.info(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                logger.error("All SSH connection attempts failed.")
                raise e

def fetch_json_from_db_with_reconnect(query, max_query_retries=3):
    """Execute SQL query via remote psql, reconnecting if SSH drops."""
    sql = f"SELECT json_agg(t) FROM ({query}) t;"
    cmd = f'docker exec -i barpro-postgres psql -U postgres -d utcms_rpa -A -t -c "{sql}"'
    
    for attempt in range(1, max_query_retries + 1):
        ssh = None
        try:
            ssh = connect_ssh(retries=2, delay=3)
            logger.info(f"Executing remote query (Attempt {attempt}/{max_query_retries}): {query[:60]}...")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_msg = stderr.read().decode("utf-8")
                logger.error(f"Command failed with exit code {exit_status}: {error_msg}")
                raise RuntimeError(f"Failed to execute query: {error_msg}")
                
            output = stdout.read().decode("utf-8").strip()
            if not output or output == "None" or output == "(null)":
                return []
            
            return json.loads(output)
        except Exception as e:
            logger.warning(f"Query execution attempt {attempt} failed: {e}")
            if attempt < max_query_retries:
                logger.info("Reconnecting and retrying query...")
                time.sleep(3)
            else:
                logger.error("All query execution attempts failed.")
                raise e
        finally:
            if ssh:
                ssh.close()

def main():
    try:
        # 1. Fetch all drivers
        logger.info("Step 1: Fetching all drivers...")
        drivers = fetch_json_from_db_with_reconnect("SELECT * FROM drivers")
        logger.info(f"Successfully fetched {len(drivers)} drivers.")
        with open("remote_drivers.json", "w", encoding="utf-8") as f:
            json.dump(drivers, f, indent=4, ensure_ascii=False)
        logger.info("Saved drivers to remote_drivers.json")
        
        # 2. Fetch all driver plates
        logger.info("Step 2: Fetching all driver plates...")
        plates = fetch_json_from_db_with_reconnect("SELECT * FROM driver_plates")
        logger.info(f"Successfully fetched {len(plates)} driver plates.")
        with open("remote_plates.json", "w", encoding="utf-8") as f:
            json.dump(plates, f, indent=4, ensure_ascii=False)
        logger.info("Saved plates to remote_plates.json")
        
        # 3. Fetch last 3 waybills
        logger.info("Step 3: Fetching last 3 waybills...")
        waybills = fetch_json_from_db_with_reconnect("SELECT * FROM waybill_jobs ORDER BY created_at DESC LIMIT 3")
        logger.info(f"Successfully fetched {len(waybills)} waybills.")
        with open("remote_waybills.json", "w", encoding="utf-8") as f:
            json.dump(waybills, f, indent=4, ensure_ascii=False)
        logger.info("Saved waybills to remote_waybills.json")
        
        # Consolidate backup file
        consolidated = {
            "drivers": drivers,
            "driver_plates": plates,
            "waybill_jobs": waybills
        }
        with open("remote_data_backup.json", "w", encoding="utf-8") as f:
            json.dump(consolidated, f, indent=4, ensure_ascii=False)
        logger.info("Consolidated all remote data into remote_data_backup.json successfully.")
        
    except Exception as e:
        logger.error(f"Migration backup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
