import cpu_limit_capper_pb2 as pb2_cpu_limit_capper
import cpu_limit_capper_pb2_grpc as pb2_cpu_limit_capper_grpc
import container_service_pb2 as pb2_container_service
import container_service_pb2_grpc as pb2_container_service_grpc
import rapl_power_monitor_per_socket_pb2 as pb2_monitor
import rapl_power_monitor_per_socket_pb2_grpc as pb2_monitor_grpc
from Utility import Utility
import argparse
import grpc
import time
import math
import subprocess
import json
import os
import pandas as pd
import statistics as stat
from collections import defaultdict
import numpy as np
import threading
import re
import pickle
import timeit
import csv

# Latency sentitive app
f_mean_rt, f_tail_rt, f_error_value, f_est_number_of_request, f_actual_number_of_request, f_drop_percent, f_service_rate, f_log_file, f_rps_prediction, f_rps_next = "", "", "", "", "", "", "", "", "", ""
# Batch-application
f_progress, f_progress_percentage = "", ""
# System telemetries
f_measured_cpu_power, f_measured_server_power, f_cpu_util, f_cpu_freq, f_allocated_number_of_core, f_allocated_cpu_quota, f_power_cap_values, f_system_decision = "", "", "", "", "", "", "", ""

# machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/single_machine.json"
machines_config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/single_machine.json"
config_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/config-files/cluster_manager_config.json"
info_log_file = "/nfs/obelix/raid2/msavasci/Diagonal-Scaler-Experiment-Data/IGSC24/Experiment-1/info_log.txt"
power_cap_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/data/power_cap_data_fixed.csv"
workload_file = "/nfs/obelix/users1/msavasci/PARS/diagonal-scaling/system-implementation/data/wikipedia-workload-data.csv"
workload_index_file = "/nfs/obelix/raid2/msavasci/workload_index_file.txt"

my_utility = Utility()

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
        
    task_done = 0

    for line in log_lines:
        # Find all matches in the line
        matches = re.findall(pattern, line)

        # For the provided sample log
        # if len(matches) == column_count and (ntype in matches[2].lower()) and (template_id in matches[3].lower()) and (event in matches[8].lower()):
        
        # For the real log
        if len(matches) == column_count and (ntype in matches[5].lower()) and (template_id in matches[3].lower()) and (event in matches[4].lower()):
            task_done += 1

        # Print the parsed result
        # print(matches)

    print(f"Iteration: {curr_iteration}, Completed number of tasks: {task_done}.")

    # Add iteration progress value into list.
    iteration_progress_data.append((curr_iteration, task_done))

    curr_progress_percentage = task_done / target_slo
    # Add current progress percentage value into list.
    progress_percentage_data.append((curr_iteration, curr_progress_percentage * 100))

    tmp_progress = curr_progress_percentage + iteration_tracker.pop()
    iteration_tracker.append(tmp_progress)

    print(f"{iteration_tracker[0] * 100:.2f}% completed...")


# This method returns [200 code response times, average response time, tail latency, #req/s, log_data, drop_rate, arrival_rate, service_rate] in this order
def sample_latency_sensitive_log(log_file, application_sub_path, percentile, sampling_time, mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_data, curr_iteration, target_slo):
    log_lines, response_times = [], []
    count_all_response_codes, count_not_200_response_codes = 0, 0

    with open(log_file) as f: 
        # read log lines and store it in list
        log_lines = f.readlines()

    if len(log_lines) == 0:
        mean_response_time_data.append((curr_iteration, 0))
        tail_response_time_data.append((curr_iteration, 0))
        error_data.append((curr_iteration, 0))
        estimated_number_of_request_data.append((curr_iteration, 0))
        drop_percentage_data.append((curr_iteration, 0))
        service_rate_data.append((curr_iteration, 0))
        log_data[curr_iteration] = log_lines

        return
    
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

    service_rate = int(count_all_response_codes / sampling_time)

    print(f"Iteration: {curr_iteration}, Estimated number of request: {request_per_second}, Average response time: {average_rt}, {percentile}th response time: {perct}")

    if average_rt <= 1:
        print(f"No (logical) response time has been read.")
    
    else:
        mean_response_time_data.append((curr_iteration, average_rt))
        tail_response_time_data.append((curr_iteration, perct))
        error_data.append((curr_iteration, target_slo - perct))
        estimated_number_of_request_data.append((curr_iteration, int(request_per_second)))
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


def write_to_file( mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, actual_number_of_request_data, drop_percentage_data, service_rate_data, log_data, rps_prediction_data, rps_actual_next_data, iteration_progress_data, progress_percentage_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data, allocated_number_of_core_data, allocated_cpu_quota_data, power_cap_values_data, system_decision_data ):
    # Batch-application specific data
    with open(f_progress, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in iteration_progress_data))

    with open(f_progress_percentage, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]:.2f}),' for tup in progress_percentage_data))
    
    # Latency-sensitive specific data
    with open(f_mean_rt, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in mean_response_time_data))

    with open(f_tail_rt, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in tail_response_time_data))

    with open(f_error_value, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in error_data))

    with open(f_est_number_of_request, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in estimated_number_of_request_data))

    with open(f_actual_number_of_request, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in actual_number_of_request_data))
    
    with open(f_drop_percent, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in drop_percentage_data))
    
    with open(f_service_rate, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in service_rate_data))

    with open(f_log_file, 'wb') as filehandle:
        pickle.dump(log_data, filehandle)

    with open(f_rps_prediction, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in rps_prediction_data))

    with open(f_rps_next, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in rps_actual_next_data))

    # System telemetry data
    with open(f_measured_cpu_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in measured_cpu_power_data))

    with open(f_measured_server_power, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in measured_server_power_data))

    with open(f_cpu_util, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}","{tup[2]}",{tup[3]}),' for tup in cpu_util_data))

    with open(f_cpu_freq, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]}),' for tup in cpu_freq_data))

    with open(f_allocated_number_of_core, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}","{tup[2]}",{tup[3]}),' for tup in allocated_number_of_core_data))

    with open(f_allocated_cpu_quota, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}","{tup[2]}",{tup[3]}),' for tup in allocated_cpu_quota_data))

    with open(f_power_cap_values, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},{tup[1]}),' for tup in power_cap_values_data))

    with open(f_system_decision, 'a', encoding='utf-8') as filehandle:
        filehandle.write(''.join(f'({tup[0]},"{tup[1]}",{tup[2]},{tup[3]},"{tup[4]}"),' for tup in system_decision_data))


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

    return int(lined_output.split(',')[5])


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
        # cpu_usage = max(0.01, min(cpu_usage, s.cpu_usage))
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


