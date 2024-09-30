import cpu_limit_capper_pb2 as pb2_cpu_limit_capper
import cpu_limit_capper_pb2_grpc as pb2_cpu_limit_capper_grpc
import container_service_pb2 as pb2_container_service
import container_service_pb2_grpc as pb2_container_service_grpc
import rapl_power_monitor_per_socket_pb2 as pb2_monitor
import rapl_power_monitor_per_socket_pb2_grpc as pb2_monitor_grpc
import argparse
import grpc
import time
import math
import subprocess
import json
import os
import pandas as pd
import threading
import re

# Batch-application
f_progress, f_progress_percentage, f_allocated_number_of_core, f_allocated_cpu_bandwidth = "", "", "", ""
# System telemetries
f_measured_cpu_power, f_measured_server_power, f_cpu_util, f_cpu_freq = "", "", "", ""

# machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/single_machine.json"
machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/motivation_single_machine.json"
config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/cluster_manager_config.json"
info_log_file = "/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/Motivation/Experiment-33/info_log.txt"

EXPERIMENT_REPEAT_TIMES = 1

# CORE_ALLOCATIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
CORE_ALLOCATIONS = [8, 10, 12, 8, 12, 16, 8, 10, 16]
CPU_QUOTAS = [75, 60, 50, 90, 60, 45, 100, 80, 50]
# CORE_ALLOCATIONS = [4, 4, 4, 4, 8, 8, 8, 8, 16, 16, 16, 16]
# CPU_QUOTAS = [40, 60, 80, 100, 20, 30, 40, 50, 10, 15, 20, 25]

# This method returns the progress nbody simulation makes across different instances.
def sample_batch_application_log(log_file, iteration_progress_data, progress_percentage_data, iteration_tracker, curr_iteration, target_slo):
    df = pd.read_csv(log_file, names=['Instance', 'Time', 'Progress', 'Iteration'])

    filtered = df.groupby('Instance', as_index=False).max()

    number_of_instances = len(filtered)

    total_iteration = 0

    for ind in range(number_of_instances):
        instance_name = filtered.loc[ind]['Instance']
        curr_iteration = filtered.loc[ind]['Iteration']
        print(f"Instance: {instance_name}, current iteration: {curr_iteration}")
        total_iteration += curr_iteration

    progress_made = total_iteration - iteration_tracker.pop(0)
    
    print(f"Iteration: {curr_iteration}, Progress made: {progress_made} iteration(s).")

    # Add iteration progress value into list.
    iteration_progress_data.append((curr_iteration, progress_made))

    curr_progress_percentage = total_iteration / target_slo
    # Add error value into list.
    progress_percentage_data.append((curr_iteration, curr_progress_percentage))

    iteration_tracker.insert(0, total_iteration)

    # subprocess.run(['sudo', 'truncate', '-s', '0', log_file], stdout=subprocess.PIPE)


def sample_blast_log(log_file, pattern, column_count, ntype, template_id, event, iteration_progress_data, progress_percentage_data, iteration_tracker, curr_iteration, target_slo):
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

    print(f"Iteration: {curr_iteration}, Progress made: {throughput} task(s).")

    # Add iteration progress value into list.
    iteration_progress_data.append((curr_iteration, throughput))

    curr_progress_percentage = throughput / target_slo
    # Add current progress percentage value into list.
    progress_percentage_data.append((curr_iteration, curr_progress_percentage * 100))

    tmp_progress = curr_progress_percentage + iteration_tracker.pop()
    iteration_tracker.append(tmp_progress)

    print(f"{iteration_tracker[0] * 100:.2f}% completed...")


def sample_cpu_power_consumption(machines, measured_cpu_power_data, curr_iteration):
    # Retrieve power consumption information of CPUs.
    for mac in machines["machines"]["cpu_power_monitor"]:
        tmp_pow = retrieve_cpu_power_consumption(mac["ip"], mac["port"])
        measured_cpu_power_data.append((curr_iteration, mac["ip"], tmp_pow))


def sample_server_power_consumption(machines, measured_server_power_data, curr_iteration):
    # Retrieve power consumption information of nodes.
    for mac in machines["machines"]["server_power_monitor"]:
        tmp_pow = retrieve_server_power_consumption(mac["epdu_ip"], mac["outlet"])
        measured_server_power_data.append((curr_iteration, mac["epdu_ip"] + "-" + str(mac["outlet"]), tmp_pow))


def sample_cpu_freq(machines, cpu_freq_data, curr_iteration):
    # Retrieve cpu frequency information of nodes and cpu utilization information of containers.
    for mac in machines["machines"]["container_service"]:
        cpu_freq_data.append((curr_iteration, mac["ip"], retrieve_cpu_freq_information(mac["ip"], mac["port"], "")))


def sample_cpu_util(machines, cpu_util_data, curr_iteration):
    # Retrieve cpu frequency information of nodes and cpu utilization information of containers.
    for mac in machines["machines"]["container_service"]:
        for c1 in mac["container_name"]:
            cpu_util_data.append((curr_iteration, mac["ip"], c1, retrieve_container_cpu_usage_information(mac["ip"], mac["port"], c1)))


