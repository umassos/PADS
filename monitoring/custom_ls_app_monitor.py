import cpu_limit_capper_pb2 as pb2_cpu_limit_capper
import cpu_limit_capper_pb2_grpc as pb2_cpu_limit_capper_grpc
import container_service_pb2 as pb2_container_service
import container_service_pb2_grpc as pb2_container_service_grpc
import rapl_power_monitor_per_socket_pb2 as pb2_monitor
import rapl_power_monitor_per_socket_pb2_grpc as pb2_monitor_grpc
import argparse
import grpc
import time
import subprocess
import json
import os
import statistics as stat
from collections import defaultdict
import numpy as np
import threading
import pickle

# Latency sentitive app
f_mean_rt, f_tail_rt, f_error_value, f_est_number_of_request,  f_drop_percent, f_service_rate, f_log_file, f_allocated_number_of_core, f_allocated_cpu_bandwidth = "", "", "", "", "", "", "", "", ""
# System telemetries
f_measured_cpu_power, f_measured_server_power, f_cpu_util, f_cpu_freq = "", "", "", ""

machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/motivation_single_machine.json"
config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/cluster_manager_config.json"
info_log_file = "/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/IGSC24/Motivation/Experiment-1/info_log.txt"

CORE_ALLOCATIONS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
CPU_QUOTAS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]

EXPERIMENT_REPEAT_TIMES = 1

# This method returns [200 code response times, average response time, tail latency, #req/s, log_data, drop_rate, arrival_rate, service_rate] in this order
def sample_latency_sensitive_log(log_file, application_sub_path, percentile, sampling_time, mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_data, curr_iteration, target_slo):
    log_lines, response_times = [], []
    count_all_response_codes, count_not_200_response_codes = 0, 0

    with open(log_file) as f: 
        # read log lines and store it in list
        log_lines = f.readlines()

    # Initialize a dictionary to store the count of each field
    field_counts = defaultdict(int)

    for line in log_lines:
        splitted = line.split()
    
        if len(splitted) < 21:
            continue

        # log_lines.append(line)
    
        response_code_info = splitted[10]
        page_info = splitted[18]
        response_time_info = int(splitted[20])

        if page_info.strip().startswith(application_sub_path):
            count_all_response_codes += 1

            # Split the line by space and extract the 16th field
            field_16 = splitted[15]
    
            # Split the 16th field by '/' and extract the first part
            field_1 = field_16.split('/')[0]
    
            # Increment the count of the extracted field
            field_counts[field_1] += 1

            if response_code_info.strip() == "200":  
                response_times.append(response_time_info)
        
            else:
                count_not_200_response_codes += 1

    ''' TO DO: Handle ValueError: max() arg is an empty sequence if no request comes to the application. '''
    if len(field_counts) == 0:
        print(f"No response time has been read.")
        return
    
    # Find the field with the highest occurrence
    max_field = max(field_counts, key=field_counts.get)

    # Get the count of the most frequent field
    max_count = field_counts[max_field]

    arrival_rate = max_field
    
    # req/s should be same with arrival rate.
    request_per_second = arrival_rate
        
    drop_rate = count_not_200_response_codes / count_all_response_codes

    average_rt = stat.mean(response_times)

    perct = np.percentile(response_times, percentile)

    service_rate = int((count_all_response_codes - count_not_200_response_codes) / sampling_time)

    print(f"Iteration: {curr_iteration}, Estimated number of request: {request_per_second}, Average response time: {average_rt}, {percentile}th response time: {perct}")

    if average_rt <= 1:
        print(f"No (logical) response time has been read.")
    
    else:
        mean_response_time_data.append((curr_iteration, average_rt))
        tail_response_time_data.append((curr_iteration, perct))
        error_data.append((curr_iteration, target_slo - perct))
        estimated_number_of_request_data.append((curr_iteration, request_per_second))
        drop_percentage_data.append((curr_iteration, drop_rate))
        service_rate_data.append((curr_iteration, service_rate))
        log_data[curr_iteration] = log_lines


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


def write_to_file( mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_data,  allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data ):
    # Latency-sensitive specific data
    with open(f_mean_rt, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in mean_response_time_data))

    with open(f_tail_rt, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in tail_response_time_data))

    with open(f_error_value, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in error_data))

    with open(f_est_number_of_request, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in estimated_number_of_request_data))
    
    with open(f_drop_percent, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in drop_percentage_data))
    
    with open(f_service_rate, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in service_rate_data))

    with open(f_log_file, 'wb') as filehandle:
        pickle.dump(log_data, filehandle)

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