# This method predicts the arrival rate or cpu usage based on given data.
def predict_best_fit_point(data, window_size):
    if len(data) == 1:
        return data[-1]

    elif len(data) < window_size:
        m_window_size = len(data)

    else:
        m_window_size = window_size

    x = np.arange(m_window_size)
    y = np.array(data[-m_window_size:])

    coeff = np.polyfit(x, y, 1)

    yn = np.poly1d(coeff)

    return yn(m_window_size)


# This function returns upper active power consumption bound of given number of cores.     
def core_power_limit(number_of_cores):    
    # The following equation has been derived for acpi_freq driver with performance governor.
    return math.floor(2.8 * number_of_cores + 46.6)


# This function return performance value given number of cores and quota.
def compute_perf_value_of_core_quota(core_value, quota_value):
    # Equation is based on Blast application profile data: perf = 0.79 * #cores + 0.04 * cpu_quota - 2.3
    return 0.79 * core_value + 0.04 * quota_value - 2.3


# Given power value, this function computes the equivalent number of cores and cpu quota.
def convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_step, power_value):
    # Equation is based on Blast application profile data: power_cons = 2.07 * #cores + 0.48 * cpu_quota - 3.6
    quota_values = range(min_quota, max_quota, quota_step)
    
    conf_candidates = []

    for quota in quota_values:
        # number_of_cores = round((power_value + 3.6 - 0.48 * quota) / 2.07)
        number_of_cores = math.floor((power_value + 3.6 - 0.48 * quota) / 2.07)

        print(f"Computed number of core: {number_of_cores}, quota: {quota}")
        
        if number_of_cores < 0:
            break

        conf_candidates.append((number_of_cores, quota))
        # conf_candidates.append((min(max_core, number_of_cores), quota))
 
    print(f"Configuration candidates: {conf_candidates}")

    return conf_candidates


# Given power value, this function computes the equivalent number of cores and cpu quota.
def convert_from_power_to_cpu_core_quota_quota_first(min_core, max_core, min_quota, max_quota, quota_step, power_value):
    # Equation is based on Blast application profile data: power_cons = 2.07 * #cores + 0.48 * cpu_quota - 3.6
    core_values = range(min_core, max_core, 1)
    
    conf_candidates = []

    for core in core_values:
        # number_of_cores = round((power_value + 3.6 - 0.48 * quota) / 2.07)
        quota = math.floor((power_value + 3.6 - 2.07 * core) / 0.48)

        print(f"Computed number of core: {core}, quota: {quota}")
        
        if quota < 0:
            break

        conf_candidates.append((core, quota))
 
    print(f"Configuration candidates: {conf_candidates}")

    return conf_candidates


# Given request per second (rps), this function computes power consumption.
def mw_rps_power_model(rps):
    # Equation is based on Mediwaiki application profile data: power_cons = 0.52 * rps + 19.8
    return 0.52 * rps + 19.8


# Given request per second (rps), this function computes cpu utilization.
def mw_rps_to_cpu_util(rps):
    return 1.45 * rps + 1.65