def write_to_file( iteration_progress_data, progress_percentage_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data ):
    # Batch-application specific data
    with open(f_progress, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in iteration_progress_data))

    with open(f_progress_percentage, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]:.2f}),' for tup in progress_percentage_data))

    with open(f_allocated_number_of_core, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in allocated_number_of_core_data))

    with open(f_allocated_cpu_bandwidth, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in allocated_cpu_bandwidth_data))
    
    # System telemetry data
    with open(f_measured_cpu_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in measured_cpu_power_data))

    with open(f_measured_server_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in measured_server_power_data))

    with open(f_cpu_util, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}","{tup[2]}",{tup[3]}),' for tup in cpu_util_data))

    with open(f_cpu_freq, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in cpu_freq_data))
    

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
                

def retrieve_cpu_power_consumption(machine_ip, machine_port):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_monitor_grpc.PowerMonitorStub(channel)
        avg_power = stub.per_socket_power( pb2_monitor.No_Input() )
    
        return avg_power.power_values
    

# This method return power consumption of the machine at the outlet level.
def retrieve_server_power_consumption(ePDU_ip, outlet):
    # Output: date of observation, time of observation, outletname, status (on/off), load in tenth of Amps, load in Watts
    command = f"snmpget -v1 -c private -M +. -O vq -m ALL {ePDU_ip} mconfigClockDate.0 mconfigClockTime.0 ePDU2OutletSwitchedInfoName.{outlet} ePDU2OutletSwitchedStatusState.{outlet} ePDU2OutletMeteredStatusLoad.{outlet} ePDU2OutletMeteredStatusActivePower.{outlet}"

    parsed_command = command.split()

    proc1 = subprocess.run(parsed_command, stdout=subprocess.PIPE)
    output = proc1.stdout.decode('utf-8')

    lined_output = output.replace('\n', ',')

    return lined_output.split(',')[5]


def retrieve_cpu_freq_information(machine_ip, machine_port, container_name):
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        s = stub.retrieve_cpu_freq_information( pb2_container_service.Container_Service_Input(domain_name=container_name))
        return s.cpu_freq
    

def retrieve_container_cpu_usage_information(machine_ip, machine_port, container_name):
    cpu_usage = 0.99
    
    with grpc.insecure_channel(f'{machine_ip}:{machine_port}') as channel:
        stub = pb2_container_service_grpc.ContainerServiceStub(channel)
        s = stub.retrieve_container_cpu_usage_information( pb2_container_service.Container_Service_Input(domain_name=container_name))
        cpu_usage = min(cpu_usage, s.cpu_usage)

        return cpu_usage
    

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
    

# This method returns the hash of the last modification time of given file_name.
def hash_file(file_name):
    modify_time = os.path.getmtime(file_name)
    # print(modify_time)
    hashed_object = hash(modify_time)
    # print(hashed_object)
    return hashed_object