def run_manager(log_file_latency, latency_ref_input):
    # Latency-sensitive application variables
    mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data = [], [], [], [], [], [], [], []
    log_records = {}
    # System telemetry variables
    measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []

    ''' To keep configuration variables '''
    config_dict = {}

    with open(config_file, "r") as f:
        config_dict = json.load(f)

    cluster_size = config_dict["system_configs"]["cluster_size"]
    sampling_time = config_dict["system_configs"]["sampling_time"]
    host_min_power = config_dict["system_configs"]["min_power"]
    host_max_power = config_dict["system_configs"]["max_power"]
    rt_percentile = config_dict["system_configs"]["rt_percentile"]
    application_sub_path = config_dict["system_configs"]["mediawiki_sub_path"]

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
    
    print(f"Reference input of the latency-sensitive application: {latency_ref_input} ms.")

    iteration_counter = 0

    while True:
        prev_hash_latency = hash_file(log_file_latency)
        time.sleep(2)

        if prev_hash_latency != hash_file(log_file_latency):
            break

    # Wait 5 seconds for warm-up.
    time.sleep(5)

    for alloc_core in CORE_ALLOCATIONS:
        for m1 in machines["machines"]["core_allocator"]:
            for m2 in m1["container_name"]:
                step1_output = run_core_number_allocator(m1["ip"], m1["port"], m2, alloc_core)

                if step1_output == True:
                    print(f"{alloc_core} core(s) has been allocated to {m2} hosted on {m1['ip']}.")

                else:
                    with open(info_log_file, "a") as f:
                        f.write(f"Iteration: {iteration_counter} - {alloc_core} core(s) could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

        for alloc_quota in CPU_QUOTAS:
            for m1 in machines["machines"]["core_allocator"]:
                for m2 in m1["container_name"]:
                    step2_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, alloc_core * alloc_quota)

                    if step2_output == True:
                        print(f"{alloc_quota}% cpu bandwidth limit has been allocated per core for {m2} hosted on {m1['ip']}.")

                    else:
                        with open(info_log_file, "a") as f:
                            f.write(f"Iteration: {iteration_counter} - {alloc_quota}% cpu bandwidth per core could not been allocated for the container {m2} hosted on {m1['ip']}.\n")

            # Wait for 2 seconds to make sure that new configuration is in effect.
            time.sleep(2)

            for _ in range(EXPERIMENT_REPEAT_TIMES):
                subprocess.run(['truncate', '-s', '0', log_file_latency], stdout=subprocess.PIPE)

                print("HAProxy log file is cleared for the next iteration.")

                time.sleep(sampling_time)

                # Latency-sensitive application part
                t1 = threading.Thread( target=sample_latency_sensitive_log, args=(log_file_latency, application_sub_path, rt_percentile, sampling_time, mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_records, iteration_counter, latency_ref_input,) )
                
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
                allocated_number_of_core_data.append((iteration_counter, alloc_core))

                # Adding allocated core bandwidth data info into the list.
                allocated_cpu_bandwidth_data.append((iteration_counter, alloc_quota))

                iteration_counter += 1
                
                if len(mean_response_time_data) != 0 and len(tail_response_time_data) != 0:
                    print("Recording data to files...")
                    
                    write_to_file( mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_records, allocated_number_of_core_data, allocated_cpu_bandwidth_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data )

                # reset latency-sensitive application variables
                mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, allocated_number_of_core_data, allocated_cpu_bandwidth_data = [], [], [], [], [], [], [], []

                # reset system telemetry variables
                measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Application Telemetry Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Latency-sensitive arguments
    parser.add_argument("-llf", "--l-log-file", default="/var/log/haproxy.log", help="HAProxy log file location")
    parser.add_argument("-lts", "--l-target-slo", default=150, type=int, help="target SLO response time for latency-sensitive application")

    parser.add_argument("-mrt", "--mean-rt", default="./data/real-rt.txt", help="File to keep measured response time")
    parser.add_argument("-trt", "--tail-rt", default="./data/tail-rt.txt", help="File to keep measured tail response times")
    parser.add_argument("-ev", "--error-value", default="./data/error-value.txt", help="File to keep error value")
    parser.add_argument("-er", "--est-number-of-request", default="./data/est-number-of-request.txt", help="File to keep estimated number of request")
    parser.add_argument("-dp", "--drop-percent", default="./data/drop-percentage.txt", help="File to keep percentage of dropped requests")
    parser.add_argument("-sr", "--service-rate", default="./data/service-rate.txt", help="File to keep service rate")
    parser.add_argument("-lf", "--log-file", default="./data/log-file.txt", help="File to keep interested log file columns")

    parser.add_argument("-anc", "--allocated-number-of-core", default="./data/allocated-number-of-core.txt", help="File to keep allocated number of core")
    parser.add_argument("-acb", "--allocated-cpu-bandwidth", default="./data/allocated-cpu-bandwidth.txt", help="File to keep allocated cpu bandwidth")
        
    # System telemetry
    parser.add_argument("-cp", "--measured-cpu-power", default="./data/measured_cpu_power.txt", help="File to measured cpu power")
    parser.add_argument("-sp", "--measured-server-power", default="./data/measured_server_power.txt", help="File to measured server power")
    parser.add_argument("-cf", "--cpu-frequency", default="./data/cpu_frequency.txt", help="File to keep cpu frequency")
    parser.add_argument("-cu", "--cpu-utilization", default="./data/cpu_utilization.txt", help="File to keep cpu utilization")
    
    args = parser.parse_args()
    
    # Latency sentitive app
    f_mean_rt = args.mean_rt
    f_tail_rt = args.tail_rt
    f_error_value = args.error_value
    f_est_number_of_request = args.est_number_of_request
    f_drop_percent = args.drop_percent
    f_service_rate = args.service_rate
    f_log_file = args.log_file

    f_allocated_number_of_core = args.allocated_number_of_core    # File for keeping allocated number of core data
    f_allocated_cpu_bandwidth = args.allocated_cpu_bandwidth      # File for keeping allocated core usage data

    # System telemetries    
    f_measured_cpu_power = args.measured_cpu_power            # File for keeping measured cpu power consumption
    f_measured_server_power = args.measured_server_power      # File for keeping measured cpu power consumption
    f_cpu_freq = args.cpu_frequency                           # File for keeping cpu frequency
    f_cpu_util = args.cpu_utilization                         # File for keeping cpu utilization
    
    run_manager(args.l_log_file, args.l_target_slo)