def reactive_scaling(min_core, max_core, min_quota, max_quota, quota_up_step, quota_down_step, curr_batch_cpu_util, curr_int_cpu_util, curr_cpu_core, curr_cpu_quota, power_value, lower_threshold):
    selected_candidates = {}
    
    # Capping value is greater consumption. So, increase the power consumption.
    if power_value > lower_threshold:
        candidates = convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_up_step, power_value)
        
        for cand in candidates:
            new_cpu_util = min(max_core * max_quota, curr_cpu_quota + cand[1] * cand[0]) / min(max_core, curr_cpu_core + cand[0])

            if new_cpu_util < min_quota:
                continue

            if new_cpu_util > curr_batch_cpu_util and new_cpu_util < (100 - curr_int_cpu_util):
                selected_candidates[cand] = compute_perf_value_of_core_quota(cand[0], cand[1])

        if len(selected_candidates) != 0:
            # Sorted in descending order
            tmp_sorted = sorted(selected_candidates.items(), key=lambda x:x[1], reverse=True)
            sorted_selected_candidates_by_perf = dict(tmp_sorted)

            print(f"if --> Selected candidates: {selected_candidates}")
            print(f"if --> Selected candidates after sorting: {sorted_selected_candidates_by_perf}")

            return list(sorted_selected_candidates_by_perf.keys())[0][0], list(sorted_selected_candidates_by_perf.keys())[0][1], "positive"

        # added_cpu_core = max_core - curr_cpu_core
        # added_cpu_quota = curr_cpu_core * curr_batch_cpu_util - curr_cpu_quota + curr_batch_cpu_util * added_cpu_core

        # return added_cpu_core, math.floor(added_cpu_quota)

        # return min_core, min_quota
        return 0, min_quota, "positive"

    # Capping value is greater consumption. So, decrease the power consumption.
    elif power_value < 0:
        candidates = convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_down_step, abs(power_value))

        for cand in candidates:
            if curr_cpu_quota <= cand[1] * cand[0] or curr_cpu_core <= cand[0]:
                continue

            new_cpu_util = (curr_cpu_quota - cand[1] * cand[0]) / (curr_cpu_core - cand[0])

            if new_cpu_util < min_quota:
                continue

            if new_cpu_util < curr_batch_cpu_util and new_cpu_util < (100 - curr_int_cpu_util):
                selected_candidates[cand] = compute_perf_value_of_core_quota(cand[0], cand[1])

        if len(selected_candidates) != 0:
            # Sorted in ascending order
            tmp_sorted = sorted(selected_candidates.items(), key=lambda x:x[1])
            sorted_selected_candidates_by_perf = dict(tmp_sorted)

            print(f"if --> Selected candidates: {selected_candidates}")
            print(f"if --> Selected candidates after sorting: {sorted_selected_candidates_by_perf}")

            return -list(sorted_selected_candidates_by_perf.keys())[0][0], list(sorted_selected_candidates_by_perf.keys())[0][1], "negative"

        return -min_core, math.ceil(curr_cpu_quota / 2), "negative"
        
        # return -int(max_core / 2), int(max_quota / 2)

        # removed_cpu_core = curr_cpu_core - min_core
        # removed_cpu_quota = curr_cpu_core * curr_batch_cpu_util + curr_cpu_quota - curr_batch_cpu_util * removed_cpu_core

        # return -removed_cpu_core, math.floor(removed_cpu_quota)

    else:
        return 0, 0, "none"


def proactive_scaling(min_core, max_core, min_quota, max_quota, quota_up_step, quota_down_step, curr_batch_cpu_util, curr_int_cpu_util, curr_cpu_core, curr_cpu_quota, power_value, rps_change, lower_threshold, mw_cpu_util_buffer, lower_rps_change_limit):
    selected_candidates = {}

    # If rps prediction shows decrease in rps, then increase (if power budget stays same) the cpu core and quota given to the batch application.
    if rps_change < lower_rps_change_limit:
        predicted_server_power_cons_change = mw_rps_power_model(abs(rps_change))
        cpu_util_change = -mw_rps_to_cpu_util(abs(rps_change))

    elif rps_change > lower_rps_change_limit:
        predicted_server_power_cons_change = -mw_rps_power_model(rps_change)
        cpu_util_change = mw_rps_to_cpu_util(rps_change)

    else:
        predicted_server_power_cons_change, cpu_util_change = 0, 0
            
    # power_change = power_value + predicted_server_power_cons_change
    power_change = predicted_server_power_cons_change

    # If power change is greater than threshold, we can scale the batch up. 
    if power_change > lower_threshold: 
        candidates = convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_up_step, power_change)
        
        for cand in candidates:
            new_cpu_util = min(max_core * max_quota, curr_cpu_quota + cand[1] * cand[0]) / min(max_core, curr_cpu_core + cand[0])
            
            if new_cpu_util < min_quota:
                continue

            if new_cpu_util > curr_batch_cpu_util and new_cpu_util < (100 - (curr_int_cpu_util + cpu_util_change - mw_cpu_util_buffer)):
                selected_candidates[cand] = compute_perf_value_of_core_quota(cand[0], cand[1])

        if len(selected_candidates) != 0:
            # Sorted in descending order
            tmp_sorted = sorted(selected_candidates.items(), key=lambda x:x[1], reverse=True)
            sorted_selected_candidates_by_perf = dict(tmp_sorted)

            print(f"if --> Selected candidates: {selected_candidates}")
            print(f"if --> Selected candidates after sorting: {sorted_selected_candidates_by_perf}")

            return list(sorted_selected_candidates_by_perf.keys())[0][0], list(sorted_selected_candidates_by_perf.keys())[0][1], "positive"

        # added_cpu_core = max_core - curr_cpu_core
        # added_cpu_quota = curr_cpu_core * curr_batch_cpu_util - curr_cpu_quota + curr_batch_cpu_util * added_cpu_core

        # return added_cpu_core, math.floor(added_cpu_quota)

        # return min_core, min_quota
        return 0, min_quota, "positive"
    
    # Capping value is greater than consumption. So, decrease the power consumption.
    elif power_change < 0:
        candidates = convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_down_step, abs(power_change))

        for cand in candidates:
            if curr_cpu_quota <= cand[1] * cand[0] or curr_cpu_core <= cand[0]:
                continue

            new_cpu_util = (curr_cpu_quota - cand[1] * cand[0]) / (curr_cpu_core - cand[0])

            if new_cpu_util < min_quota:
                continue

            if new_cpu_util < curr_batch_cpu_util and new_cpu_util < (100 - (curr_int_cpu_util + cpu_util_change - mw_cpu_util_buffer)):
                selected_candidates[cand] = compute_perf_value_of_core_quota(cand[0], cand[1])

        if len(selected_candidates) != 0:
            # Sorted in ascending order
            tmp_sorted = sorted(selected_candidates.items(), key=lambda x:x[1])
            sorted_selected_candidates_by_perf = dict(tmp_sorted)

            print(f"if --> Selected candidates: {selected_candidates}")
            print(f"if --> Selected candidates after sorting: {sorted_selected_candidates_by_perf}")

            return -list(sorted_selected_candidates_by_perf.keys())[0][0], list(sorted_selected_candidates_by_perf.keys())[0][1], "negative"

        # return -int(max_core / 2), int(max_quota / 2)
        return -min_core, math.ceil(curr_cpu_quota / 2), "negative"
    
    else:
        return 0, 0, "none"
    

