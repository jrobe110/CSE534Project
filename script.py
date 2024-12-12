import subprocess
import time
import paramiko

P4_SWITCH_CLI_PATH = "/usr/bin/simple_switch_CLI"  # Path to the simple_switch_CLI
THRIFT_PORT = 9090
MONITOR_INTERVAL = 10
BANDWIDTH_THRESHOLD = 25.0 

# Router details
ROUTERS = {
    "router1": {"ip": "192.168.2.10", "mac": "00:00:00:00:00:04", "iperf_port": 1},
    "router2": {"ip": "192.168.3.10", "mac": "00:00:00:00:00:06", "iperf_port": 2}
}

ALTERNATE_ROUTE = "192.168.5.10"  # Alternate destination IP

# SSH connection details
P4_SWITCH_IP = "2001:400:a100:3030:f816:3eff:fe4f:d001"  # IP address of the P4 switch
P4_SWITCH_USER = "ubuntu"  # SSH username for the P4 switch
PRIVATE_KEY_PATH = "/home/fabric/work/fabric_config/slice_key"  # Path to your private key
SSH_CONFIG_PATH = "/home/fabric/work/fabric_config/ssh_config"  # Path to your SSH config file

# Function to run iperf client and get bandwidth
def get_bandwidth(router_ip, port):
    try:
        result = subprocess.run(
            ["iperf3", "-c", router_ip, "-p", str(port), "-t", "2", "-f", "m"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        for line in result.stdout.splitlines():
            if "sender" in line:
                bandwidth = float(line.split()[-2])
                print(line)
                return bandwidth
    except Exception as e:
        print(f"Error running iperf for {router_ip}: {e}")
    return 0.0

# Function to execute a simple_switch_CLI command on the P4 switch via SSH
def run_simple_switch_cli(command):
    try:
        # Create an SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load SSH config and set up the connection
        ssh.load_system_host_keys()
        ssh_config = paramiko.config.SSHConfig()
        with open(SSH_CONFIG_PATH) as f:
            ssh_config.parse(f)
        
        private_key = paramiko.RSAKey.from_private_key_file(PRIVATE_KEY_PATH)

        ssh.connect(P4_SWITCH_IP, username=P4_SWITCH_USER, pkey=private_key, look_for_keys=False)

        stdin, stdout, stderr = ssh.exec_command(f"{P4_SWITCH_CLI_PATH} --thrift-port {THRIFT_PORT} {command}")
        
        output = stdout.read().decode()
        error = stderr.read().decode()

        if error:
            print(f"Error executing CLI command:\n{error}")
        return output
    except Exception as e:
        print(f"Error running simple_switch_CLI via SSH: {e}")
    finally:
        ssh.close()

    return ""

# Function to update the P4 table
def update_p4_table(overloaded_router_ip):
    print(f"Updating P4 table to reroute traffic away from {overloaded_router_ip}")

    # Remove existing entry for overloaded router
    delete_command = f"table_delete MyIngress.modify_dst_ip {overloaded_router_ip}\n"
    run_simple_switch_cli(delete_command)

    # Add a new entry with the alternate route
    add_command = f"table_add MyIngress.modify_dst_ip MyIngress.set_dst_ip {overloaded_router_ip} => {ALTERNATE_ROUTE}\n"
    run_simple_switch_cli(add_command)

# Function to restore routing for a router
def restore_p4_table(router_ip):
    print(f"Restoring P4 table for {router_ip}")
    delete_command = f"table_delete MyIngress.modify_dst_ip {router_ip}\n"
    run_simple_switch_cli(delete_command)

def main():
    while True:
        for router_name, router_info in ROUTERS.items():
            bandwidth = get_bandwidth(router_info["ip"], router_info["iperf_port"])
            print(f"Router {router_name} ({router_info['ip']}): Bandwidth = {bandwidth} Mbps")

            if bandwidth < BANDWIDTH_THRESHOLD:
                update_p4_table(router_info["ip"])
            else:
                restore_p4_table(router_info["ip"])

        time.sleep(MONITOR_INTERVAL)

if __name__ == "__main__":
    main()