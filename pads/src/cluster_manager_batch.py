import cpu_limit_capper_pb2 as pb2_cpu_limit_capper
import cpu_limit_capper_pb2_grpc as pb2_cpu_limit_capper_grpc
import container_service_pb2 as pb2_container_service
import container_service_pb2_grpc as pb2_container_service_grpc
import rapl_power_monitor_pb2 as pb2_monitor
import rapl_power_monitor_pb2_grpc as pb2_monitor_grpc
import argparse
import grpc
import time
import math
import subprocess
import json
import os
import pandas as pd
import re

f_progress, f_error_value, f_allocated_number_of_core, f_allocated_cpu_bandwidth, f_measured_cpu_power, f_measured_server_power, f_cpu_util, f_cpu_freq = "", "", "", "", "", "", "", ""

machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/single_machine.json"
# machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/cluster_machines.json"
config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/cluster_manager_config.json"
info_log_file = "/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/Batch/Experiment-1/info_log.txt"

core_number_values = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
core_usage_values = [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]


def core_power_limit(number_of_cores):
    # This equation derived from core_power experiment. intel pstate driver with powersave governor.
    # return math.ceil(2.81 * number_of_cores + 44.95)

    # This equation derived from core_power experiment. acpi_freq driver with performance governor.
    return math.floor(2.86 * number_of_cores + 46.52)


# This method returns the progress nbody simulation makes across different instances.
def sample_batch_progress(log_file):
    df = pd.read_csv(log_file, names=['Instance', 'Time', 'Progress', 'Iteration'])

    filtered = df.groupby('Instance', as_index=False).max()

    number_of_instances = len(filtered)

    total_iteration = 0

    for ind in range(number_of_instances):
        instance_name = filtered.loc[ind]['Instance']
        curr_iteration = filtered.loc[ind]['Iteration']
        print(f"Instance: {instance_name}, current iteration: {curr_iteration}")
        total_iteration += curr_iteration

    return total_iteration


def sample_blast_log(log_file, pattern, column_count, ntype, template_id, event):
    log_lines = []

    with open(log_file) as f: 
        # read log lines and store it in list
        log_lines = f.readlines()

    # Log file is empty
    # if len(log_lines) == 0:
    #     return -1
        
    throughput = 0

    for line in log_lines:
        # Find all matches in the line
        matches = re.findall(pattern, line)

        # For the provided sample log
        # if len(matches) == column_count and (ntype in matches[2].lower()) and (template_id in matches[3].lower()) and (event in matches[8].lower()):
        # For the real log
        if len(matches) == column_count and (ntype in matches[5].lower()) and (template_id in matches[3].lower()) and (event in matches[4].lower()):
            throughput += 1

        # Print the parsed result
        # print(matches)

    return throughput


def write_to_file( iteration_progress_data, error_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data ):
    with open(f_progress, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in iteration_progress_data))

    with open(f_error_value, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in error_data))

    with open(f_allocated_number_of_core, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in allocated_number_of_core_data))

    with open(f_allocated_cpu_bandwidth, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in allocated_cpu_bandwidth_data))

    with open(f_measured_cpu_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]},{tup[2]}),' for tup in measured_cpu_power_data))

    with open(f_measured_server_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]},{tup[2]}),' for tup in measured_server_power_data))

    with open(f_cpu_util, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]},{tup[2]},{tup[3]}),' for tup in cpu_util_data))

    with open(f_cpu_freq, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]},{tup[2]}),' for tup in cpu_freq_data))


def run_core_number_allocator(host, port, vm_name, number_of_cores):
    with grpc.insecure_channel(f'{host}:{port}') as channel:
        stub = pb2_cpu_limit_capper_grpc.CpuLimitCapperStub(channel)
        response = stub.limit_core_number( pb2_cpu_limit_capper.Core_Number_Inputs(domain_name=vm_name, number_of_cores=number_of_cores))
        
        return response.status
    