def reactive_with_proactive_scaling(min_core, max_core, min_quota, max_quota, quota_down_step, curr_batch_cpu_util, curr_int_cpu_util, curr_cpu_core, curr_cpu_quota, power_value, rps_change, mw_cpu_util_buffer, lower_rps_change_limit):
    selected_candidates = {}

    if rps_change > lower_rps_change_limit:
        power_change = power_value - mw_rps_power_model(rps_change)
        cpu_util_change = mw_rps_to_cpu_util(rps_change)

    else:
        power_change = power_value
        cpu_util_change = 0

    m_mw_cpu_util_buffer = -mw_cpu_util_buffer

    candidates = convert_from_power_to_cpu_core_quota(min_core, max_core, min_quota, max_quota, quota_down_step, abs(power_change))

    for cand in candidates:
        if curr_cpu_quota <= cand[1] * cand[0] or curr_cpu_core <= cand[0]:
            continue

        new_cpu_util = (curr_cpu_quota - cand[1] * cand[0]) / (curr_cpu_core - cand[0])

        if new_cpu_util < min_quota:
            continue

        if new_cpu_util < curr_batch_cpu_util and new_cpu_util < (100 - (curr_int_cpu_util + cpu_util_change + m_mw_cpu_util_buffer)):
            selected_candidates[cand] = compute_perf_value_of_core_quota(cand[0], cand[1])

    if len(selected_candidates) != 0:
        # Sorted in ascending order
        tmp_sorted = sorted(selected_candidates.items(), key=lambda x:x[1])
        sorted_selected_candidates_by_perf = dict(tmp_sorted)

        print(f"if --> Selected candidates: {selected_candidates}")
        print(f"if --> Selected candidates after sorting: {sorted_selected_candidates_by_perf}")

        return -list(sorted_selected_candidates_by_perf.keys())[0][0], list(sorted_selected_candidates_by_perf.keys())[0][1], "negative"

    return -min_core, math.ceil(curr_cpu_quota / 2), "negative"
    
    # return -int(max_core / 2), int(max_quota / 2)

    # removed_cpu_core = curr_cpu_core - min_core
    # removed_cpu_quota = curr_cpu_core * curr_batch_cpu_util + curr_cpu_quota - curr_batch_cpu_util * removed_cpu_core

    # return -removed_cpu_core, math.floor(removed_cpu_quota)

    
def apply_core_quota_changes(core_change, quota_change, status, machines, machine_curr_number_of_cores, machine_curr_core_usage_limits, container_subname, min_core, max_core, min_quota, max_quota, iteration, allocated_number_of_core_data, allocated_cpu_quota_data):
    for m1 in machines["machines"]["core_allocator"]:
        for m2 in m1["container_name"]:
            if container_subname in m2.lower():
                curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
                curr_cpu_quotas = machine_curr_core_usage_limits[(m1["ip"], m2)]

                new_cpu_cores = min(max_core, max(min_core, curr_cpu_cores + core_change))

                if core_change == 0 and status == "positive":
                    core_change = 1
                
                if core_change == 0 and status == "negative":
                    core_change = -1

                new_cpu_quotas = min(new_cpu_cores * max_quota, max(min_quota, curr_cpu_quotas + core_change * quota_change))

                step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
                step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_quotas)

                if step2_core_output == True and step2_quota_output == True:
                    print(f"{new_cpu_cores} cores and {new_cpu_quotas}ms/100ms quota has been allocated for {m2} hosted on {m1['ip']}.")

                    machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
                    machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

                    allocated_number_of_core_data.append((iteration, m1["ip"], m2, new_cpu_cores))
                    allocated_cpu_quota_data.append((iteration, m1["ip"], m2, new_cpu_quotas))

                    return new_cpu_cores, new_cpu_quotas
                
                else:
                    with open(info_log_file, "a") as f:
                        print(f"Iteration: {iteration} : {new_cpu_cores} cores and {new_cpu_quotas}ms/100ms quota has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

                    step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
                    step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_quotas)

                    machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
                    machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quotas

                    allocated_number_of_core_data.append((iteration, m1["ip"], m2, curr_cpu_cores))
                    allocated_cpu_quota_data.append((iteration, m1["ip"], m2, curr_cpu_quotas))

                    return curr_cpu_cores, curr_cpu_quotas


# Function to read power cap values from a CSV file
def read_from_csv(filename):
    with open(filename, newline='') as f:
        reader = csv.reader(f)
        data = list(reader)

    return data[0]

    