def run_manager(log_file_batch, batch_ref_input):
    # Batch application variables
    iteration_progress_data, progress_percentage_data, iteration_tracker, allocated_number_of_core_data, allocated_cpu_bandwidth_data = [], [], [], [], []
    # System telemetry variables
    measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []

    ''' To keep configuration variables '''
    config_dict = {}

    with open(config_file, "r") as f:
        config_dict = json.load(f)

    cluster_size = config_dict["system_configs"]["cluster_size"]
    sampling_time = config_dict["system_configs"]["blast_sampling_time"]
    host_min_power = config_dict["system_configs"]["min_power"]
    host_max_power = config_dict["system_configs"]["max_power"]
    
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

    print(f"Total number of machines in the cluster: {cluster_size}")
    print(f"Min power limit of nodes: {host_min_power}")
    print(f"Max power limit of nodes: {host_max_power}")

    print(f"Current core info of containers: {machine_curr_number_of_cores}")
    print(f"Current core usage limits of containers: {machine_curr_core_usage_limits}")
    
    print(f"Reference input of the batch application: {batch_ref_input} task(s).")

    iteration_counter = 0

    iteration_tracker.append(0)

    while True:
        prev_hash_batch = hash_file(log_file_batch)
        time.sleep(2)

        if prev_hash_batch != hash_file(log_file_batch):
            break

    # Wait 5 seconds for warm-up.
    time.sleep(5)

    # while True:
    for ind in range(len(CORE_ALLOCATIONS)):
        for m1 in machines["machines"]["core_allocator"]:
            for m2 in m1["container_name"]:
                step1_output = run_core_number_allocator(m1["ip"], m1["port"], m2, CORE_ALLOCATIONS[ind])

                if step1_output == True:
                    print(f"{CORE_ALLOCATIONS[ind]} core(s) has been allocated to {m2} hosted on {m1['ip']}.")
            
                else:
                    with open(info_log_file, "a") as f:
                        f.write(f"Iteration: {iteration_counter} - {CORE_ALLOCATIONS[ind]} core(s) could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

        for m1 in machines["machines"]["core_allocator"]:
            for m2 in m1["container_name"]:
                step2_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, CORE_ALLOCATIONS[ind] * CPU_QUOTAS[ind])

                if step2_output == True:
                    print(f"{CPU_QUOTAS[ind]} cpu bandwidth limit has been allocated per core for {m2} hosted on {m1['ip']}.")

                else:
                    with open(info_log_file, "a") as f:
                        f.write(f"Iteration: {iteration_counter} - {CORE_ALLOCATIONS[ind] * CPU_QUOTAS[ind]} cpu bandwidth per core could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

        # Wait for 1 second to make sure that new configuration is in effect.
        time.sleep(1)

        for _ in range(EXPERIMENT_REPEAT_TIMES):
            subprocess.run(['truncate', '-s', '0', log_file_batch], stdout=subprocess.PIPE)

            print("Blast progress log file is cleared for the next iteration.")

            time.sleep(sampling_time)

            # Batch application part
            t1 = threading.Thread( target=sample_blast_log, args=(log_file_batch, r'(?:[^\s"]+|"[^"]*")+', 9, 'task', 'parallel', 'done', iteration_progress_data, progress_percentage_data, iteration_tracker, iteration_counter, batch_ref_input,))

            # System telemetry part
            t2 = threading.Thread( target=sample_cpu_power_consumption, args=(machines, measured_cpu_power_data, iteration_counter,))

            t3 = threading.Thread( target=sample_server_power_consumption, args=(machines, measured_server_power_data, iteration_counter,))

            t4 = threading.Thread( target=sample_cpu_freq, args=(machines, cpu_freq_data, iteration_counter,))

            t5 = threading.Thread( target=sample_cpu_util, args=(machines, cpu_util_data, iteration_counter,))

            threads = [t1, t2, t3, t4, t5]

            for my_thread in threads:
                my_thread.start()
            
            for my_thread in threads:
                my_thread.join()

            # Adding allocated number of core data info into the list.
            allocated_number_of_core_data.append((iteration_counter, CORE_ALLOCATIONS[ind]))

            # Adding allocated core bandwidth data info into the list.
            allocated_cpu_bandwidth_data.append((iteration_counter, CPU_QUOTAS[ind]))

            iteration_counter += 1
            
            print("Recording data to files...")
            
            write_to_file( iteration_progress_data, progress_percentage_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data )

            # reset batch application variables
            iteration_progress_data, progress_percentage_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data = [], [], [], []
            # reset system telemetry variables
            measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Batch Application Telemetry Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Batch application arguments
    parser.add_argument("-blf", "--b-log-file", default="/nfs/obelix/raid2/msavasci/workflows/blast/TigresBlast-235-16-DISTRIBUTE_PROCESS.log", help="Blast progress log file location")
    parser.add_argument("-bts", "--b-target-slo", default=235, type=int, help="target iteration SLO for blast")

    parser.add_argument("-ip", "--iteration-progress", default="./data/iteration-progress.txt", help="File to keep iteration progress data")
    parser.add_argument("-pp", "--progress-percentage", default="./data/progress-percentage.txt", help="File to keep progress percentage")
    parser.add_argument("-anc", "--allocated-number-of-core", default="./data/allocated-number-of-core.txt", help="File to keep allocated number of core")
    parser.add_argument("-acb", "--allocated-cpu-bandwidth", default="./data/allocated-cpu-bandwidth.txt", help="File to keep allocated cpu bandwidth")
    
    # System telemetry
    parser.add_argument("-cp", "--measured-cpu-power", default="./data/measured_cpu_power.txt", help="File to measured cpu power")
    parser.add_argument("-sp", "--measured-server-power", default="./data/measured_server_power.txt", help="File to measured server power")
    parser.add_argument("-cf", "--cpu-frequency", default="./data/cpu_frequency.txt", help="File to keep cpu frequency")
    parser.add_argument("-cu", "--cpu-utilization", default="./data/cpu_utilization.txt", help="File to keep cpu utilization")
    
    args = parser.parse_args()
    
    # Batch-application
    f_progress = args.iteration_progress                      # File for iteration progress
    f_progress_percentage = args.progress_percentage          # File for controller input/error input
    f_allocated_number_of_core = args.allocated_number_of_core    # File for keeping allocated number of core data
    f_allocated_cpu_bandwidth = args.allocated_cpu_bandwidth      # File for keeping allocated core usage data

    # System telemetries    
    f_measured_cpu_power = args.measured_cpu_power            # File for keeping measured cpu power consumption
    f_measured_server_power = args.measured_server_power      # File for keeping measured cpu power consumption
    f_cpu_freq = args.cpu_frequency                           # File for keeping cpu frequency
    f_cpu_util = args.cpu_utilization                         # File for keeping cpu utilization
    
    run_manager(args.b_log_file, args.b_target_slo)