def run_core_usage_allocator(host, port, vm_name, core_usage):
    with grpc.insecure_channel(f'{host}:{port}') as channel:
        stub = pb2_cpu_limit_capper_grpc.CpuLimitCapperStub(channel)
        response = stub.limit_core_usage( pb2_cpu_limit_capper.Core_Usage_Inputs(domain_name=vm_name, core_usage_limit=core_usage))
        
        return response.status


def retrieve_cpu_freq_information(machine_ip, machine_port, container_name):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        s = stub.retrieve_cpu_freq_information( pb2_container_service.Container_Service_Input(domain_name=container_name))
        return s.cpu_freq
    

def retrieve_container_core_information(machine_ip, machine_port, container_name):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        response = stub.retrieve_container_core_information(pb2_container_service.Container_Service_Input(domain_name=container_name))
    
        return response.number_of_cores
    

def retrieve_container_core_usage_limit_information(machine_ip, machine_port, container_name):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        response = stub.retrieve_container_core_usage_limit_information(pb2_container_service.Container_Service_Input(domain_name=container_name))
    
        return response.core_usage_limit
    

def retrieve_container_cpu_usage_information(machine_ip, machine_port, container_name):
    cpu_usage = 0.99
    
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        s = stub.retrieve_container_cpu_usage_information( pb2_container_service.Container_Service_Input(domain_name=container_name))
        cpu_usage = min(cpu_usage, s.cpu_usage)

        return cpu_usage
            

def retrieve_cpu_power_consumption(machine_ip, machine_port):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_monitor_grpc.PowerMonitorStub(channel)
        avg_power = stub.average_power( pb2_monitor.No_Input() )
    
        return avg_power.power_value
    

# This method return power consumption of the machine at the outlet level.
def retrieve_server_power_consumption(ePDU_ip, outlet):
    # Output: date of observation, time of observation, outletname, status (on/off), load in tenth of Amps, load in Watts
    command = f"snmpget -v1 -c private -M +. -O vq -m ALL {ePDU_ip} mconfigClockDate.0 mconfigClockTime.0 ePDU2OutletSwitchedInfoName.{outlet} ePDU2OutletSwitchedStatusState.{outlet} ePDU2OutletMeteredStatusLoad.{outlet} ePDU2OutletMeteredStatusActivePower.{outlet}"

    parsed_command = command.split()

    proc1 = subprocess.run(parsed_command, stdout=subprocess.PIPE)
    output = proc1.stdout.decode('utf-8')

    lined_output = output.replace('\n', ',')

    return lined_output.split(',')[5]
    

# This method returns the hash of the last modification time of given file_name.
def hash_file(file_name):
    modify_time = os.path.getmtime(file_name)
    # print(modify_time)
    hashed_object = hash(modify_time)
    # print(hashed_object)
    return hashed_object