def run_manager(log_file_latency, latency_ref_input, log_file_batch, batch_ref_input):
    # Latency-sensitive application variables
    mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, actual_number_of_request_data, drop_percentage_data, service_rate_data, rps_prediction_data, rps_actual_next_data = [], [], [], [], [], [], [], [], []
    log_records = {}
    # Batch application variables
    iteration_progress_data, progress_percentage_data, iteration_tracker = [], [], []
    # System telemetry variables
    measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data, allocated_number_of_core_data, allocated_cpu_quota_data, power_cap_values_data, system_decision_data = [], [], [], [], [], [], [], []
    # Decision variables
    rps_window = []

    # power_budgets = [120]
    power_budgets = read_from_csv(power_cap_file)
    workload_traces = read_from_csv(workload_file)

    power_cap_index = 1

    iteration_counter = 0

    iteration_tracker.append(0)

    ''' To keep configuration variables '''
    config_dict = {}

    with open(config_file, "r") as f:
        config_dict = json.load(f)

    cluster_size = config_dict["system_configs"]["cluster_size"]
    sampling_time = config_dict["system_configs"]["sampling_time"]
    blast_sampling_time = config_dict["system_configs"]["blast_sampling_time"]
    host_min_power = config_dict["system_configs"]["min_power"]
    host_max_power = config_dict["system_configs"]["max_power"]
    rt_percentile = config_dict["system_configs"]["rt_percentile"]
    application_sub_path = config_dict["system_configs"]["mediawiki_sub_path"]
    rps_window_size = config_dict["system_configs"]["rps_window_size"]
    blast_min_core = config_dict["system_configs"]["blast_min_core"]
    blast_min_quota = config_dict["system_configs"]["blast_min_quota"]
    max_cpu_quota = config_dict["system_configs"]["max_cpu_quota"]
    min_cpu_core = config_dict["system_configs"]["min_core"]
    max_cpu_core = config_dict["system_configs"]["max_core"]
    blast_quota_up_step = config_dict["system_configs"]["blast_up_quota_steps"]
    blast_quota_down_step = config_dict["system_configs"]["blast_down_quota_steps"]
    power_cap_guard = config_dict["system_configs"]["power_cap_guard"]
    lower_rps_change_limit = config_dict["system_configs"]["min_rps_change_limit"]
    min_power_increase_limit = config_dict["system_configs"]['min_power_increase_limit']

    with open(machines_config_file) as f:
        machines = json.load(f)

    machine_curr_number_of_cores, machine_curr_core_usage_limits = {}, {}

    for m1 in machines["machines"]["container_service"]:
        for m2 in m1["container_name"]:
            machine_curr_number_of_cores[(m1["ip"], m2)] = retrieve_container_core_information(m1["ip"], m1["port"], m2)
            curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
            
            machine_curr_core_usage_limits[(m1["ip"], m2)] = int(retrieve_container_core_usage_limit_information(m1["ip"], m1["port"], m2).split('/')[0])
            
            curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

            # allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
            # allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                

    print(f"Total number of machines in the cluster: {cluster_size}")
    print(f"Min power limit of nodes: {host_min_power}")
    print(f"Max power limit of nodes: {host_max_power}")

    print(f"Current core info of containers: {machine_curr_number_of_cores}")
    print(f"Current core usage limits of containers: {machine_curr_core_usage_limits}")
    
    print(f"Reference input of the latency-sensitive application: {latency_ref_input} ms.")
    print(f"Reference input of the batch application: {batch_ref_input} task(s).")

    while True:
        prev_hash_latency = hash_file(log_file_latency)
        prev_hash_batch = hash_file(log_file_batch)
        time.sleep(2)

        if prev_hash_latency != hash_file(log_file_latency) or prev_hash_batch != hash_file(log_file_batch):
            break

    # Wait 5 seconds for warm-up.
    time.sleep(5)

    subprocess.run(['truncate', '-s', '0', log_file_latency], stdout=subprocess.PIPE)
    subprocess.run(['truncate', '-s', '0', log_file_batch], stdout=subprocess.PIPE)
    print("HAProxy and Blast log files are cleared for the initialization.")

    batch_flag = False

    curr_time = timeit.default_timer()

    power_cap_timer = timeit.default_timer()

    original_power_budget = int(float(power_budgets[power_cap_index]))
    curr_power_budget = math.floor(original_power_budget * power_cap_guard)

    mw_cpu_util_buffer = 0

    while True:
        subprocess.run(['truncate', '-s', '0', log_file_latency], stdout=subprocess.PIPE)
        print("HAProxy log file is cleared for the next iteration.")

        time.sleep(sampling_time)

        iteration_counter += 1

        threads = []

        # Latency-sensitive application part
        t1 = threading.Thread( target=sample_latency_sensitive_log, args=(log_file_latency, application_sub_path, rt_percentile, sampling_time, mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, drop_percentage_data, service_rate_data, log_records, iteration_counter, latency_ref_input,) )
        threads.append(t1)
        
        # Batch application part
        if timeit.default_timer() - curr_time >= blast_sampling_time:
            t2 = threading.Thread( target=sample_blast_log, args=(log_file_batch, r'(?:[^\s"]+|"[^"]*")+', 9, 'task', 'parallel', 'done', iteration_progress_data, progress_percentage_data, iteration_tracker, iteration_counter, batch_ref_input,))
            threads.append(t2)
            
            batch_flag = True

        # System telemetry part
        t3 = threading.Thread( target=sample_cpu_power_consumption, args=(machines, measured_cpu_power_data, iteration_counter,))
        threads.append(t3)

        t4 = threading.Thread( target=sample_server_power_consumption, args=(machines, measured_server_power_data, iteration_counter,))
        threads.append(t4)

        t5 = threading.Thread( target=sample_cpu_freq, args=(machines, cpu_freq_data, iteration_counter,))
        threads.append(t5)

        t6 = threading.Thread( target=sample_cpu_util, args=(machines, cpu_util_data, iteration_counter,))
        threads.append(t6)

        for my_thread in threads:
            my_thread.start()
        
        for my_thread in threads:
            my_thread.join()

        if batch_flag == True:
            subprocess.run(['truncate', '-s', '0', log_file_batch], stdout=subprocess.PIPE)
            print("Blast log file is cleared for the next iteration.")
            curr_time = timeit.default_timer()
            batch_flag = False
        
        if timeit.default_timer() - power_cap_timer >= 10:
            if power_cap_index == len(power_budgets):
                break

            original_power_budget = int(float(power_budgets[power_cap_index]))
            curr_power_budget = math.floor(original_power_budget * power_cap_guard)
            power_cap_index += 1
            power_cap_timer = timeit.default_timer()

        power_cap_values_data.append((iteration_counter, original_power_budget))
        
        curr_server_power_cons = measured_server_power_data[-1][2]

        print(f"Current power budget: {curr_power_budget}, curr power consumption: {curr_server_power_cons}")

        # with open(workload_index_file, 'r') as file:
        #     w_index = file.read()
        with open(workload_index_file, 'r') as infile:
            lines = infile.readlines()

        if len(lines) == 0:
            with open(info_log_file, "a") as f:
                print(f"Iteration: {iteration_counter} : Workload info could not been read from the index file. Iteration will be repeated.")

            rps_prediction_data, rps_actual_next_data, allocated_number_of_core_data, allocated_cpu_quota_data, power_cap_values_data, system_decision_data = [], [], [], [], [], []
            # reset latency-sensitive application variables
            mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, actual_number_of_request_data, drop_percentage_data, service_rate_data = [], [], [], [], [], [], []
            # reset batch application variables
            iteration_progress_data, progress_percentage_data = [], []
            # reset system telemetry variables
            measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []
            
            continue

        w_index = int(lines[0].strip())

        if w_index == len(workload_traces):
            break

        curr_estimated_rps = int(estimated_number_of_request_data[-1][1])
        curr_actual_rps = int(workload_traces[w_index])
        next_rps = int(workload_traces[w_index + 1])

        rps_window.append(curr_estimated_rps)

        actual_number_of_request_data.append((iteration_counter, curr_actual_rps))
        
        rps_actual_next_data.append((iteration_counter, next_rps))
        
        predicted_next_rps = round(predict_best_fit_point(rps_window, rps_window_size))

        rps_prediction_data.append((iteration_counter, predicted_next_rps))

        print(f"CURR LOAD FROM LOG FILE: {curr_estimated_rps}")
        print(f"CURR LOAD FROM TRACE: {curr_actual_rps}")
        print(f"NEXT PREDICTED LOAD FROM LOG FILE: {predicted_next_rps}")
        print(f"NEXT LOAD FROM TRACE: {next_rps}")

        diff_rps = next_rps - curr_actual_rps

        tmp_cpu_util_batch, instance_counter_batch = 0, 0
        tmp_cpu_util_int, instance_counter_int = 0, 0

        for vals in cpu_util_data:
            if "blast" in vals[2].lower():
                tmp_cpu_util_batch += float(vals[3]) * 100
                instance_counter_batch += 1

            if "mediawiki" in vals[2].lower():
                tmp_cpu_util_int += float(vals[3]) * 100
                instance_counter_int += 1

        print(f"Current cpu util batch: {tmp_cpu_util_batch}, Number of instance batch: {instance_counter_batch}")
        print(f"Current cpu util interactive: {tmp_cpu_util_int}, Number of instance interactive: {instance_counter_int}")

        curr_cpu_util_batch = tmp_cpu_util_batch / max(1, instance_counter_batch)
        
        curr_cpu_util_int = tmp_cpu_util_int / max(1, instance_counter_int)

        system_dec = "none"

        power_error = curr_power_budget - curr_server_power_cons

        # Reactive scaling part
        if power_error < 0:
            print(f"Detected exceeding the power cap. Reactive with proactive scaling decision is being taken...")
            core_change, quota_change, status = reactive_with_proactive_scaling(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_down_step, curr_cpu_util_batch, curr_cpu_util_int, curr_cpu_cores, curr_cpu_quota, power_error, diff_rps, mw_cpu_util_buffer, lower_rps_change_limit)
            system_dec = "reactive_with_proactive"

        elif power_error >= 0 and diff_rps > lower_rps_change_limit:
            print(f"Detected an increase in rps --> {diff_rps}. Proactive scaling decision is being taken...")
            core_change, quota_change, status = proactive_scaling(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_up_step, blast_quota_down_step, curr_cpu_util_batch, curr_cpu_util_int, curr_cpu_cores, curr_cpu_quota, power_error, diff_rps, min_power_increase_limit, mw_cpu_util_buffer, lower_rps_change_limit)
            system_dec = "proactive"

        else:
            print(f"Reactive scaling decision is being taken...")
            core_change, quota_change, status = reactive_scaling(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_up_step, blast_quota_down_step, curr_cpu_util_batch, curr_cpu_util_int, curr_cpu_cores, curr_cpu_quota, power_error, min_power_increase_limit)
            system_dec = "reactive"
            
        curr_cpu_cores, curr_cpu_quota = apply_core_quota_changes(core_change, quota_change, status, machines, machine_curr_number_of_cores, machine_curr_core_usage_limits, "blast", min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, iteration_counter, allocated_number_of_core_data, allocated_cpu_quota_data)

        system_decision_data.append((iteration_counter, system_dec, core_change, quota_change, status))

        print("Recording data to files...")
        
        write_to_file( mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, actual_number_of_request_data, drop_percentage_data, service_rate_data, log_records, rps_prediction_data, rps_actual_next_data, iteration_progress_data, progress_percentage_data, measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data, allocated_number_of_core_data, allocated_cpu_quota_data, power_cap_values_data, system_decision_data )

        rps_prediction_data, rps_actual_next_data, allocated_number_of_core_data, allocated_cpu_quota_data, power_cap_values_data, system_decision_data = [], [], [], [], [], []

        # Proactive scaling part
        # if timeit.default_timer() - curr_time > 1500:
        #     predicted_server_power_cons_change = mw_rps_power_model(abs(diff_rps))
            
        #     # If rps prediction shows decrease in rps, then increase (if power budget stays same) the cpu core and quota given to the batch application.
        #     if diff_rps < 0:
        #         power_diff = curr_power_budget - (curr_server_power_cons - predicted_server_power_cons_change)
    
        #         if power_diff > 0:
        #             blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)

        #             for m1 in machines["machines"]["core_allocator"]:
        #                 for m2 in m1["container_name"]:
        #                     if "blast" in m2.lower():
        #                         curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                         curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                         new_cpu_cores = max(blast_min_core, curr_cpu_cores + blast_core_change)
        #                         new_cpu_quotas = max(blast_min_quota, curr_cpu_quota + blast_quota_change)

        #                         step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                         step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                
        #                         if step2_core_output == True and step2_quota_output == True:
        #                             print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))
                                
        #                         else:
        #                             with open(info_log_file, "a") as f:
        #                                 print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))
                
        #         else:
        #             blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)
                    
        #             for m1 in machines["machines"]["core_allocator"]:
        #                 for m2 in m1["container_name"]:
        #                     if "blast" in m2.lower():
        #                         curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                         curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                         new_cpu_cores = max(blast_min_core, curr_cpu_cores - blast_core_change)
        #                         new_cpu_quotas = max(blast_min_quota, curr_cpu_quota - blast_quota_change)

        #                         step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                         step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                
        #                         if step2_core_output == True and step2_quota_output == True:
        #                             print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))
                                
        #                         else:
        #                             with open(info_log_file, "a") as f:
        #                                 print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))
                                
        
        #     # If rps prediction shows increase in rps, then decrease (if power budget stays same) the cpu core and quota given to the batch application.
        #     if diff_rps > 0:
        #         power_diff = curr_power_budget - (curr_server_power_cons + predicted_server_power_cons_change)

        #         if power_diff > 0:
        #             blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)
                    
        #             for m1 in machines["machines"]["core_allocator"]:
        #                 for m2 in m1["container_name"]:
        #                     if "blast" in m2.lower():
        #                         curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                         curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                         new_cpu_cores = max(blast_min_core, curr_cpu_cores + blast_core_change)
        #                         new_cpu_quotas = max(blast_min_quota, curr_cpu_quota + blast_quota_change)

        #                         step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                         step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                
        #                         if step2_core_output == True and step2_quota_output == True:
        #                             print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))                                
                                
        #                         else:
        #                             with open(info_log_file, "a") as f:
        #                                 print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                

        #         elif power_diff > 0:
        #             blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)

        #             for m1 in machines["machines"]["core_allocator"]:
        #                 for m2 in m1["container_name"]:
        #                     if "blast" in m2.lower():
        #                         curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                         curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                         new_cpu_cores = max(blast_min_core, curr_cpu_cores - blast_core_change)
        #                         new_cpu_quotas = max(blast_min_quota, curr_cpu_quota - blast_quota_change)

        #                         step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                         step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                
        #                         if step2_core_output == True and step2_quota_output == True:
        #                             print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))                                
                                
        #                         else:
        #                             with open(info_log_file, "a") as f:
        #                                 print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                             machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                             machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                
                    
        #         else:
        #             power_diff = curr_server_power_cons - curr_power_budget
                    
        #             if power_diff > 0:
        #                 blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)

        #                 for m1 in machines["machines"]["core_allocator"]:
        #                     for m2 in m1["container_name"]:
        #                         if "blast" in m2.lower():
        #                             curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                             curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                             new_cpu_cores = max(blast_min_core, curr_cpu_cores - blast_core_change)
        #                             new_cpu_quotas = max(blast_min_quota, curr_cpu_quota - blast_quota_change)

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                    
        #                             if step2_core_output == True and step2_quota_output == True:
        #                                 print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                                 machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                                 machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                                 allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                                 allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))                                
                                    
        #                             else:
        #                                 with open(info_log_file, "a") as f:
        #                                     print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                                 machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                                 machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                                 step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                                 step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                                 allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                                 allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                
                        
        #             elif power_diff < 0:
        #                 blast_core_change, blast_quota_change = convert_from_power_to_cpu_core_quota(min_cpu_core, max_cpu_core, blast_min_quota, max_cpu_quota, blast_quota_step, power_diff)
                    
        #                 for m1 in machines["machines"]["core_allocator"]:
        #                     for m2 in m1["container_name"]:
        #                         if "blast" in m2.lower():
        #                             curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                             curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                             new_cpu_cores = max(blast_min_core, curr_cpu_cores + blast_core_change)
        #                             new_cpu_quotas = max(blast_min_quota, curr_cpu_quota + blast_quota_change)

        #                             step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, new_cpu_cores)
        #                             step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, new_cpu_cores * new_cpu_quotas)
                    
        #                             if step2_core_output == True and step2_quota_output == True:
        #                                 print(f"{new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has been allocated for {m2} hosted on {m1['ip']}.")

        #                                 machine_curr_number_of_cores[(m1["ip"], m2)] = new_cpu_cores
        #                                 machine_curr_core_usage_limits[(m1["ip"], m2)] = new_cpu_quotas

        #                                 allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, new_cpu_cores))
        #                                 allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, new_cpu_quotas))                                
                                    
        #                             else:
        #                                 with open(info_log_file, "a") as f:
        #                                     print(f"Iteration: {iteration_counter} : {new_cpu_cores} and {new_cpu_quotas}% cpu bandwidth limit has NOT been able to be allocated for {m2} hosted on {m1['ip']}.")

        #                                 machine_curr_number_of_cores[(m1["ip"], m2)] = curr_cpu_cores
        #                                 machine_curr_core_usage_limits[(m1["ip"], m2)] = curr_cpu_quota

        #                                 step2_core_output = run_core_number_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores)
        #                                 step2_quota_output = run_core_usage_allocator(m1["ip"], m1["port"], m2, curr_cpu_cores * curr_cpu_quota)

        #                                 allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                                 allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                

        #             else:
        #                 for m1 in machines["machines"]["core_allocator"]:
        #                     for m2 in m1["container_name"]:
        #                         if "blast" in m2.lower():
        #                             curr_cpu_cores = machine_curr_number_of_cores[(m1["ip"], m2)]
        #                             curr_cpu_quota = machine_curr_core_usage_limits[(m1["ip"], m2)]

        #                             allocated_number_of_core_data.append((iteration_counter, m1["ip"], m2, curr_cpu_cores))
        #                             allocated_cpu_quota_data.append((iteration_counter, m1["ip"], m2, curr_cpu_quota))                                

        # reset latency-sensitive application variables
        mean_response_time_data, tail_response_time_data, error_data, estimated_number_of_request_data, actual_number_of_request_data, drop_percentage_data, service_rate_data, = [], [], [], [], [], [], []
        # reset batch application variables
        iteration_progress_data, progress_percentage_data = [], []
        # reset system telemetry variables
        measured_cpu_power_data, measured_server_power_data, cpu_util_data, cpu_freq_data = [], [], [], []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Application Telemetry Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Latency-sensitive arguments
    parser.add_argument("-llf", "--l-log-file", default="/var/log/haproxy.log", help="HAProxy log file location")
    parser.add_argument("-lts", "--l-target-slo", default=250, type=int, help="target SLO response time for latency-sensitive application")

    parser.add_argument("-mrt", "--mean-rt", default="./data/real-rt.txt", help="File to keep measured response time")
    parser.add_argument("-trt", "--tail-rt", default="./data/tail-rt.txt", help="File to keep measured tail response times")
    parser.add_argument("-ev", "--error-value", default="./data/error-value.txt", help="File to keep error value")
    parser.add_argument("-er", "--est-number-of-request", default="./data/est-number-of-request.txt", help="File to keep estimated number of request")
    parser.add_argument("-ar", "--actual-number-of-request", default="./data/act-number-of-request.txt", help="File to keep actual number of request")
    parser.add_argument("-dp", "--drop-percent", default="./data/drop-percentage.txt", help="File to keep percentage of dropped requests")
    parser.add_argument("-sr", "--service-rate", default="./data/service-rate.txt", help="File to keep service rate")
    parser.add_argument("-lf", "--log-file", default="./data/log-file.txt", help="File to keep interested log file columns")

    parser.add_argument("-rp", "--rps-prediction", default="./data/rps-prediction.txt", help="File to RPS predictions")
    parser.add_argument("-ra", "--rps-actual-next", default="./data/rps-actual-next.txt", help="File to actual RPS")
    
    # Batch application arguments
    parser.add_argument("-blf", "--b-log-file", default="/nfs/obelix/raid2/msavasci/workflows/blast/TigresBlast-235-16-DISTRIBUTE_PROCESS.log", help="Blast progress log file location")
    parser.add_argument("-bts", "--b-target-slo", default=235, type=int, help="target iteration SLO for blast")

    parser.add_argument("-ip", "--iteration-progress", default="./data/iteration-progress.txt", help="File to keep iteration progress data")
    parser.add_argument("-pp", "--progress-percentage", default="./data/progress-percentage.txt", help="File to keep progress percentage")
    
    # System telemetry
    parser.add_argument("-cp", "--measured-cpu-power", default="./data/measured_cpu_power.txt", help="File to measured cpu power")
    parser.add_argument("-sp", "--measured-server-power", default="./data/measured_server_power.txt", help="File to measured server power")
    parser.add_argument("-cf", "--cpu-frequency", default="./data/cpu_frequency.txt", help="File to keep cpu frequency")
    parser.add_argument("-cu", "--cpu-utilization", default="./data/cpu_utilization.txt", help="File to keep cpu utilization")
    parser.add_argument("-anc", "--allocated-number-of-core", default="./data/allocated-number-of-core.txt", help="File to keep allocated number of core")
    parser.add_argument("-acq", "--allocated-cpu-quota", default="./data/allocated-cpu-quota.txt", help="File to keep allocated cpu quota")
    parser.add_argument("-pc", "--power-cap", default="./data/power-cap.txt", help="File to keep power cap values")
    parser.add_argument("-sd", "--system-decision", default="./data/system-decision.txt", help="File to system decisions")
    
    args = parser.parse_args()
    
    # Latency sentitive app
    f_mean_rt = args.mean_rt
    f_tail_rt = args.tail_rt
    f_error_value = args.error_value
    f_est_number_of_request = args.est_number_of_request
    f_actual_number_of_request = args.actual_number_of_request
    f_drop_percent = args.drop_percent
    f_service_rate = args.service_rate
    f_log_file = args.log_file

    f_rps_prediction = args.rps_prediction
    f_rps_next = args.rps_actual_next

    # Batch-application
    f_progress = args.iteration_progress                            # File for iteration progress
    f_progress_percentage = args.progress_percentage                # File for controller input/error input

    # System telemetries    
    f_measured_cpu_power = args.measured_cpu_power                  # File for keeping measured cpu power consumption
    f_measured_server_power = args.measured_server_power            # File for keeping measured cpu power consumption
    f_cpu_freq = args.cpu_frequency                                 # File for keeping cpu frequency
    f_cpu_util = args.cpu_utilization                               # File for keeping cpu utilization
    f_allocated_number_of_core = args.allocated_number_of_core      # File for keeping allocated number of core data
    f_allocated_cpu_quota = args.allocated_cpu_quota                # File for keeping allocated core quota data
    f_power_cap_values = args.power_cap
    f_system_decision = args.system_decision

    run_manager(args.l_log_file, args.l_target_slo, args.b_log_file, args.b_target_slo)