def run_manager(ref_input, log_file):
    # Define list holding measurements/variables during experiment
    iteration_progress_data, error_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], [], [], [], [], []

    ''' To keep configuration variables '''
    config_dict = {}

    with open(config_file, "r") as f:
        config_dict = json.load(f)

    recording_frequency = config_dict["system_configs"]["recording_frequency"]
    min_cpu_bandwidth = config_dict["system_configs"]['min_cpu_bandwidth']
    max_cpu_bandwidth = config_dict["system_configs"]['max_cpu_bandwidth']
    # number_of_cpu_sockets = config_dict["system_configs"]["number_of_cpu_sockets"]
    cluster_size = config_dict["system_configs"]["cluster_size"]
    slo_guard = config_dict["system_configs"]["slo_guard"]
    sampling_time = config_dict["system_configs"]["sampling_time"]
    min_host_power = config_dict["system_configs"]["min_power"]
    max_host_power = config_dict["system_configs"]["max_power"]
    
    print(f"Min cpu bandwidth: {min_cpu_bandwidth}, Max cpu bandwidth: {max_cpu_bandwidth * cluster_size}")

    with open(machines_config_file) as f:
        machines = json.load(f)

    machine_curr_number_of_cores = {}

    for m1 in machines["machines"]["container_service"]:
        for m2 in m1["container_name"]:
            machine_curr_number_of_cores[(m1["ip"], m2)] = retrieve_container_core_information(m1["ip"], m1["port"], m2)

    machine_curr_core_usage_limits = {}

    for m1 in machines["machines"]["container_service"]:
        for m2 in m1["container_name"]:
            machine_curr_core_usage_limits[(m1["ip"], m2)] =  retrieve_container_core_usage_limit_information(m1["ip"], m1["port"], m2)

    print(f"Current core info of containers: {machine_curr_number_of_cores}")
    print(f"Current core usage limits of containers: {machine_curr_core_usage_limits}")
    print(f"Controller min power limit for node: {min_host_power}")
    print(f"Controller max power limit for node: {max_host_power}")
    print(f"Target iteration of the batch application: {ref_input}")

    print(f"Reference input of the batch application: {ref_input}")
    print(f"slo_guard: {slo_guard}")

    guarded_slo_target = ref_input * slo_guard

    print(f"Guarded SLO target: {guarded_slo_target}")

    iteration_counter = 0

    REPEAT_TIMES = 1

    while True:
        prev_hash = hash_file(log_file)
        time.sleep(2)

        if prev_hash != hash_file(log_file):
            break

    # Retrieve power consumption information of CPUs.
    for mac in machines["machines"]["cpu_power_monitor"]:
        tmp_pow = retrieve_cpu_power_consumption(mac["ip"], mac["port"])

    time.sleep(10)

    subprocess.run(['truncate', '-s', '0', log_file], stdout=subprocess.PIPE)

    # print("NBody progress log file is cleared for the initialization purpose.")
    print("Blast log file is cleared for the initialization purpose.")

    # while True:
    for curr_number_of_core in core_number_values:
        for m1 in machines["machines"]["core_allocator"]:
            for m2 in m1["container_name"]:
                step1_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_number_of_core)

                if step1_output == True:
                    print(f"{curr_number_of_core} core(s) has been allocated to {m2} hosted on {m1['ip']}.")
            
                else:
                    with open(info_log_file, "a") as f:
                        f.write(f"Iteration: {iteration_counter} - {curr_number_of_core} core(s) could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

        total_throughput = 0

        for curr_cpu_bandwidth in core_usage_values:
            for m1 in machines["machines"]["core_allocator"]:
                for m2 in m1["container_name"]:
                    step2_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_number_of_core * curr_cpu_bandwidth)

                    if step2_output == True:
                        print(f"{curr_cpu_bandwidth}% cpu bandwidth limit has been allocated per core for {m2} hosted on {m1['ip']}.")

                    else:
                        with open(info_log_file, "a") as f:
                            f.write(f"Iteration: {iteration_counter} - {curr_number_of_core * curr_cpu_bandwidth} cpu bandwidth per core could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

            # Wait for 1 second to make sure that new configuration is in effect.
            time.sleep(1)

            # while_loop_counter = 0
            
            # while while_loop_counter < REPEAT_TIMES:
            for _ in range(REPEAT_TIMES):
                # Blast log file is cleared.
                subprocess.run(['truncate', '-s', '0', log_file], stdout=subprocess.PIPE)

                # prev_iteration_progress = sample_batch_progress(log_file)
                
                # time.sleep(sampling_time)

                # curr_iteration_progress = sample_batch_progress(log_file)

                # progress_made = curr_iteration_progress - prev_iteration_progress

                # print(f"Iteration: {iteration_counter}, Progress made: {progress_made} iteration(s).")
                # # Add iteration progress value into list.
                # iteration_progress_data.append((iteration_counter, progress_made))

                # curr_progress_percentage = curr_iteration_progress / guarded_slo_target
                # # Add error value into list.
                # error_data.append((iteration_counter, curr_progress_percentage))
                time.sleep(sampling_time)

                current_throughput = sample_blast_log(log_file, r'(?:[^\s"]+|"[^"]*")+', 9, 'task', 'parallel', 'done')

                # if current_throughput == -1:
                #     continue

                # while_loop_counter +=1

                iteration_counter += 1

                print(f"Iteration: {iteration_counter}, Current throughput: {current_throughput} task(s).")
                # Add iteration progress value into list.
                iteration_progress_data.append((iteration_counter, current_throughput))

                total_throughput += current_throughput

                curr_progress_percentage = total_throughput / guarded_slo_target
                # Add error value into list.
                error_data.append((iteration_counter, curr_progress_percentage))

                # Adding allocated number of core data info into the list.
                allocated_number_of_core_data.append((iteration_counter, curr_number_of_core))

                # Adding allocated core bandwidth data info into the list.
                allocated_cpu_bandwidth_data.append((iteration_counter, curr_cpu_bandwidth))

                # Retrieve power consumption information of CPUs.
                for mac in machines["machines"]["cpu_power_monitor"]:
                    tmp_pow = retrieve_cpu_power_consumption(mac["ip"], mac["port"])
                    measured_cpu_power_data.append((iteration_counter, str(mac["ip"]), tmp_pow))

                # Retrieve power consumption information of nodes.
                for mac in machines["machines"]["server_power_monitor"]:
                    tmp_pow = retrieve_server_power_consumption(mac["epdu_ip"], mac["outlet"])
                    measured_server_power_data.append((iteration_counter, str(mac["epdu_ip"]) + "-" + str(mac["outlet"]), tmp_pow))

                # Retrieve cpu frequency information of nodes and cpu utilization information of containers.
                for mac in machines["machines"]["container_service"]:
                    cpu_freq_data.append((iteration_counter, str(mac["ip"]), retrieve_cpu_freq_information(mac["ip"], mac["port"], "")))

                    for c1 in mac["container_name"]:
                        tmp_cpu_util = retrieve_container_cpu_usage_information(mac["ip"], mac["port"], c1)
                        cpu_util_data.append((iteration_counter, str(mac["ip"]), str(c1), tmp_cpu_util))

                print("Recording data to files...")

                write_to_file( iteration_progress_data, error_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data )

                iteration_progress_data, error_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], [], [], [], [], []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cluster Manager Batch Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-ts", "--target-slo", default=30000, type=int, help="target iteration SLO")
    parser.add_argument("-sl", "--source-log-file", default="/nfs/obelix/raid2/msavasci/nbody_results/30000/progress.csv", help="NBody simulation progress log file location")

    parser.add_argument("-ip", "--iteration-progress", default="./data/iteration-progress.txt", help="File to keep iteration progress data")
    parser.add_argument("-ev", "--error-value", default="./data/error-value.txt", help="File to keep error value")
    parser.add_argument("-anc", "--allocated-number-of-core", default="./data/allocated-number-of-core.txt", help="File to keep allocated number of core")
    parser.add_argument("-ac", "--allocated-cpu-bandwidth", default="./data/allocated-cpu-bandwidth.txt", help="File to keep allocated cpu bandwidth")
    parser.add_argument("-cp", "--measured-cpu-power", default="./data/measured_cpu_power.txt", help="File to measured cpu power")
    parser.add_argument("-sp", "--measured-server-power", default="./data/measured_server_power.txt", help="File to measured server power")
    parser.add_argument("-cu", "--cpu-utilization", default="./data/cpu_utilization.txt", help="File to keep cpu utilization")
    parser.add_argument("-cf", "--cpu-frequency", default="./data/cpu_frequency.txt", help="File to keep cpu frequency")

    args = parser.parse_args()

    f_progress = args.iteration_progress                          # File for iteration progress
    f_error_value = args.error_value                              # File for controller input/error input
    f_allocated_number_of_core = args.allocated_number_of_core    # File for keeping allocated number of core data
    f_allocated_cpu_bandwidth = args.allocated_cpu_bandwidth      # File for keeping allocated core usage data
    f_measured_cpu_power = args.measured_cpu_power                # File for keeping measured cpu power consumption
    f_measured_server_power = args.measured_server_power          # File for keeping measured cpu power consumption
    f_cpu_util = args.cpu_utilization                       # File for keeping cpu utilization
    f_cpu_freq = args.cpu_frequency                         # File for keeping cpu frequency
    
    run_manager(args.target_slo, args.source_log_file)